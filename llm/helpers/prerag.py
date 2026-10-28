"""Lectura de títulos, niveles, locaciones, instituciones y modalidades de Qdrant."""

import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def titulos() -> tuple[bool, str, list[str]]:
    """Devuelve los nombres únicos de todas las carreras de la colección."""
    try:
        return _obtener_valores("title")
    except Exception as e:
        logger.error("Error en obtener_carreras: %s", e)
        return False, "No se pudieron obtener las carreras de Qdrant", []


def niveles() -> tuple[bool, str, list[str]]:
    """Devuelve los niveles educativos únicos del campo level."""
    try:
        return _obtener_valores("level")
    except Exception as e:
        logger.error("Error en niveles: %s", e)
        return False, "No se pudieron obtener los niveles de Qdrant", []


def locaciones() -> tuple[bool, str, list[str]]:
    """Devuelve las locaciones únicas del campo location."""
    try:
        return _obtener_valores("location")
    except Exception as e:
        logger.error("Error en locaciones: %s", e)
        return False, "No se pudieron obtener las locaciones de Qdrant", []


def instituciones() -> tuple[bool, str, list[str]]:
    """Devuelve las instituciones únicas del campo institution."""
    try:
        return _obtener_valores("institution")
    except Exception as e:
        logger.error("Error en instituciones: %s", e)
        return False, "No se pudieron obtener las instituciones de Qdrant", []


def modalidades() -> tuple[bool, str, list[str]]:
    """Devuelve las modalidades únicas del campo modality."""
    try:
        return _obtener_valores("modality")
    except Exception as e:
        logger.error("Error en modalidades: %s", e)
        return False, "No se pudieron obtener las modalidades de Qdrant", []


def crea_prompt_rag(pregunta: str) -> tuple[bool, str, str]:
    """Completa la plantilla con los datos de Qdrant y la pregunta original."""
    try:
        if not isinstance(pregunta, str) or not pregunta.strip():
            raise ValueError("La pregunta debe ser un string no vacío")
        plantilla = Path(__file__).with_name("prompt.md").read_text(encoding="utf-8")
        consultas = {
            "TITULOS": titulos,
            "NIVELES": niveles,
            "INSTITUCIONES": instituciones,
            "LOCACIONES": locaciones,
            "MODALIDADES": modalidades,
        }
        patron = r"\{\{([A-Z_]+)\}\}"
        esperados = set(consultas) | {"PREGUNTA_USUARIO"}
        encontrados = re.findall(patron, plantilla)
        if set(encontrados) != esperados or len(encontrados) != len(esperados):
            raise ValueError("La plantilla debe contener exactamente los seis marcadores esperados")
        reemplazos = {"PREGUNTA_USUARIO": json.dumps(pregunta, ensure_ascii=False)}
        for marcador, consulta in consultas.items():
            resultado, mensaje, valores = consulta()
            if not resultado:
                return False, f"No se pudo crear el prompt: {consulta.__name__}: {mensaje}", ""
            reemplazos[marcador] = json.dumps(valores, ensure_ascii=False)
        prompt = re.sub(patron, lambda coincidencia: reemplazos[coincidencia.group(1)], plantilla)
        return True, "ok", prompt
    except Exception as e:
        logger.error("Error en crea_prompt_rag: %s", e)
        return False, "No se pudo crear el prompt para el RAG", ""


def _obtener_valores(campo: str) -> tuple[bool, str, list[str]]:
    """Recorre la colección y devuelve los valores únicos del campo indicado."""
    try:
        load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)
        direccion = os.getenv("VECTORIAL", "").strip().rstrip("/")
        namespace = os.getenv("VECTORIAL_NAMESPACE", "").strip()
        if not direccion or not namespace:
            raise ValueError("Se requieren VECTORIAL y VECTORIAL_NAMESPACE")
        if "://" not in direccion:
            direccion = "http://" + direccion
        partes = urlsplit(direccion)
        if (
            partes.scheme not in {"http", "https"}
            or not partes.hostname
            or partes.username is not None
            or partes.password is not None
            or partes.query
            or partes.fragment
        ):
            raise ValueError("VECTORIAL debe ser una URL HTTP(S) sin credenciales, query ni fragmento")

        endpoint = f"{direccion}/collections/{quote(namespace, safe='')}/points/scroll"
        nombres: set[str] = set()
        offset: int | str | None = None
        offsets_vistos: set[int | str] = set()
        while True:
            cuerpo = {
                "limit": 256,
                "with_payload": [campo],
                "with_vector": False,
            }
            if offset is not None:
                cuerpo["offset"] = offset
            solicitud = Request(
                endpoint,
                data=json.dumps(cuerpo).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(solicitud, timeout=30) as respuesta:
                pagina = json.load(respuesta)
            if pagina.get("status") != "ok":
                raise ValueError("Qdrant no confirmó la consulta")
            resultado = pagina["result"]
            for punto in resultado["points"]:
                nombre = (punto.get("payload") or {}).get(campo)
                if not isinstance(nombre, str) or not nombre.strip():
                    raise ValueError(f"Se encontró un punto sin un valor válido en {campo}")
                nombres.add(nombre.strip())
            offset = resultado["next_page_offset"]
            if offset is None:
                break
            if offset in offsets_vistos:
                raise ValueError("Qdrant repitió un offset de paginación")
            offsets_vistos.add(offset)
        return True, "ok", sorted(nombres, key=str.casefold)
    except Exception as e:
        logger.error("Error en _obtener_valores (%s): %s", campo, e)
        return False, f"No se pudieron obtener los valores de {campo} de Qdrant", []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        pregunta = "¿Dónde puedo estudiar para ser maestro de lengua?"
        resultado, mensaje, prompt = crea_prompt_rag(pregunta)
        if resultado:
            archivo_salida = Path(__file__).with_name("salida.md")
            archivo_salida.write_text(prompt, encoding="utf-8")
            print(f"Prompt guardado en {archivo_salida}")
        else:
            logger.error("No se pudo generar salida.md: %s", mensaje)
    except Exception as e:
        logger.error("Error en prueba de crea_prompt_rag: %s", e)
        resultado = False
    raise SystemExit(0 if resultado else 1)
