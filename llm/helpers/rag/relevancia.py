"""Búsqueda local en los campos originales y orden vectorial de Qdrant."""

from __future__ import annotations

import logging
import re

from .qdrant import QdrantStore
from .domain import HEADERS, Constraints, Hit, matches, normalize, query_filter

logger = logging.getLogger(__name__)


def normalizar_texto(texto: str) -> tuple[bool, str, str]:
    try:
        ok, mensaje, normalizado = normalize(texto)
        if not ok:
            return False, mensaje, ""
        return True, "ok", " ".join(re.sub(r"[^\w]+", " ", normalizado).split())
    except Exception as e:
        logger.error("Error en normalizar_texto: %s", e)
        return False, "No se pudo normalizar el título o la pregunta", ""


def tema_pregunta(pregunta: str) -> tuple[bool, str, str]:
    try:
        ok, mensaje, texto = normalizar_texto(pregunta)
        if not ok:
            return False, mensaje, ""
        # Quitar la fórmula de la pregunta, conservando el nombre solicitado.
        # Los tipos de título (Ingeniería, Licenciatura, etc.) también son búsquedas válidas.
        tema = re.sub(
            r"^(?:que|cuales carreras)(?: (?:puedo|podria|se puede))? estudiar\s*",
            "", texto,
        )
        tema = re.sub(
            r"^(?:(?:donde|en que (?:universidad(?:es)?|institucion(?:es)?))"
            r"(?: (?:puedo|podria|se puede|puede|podemos))? estudiar"
            r"|(?:quiero|quisiera|me gustaria|puedo|podria) estudiar|estudiar)\s+",
            "", tema,
        )
        tema = re.sub(
            r"^(?:(?:(?:la|una|las) )?carreras?(?: de| en)?|un|una|el|la)\s+", "", tema,
        )
        for plural, singular in [("profesorados", "profesorado"), ("ingenierias", "ingenieria"),
                                 ("licenciaturas", "licenciatura"), ("tecnicaturas", "tecnicatura")]:
            tema = re.sub(r"\b" + plural + r"\b", singular, tema)
        return True, "ok", tema
    except Exception as e:
        logger.error("Error en tema_pregunta: %s", e)
        return False, "No se pudo identificar la carrera solicitada", ""


def recuperar_catalogo(motor: QdrantStore, constraints: Constraints | None = None) -> tuple[bool, str, list[Hit]]:
    try:
        catalogo: list[Hit] = []
        offset: str | int | None = None
        vistos: set[str | int] = set()
        condiciones = constraints if constraints is not None else Constraints()
        ok, mensaje, filtros = query_filter(condiciones)
        if not ok:
            return False, mensaje, []
        while True:
            cuerpo = {"filter": filtros, "limit": 500, "with_payload": True, "with_vector": False}
            if offset is not None:
                cuerpo["offset"] = offset
            ok, mensaje, respuesta = motor.call("POST", "/collections/" + motor.namespace + "/points/scroll", cuerpo)
            if not ok:
                return False, mensaje, []
            resultado = respuesta["result"]
            for punto in resultado["points"]:
                payload = punto["payload"]
                if payload.get("catalog_scope") != "all_active_offers":
                    raise ValueError("La colección usa el catálogo anterior; ejecutar nuevamente la ingesta para publicar todas las ofertas")
                ok, mensaje, aceptado = matches(payload, condiciones)
                if not ok:
                    return False, mensaje, []
                if not aceptado:
                    raise ValueError("Qdrant devolvió una oferta incompatible con los filtros")
                # El scroll no tiene puntaje vectorial. Este valor no se usa para ordenar.
                catalogo.append(Hit(str(punto["id"]), 0.0, payload))
            offset = resultado.get("next_page_offset")
            if offset is None:
                return True, "ok", catalogo
            if offset in vistos:
                raise ValueError("Qdrant repitió el cursor de paginación")
            vistos.add(offset)
    except Exception as e:
        logger.error("Error en recuperar_catalogo: %s", e)
        return False, "No se pudo recuperar el catálogo para comprobar los títulos: " + str(e), []


def priorizar_carrera(pregunta: str, catalogo: list[Hit], hits: list[Hit],
                     limite: int, solo_filtros: bool = False,
                     solo_lugar: bool = False) -> tuple[bool, str, list[Hit]]:
    try:
        ok, mensaje, consulta = tema_pregunta(pregunta)
        if not ok:
            return False, mensaje, []
        if not consulta and not solo_filtros:
            return True, "ok", []
        # Un complemento final «en ...» que existe en el lugar de cursada
        # restringe ese campo, sin confundir «Ingeniería en Informática» con un lugar.
        lugar = ""
        campos_catalogo: dict[str, dict[str, str]] = {}
        for hit in catalogo:
            campos: dict[str, str] = {}
            for campo in HEADERS:
                ok, mensaje, valor = normalizar_texto(hit.payload["original"][campo])
                if not ok:
                    return False, mensaje, []
                campos[campo] = valor
            campos_catalogo[hit.id] = campos
        for complemento in re.finditer(r"(?=(?:^|\s)en\s+(.+)$)", consulta):
            posible = complemento.group(1)
            if any(" " + posible + " " in " " + campos["Lugar donde se cursa"] + " "
                   for campos in campos_catalogo.values()):
                lugar = posible
                consulta = consulta[:complemento.start()].strip()
                break
        if solo_lugar:
            lugar = consulta
            consulta = ""
        conectores = {"en", "de", "del", "la", "el", "los", "las", "y", "con", "para", "una", "un"}
        terminos = [palabra for palabra in consulta.split() if palabra not in conectores]
        candidatos: dict[str, Hit] = {}
        for hit in catalogo:
            campos = campos_catalogo[hit.id]
            if lugar and " " + lugar + " " not in " " + campos["Lugar donde se cursa"] + " ":
                continue
            # Todos los términos significativos deben aparecer en algún campo
            # de la misma oferta. Las coincidencias respetan límites de palabra.
            coincide = bool(terminos) and all(
                any(" " + termino + " " in " " + valor + " " for valor in campos.values())
                for termino in terminos
            )
            if ((solo_filtros or lugar) and not consulta) or coincide:
                candidatos[hit.id] = hit
        # Conservar el orden semántico entre los títulos recuperados por el vector.
        salida = [candidatos.pop(hit.id) for hit in hits if hit.id in candidatos]
        # Rescatar también títulos exactos que quedaron fuera del top vectorial.
        salida.extend(candidatos[identificador] for identificador in sorted(candidatos))
        return True, "ok", salida[:limite]
    except Exception as e:
        logger.error("Error en priorizar_carrera: %s", e)
        return False, "No se pudo buscar en los campos del catálogo", []
