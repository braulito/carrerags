"""Interpretación explícita de condiciones de búsqueda, sin LLM."""

from __future__ import annotations

import logging
import re
from typing import Any

from carrerags_ingesta.domain import Constraints, query_filter
from relevancia import normalizar_texto, tema_pregunta

logger = logging.getLogger(__name__)


def interpretar_pregunta(pregunta: str) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, mensaje, original = normalizar_texto(pregunta)
        if not ok:
            return False, mensaje, {}
        solo_lugar = bool(re.match(r"^(?:que|cuales carreras)(?: (?:puedo|podria|se puede))? estudiar en\s+", original))
        ok, mensaje, texto = tema_pregunta(pregunta)
        if not ok:
            return False, mensaje, {}
        texto = re.sub(r"\bon line\b", "online", texto)
        constraints = Constraints()
        avisos: list[str] = []
        hubo_filtros = False
        patron_viajes = r"\b(?:sin viajar|sin presencialidad|no puedo viajar)\b"
        if re.search(patron_viajes, texto):
            constraints.no_travel = True
            texto = re.sub(patron_viajes, " ", texto)
            hubo_filtros = True
        patron_secundario = (
            r"\b(?:tengo (?:solo )?(?:el )?secundario(?: (?:completo|terminado))?"
            r"|solo (?:tengo )?(?:el )?secundario(?: (?:completo|terminado))?"
            r"|(?:con|termine) (?:el )?secundario(?: (?:completo|terminado))?"
            r"|sin (?:titulo|estudios) (?:superior(?:es)?(?: previo(?:s)?)?|previo(?:s)?)"
            r"|no tengo titulo (?:superior|previo))\b"
        )
        if re.search(patron_secundario, texto):
            constraints.secondary_only = True
            texto = re.sub(patron_secundario, " ", texto)
            avisos.append("Se excluyen títulos previos, accesos restringidos y títulos intermedios; el ingreso con secundario puede seguir pendiente de confirmar.")
            hubo_filtros = True
        if re.search(r"\b(?:no|sin)\s+(?:online|virtual(?:es)?|public[oa]s?|privad[oa]s?|presencial(?:es)?)\b", texto):
            raise ValueError("No se admite esa negación; indicar una modalidad o gestión positiva")
        modalidades: set[str] = set()
        for valor, patron in [
            ("distancia", r"\b(?:online|a distancia|virtual(?:es)?|remot[oa]s?)\b"),
            ("semipresencial", r"\bsemipresencial(?:es)?\b"),
            ("hibrida", r"\bhibrid[oa]s?\b"),
            ("presencial", r"\bpresencial(?:es)?\b"),
        ]:
            if re.search(patron, texto):
                modalidades.add(valor)
                texto = re.sub(patron, " ", texto)
                hubo_filtros = True
        if len(modalidades) > 1:
            raise ValueError("La pregunta pide varias modalidades; elegir una o no indicar modalidad")
        if modalidades:
            constraints.modality = modalidades.pop()
        gestiones: set[str] = set()
        for valor, adjetivo in [("Pública", r"public[oa]s?|estatal(?:es)?"), ("Privada", r"privad[oa]s?")]:
            # El contexto distingue «profesorado público» de títulos como
            # «Administración Pública» o «Contador Público».
            patron = (
                r"\b(?:(?:en\s+)?(?:(?:una|un|las|los)\s+)?(?:universidad(?:es)?|institucion(?:es)?|gestion)\s+"
                r"|(?:que\s+sean?|solo|solamente|exclusivamente)\s+)"
                r"(?:" + adjetivo + r")\b"
            )
            patron_tipo = (r"\b(profesorados?|ingenierias?|licenciaturas?|tecnicaturas?|carreras?)\s+(?:y\s+)?"
                           r"(?:" + adjetivo + r")\b")
            patron_inicial = r"^\s*(?:y\s+)?(?:" + adjetivo + r")\b"
            if re.search(patron, texto) or re.search(patron_tipo, texto) or re.search(patron_inicial, texto):
                gestiones.add(valor)
                texto = re.sub(patron, " ", texto)
                texto = re.sub(patron_tipo, r"\1", texto)
                texto = re.sub(patron_inicial, " ", texto)
                hubo_filtros = True
        if len(gestiones) > 1:
            raise ValueError("La pregunta pide gestión pública y privada a la vez; elegir una o no indicar gestión")
        if gestiones:
            constraints.management = gestiones.pop()
        if constraints.no_travel:
            avisos.append("Sin viajar exige cursada a distancia, exámenes remotos y prácticas remotas o que no apliquen, confirmados en los datos.")
        # Quitar conectores que quedaron al retirar condiciones; preservar los
        # conectores internos del nombre, por ejemplo «Ciencias de la Educación».
        ok, mensaje, texto = tema_pregunta(texto)
        if not ok:
            return False, mensaje, {}
        palabras = texto.split()
        bordes = {"y", "o", "que", "sea", "sean", "en", "de", "a", "con", "para", "solo",
                  "solamente", "exclusivamente", "modalidad", "cursada", "universidad", "universidades",
                  "institucion", "instituciones", "hay", "cuales", "son", "existen"}
        while palabras and palabras[0] in bordes:
            palabras.pop(0)
        while palabras and palabras[-1] in bordes:
            palabras.pop()
        tema = " ".join(palabras)
        if not tema and not hubo_filtros:
            raise ValueError("Indicar una carrera o al menos una condición de búsqueda")
        ok, mensaje, _ = query_filter(constraints)
        if not ok:
            return False, mensaje, {}
        return True, "ok", {"tema": tema, "constraints": constraints, "solo_filtros": not tema,
                            "solo_lugar": solo_lugar, "avisos": avisos}
    except Exception as e:
        logger.error("Error en interpretar_pregunta: %s", e)
        return False, "No se pudo interpretar la pregunta: " + str(e), {}
