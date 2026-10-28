"""Consultar carreras: python run.py. Configuración en config.json, sin dotenv."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Reutilizar únicamente adaptadores puros; no importar bootstrap ni cargar .env.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingesta"))

from carrerags_ingesta.adapters.http import HttpTransport
from carrerags_ingesta.registry import create_adapter
from carrerags_ingesta.adapters.qdrant import QdrantStore
from carrerags_ingesta.config import Settings, read_settings
from carrerags_ingesta.domain import HEADERS, Hit
from relevancia import priorizar_carrera, recuperar_catalogo
from reglas import interpretar_pregunta

logger = logging.getLogger(__name__)


def create_embeddings(settings: Settings) -> tuple[bool, str, Any]:
    try:
        return create_adapter("embedding", settings.embedding_provider, settings)
    except Exception as e:
        logger.error("Error en create_embeddings: %s", e)
        return False, "No se pudo crear el proveedor de embeddings", None


def leer_configuracion(base_dir: Path) -> tuple[bool, str, dict[str, Any]]:
    try:
        valores = json.loads((base_dir / "config.json").read_text(encoding="utf-8-sig"))
        if not isinstance(valores, dict):
            raise ValueError("config.json debe contener un objeto")
        pregunta = valores.get("PREGUNTA")
        if not isinstance(pregunta, str) or not pregunta.strip():
            raise ValueError("PREGUNTA debe ser un texto no vacío")
        limite = valores.get("LIMITE", 10)
        if type(limite) is not int or not 1 <= limite <= 100:
            raise ValueError("LIMITE debe ser un entero entre 1 y 100")
        if any(not isinstance(valor, str) for clave, valor in valores.items() if clave != "LIMITE"):
            raise ValueError("Los valores de configuración deben ser textos, salvo LIMITE")
        # Pasar un mapa explícito impide leer variables de entorno o archivos .env.
        ok, mensaje, settings = read_settings(valores)
        if not ok or settings is None:
            return False, mensaje, {}
        if not settings.vectorial:
            raise ValueError("Falta configurar VECTORIAL")
        if settings.vector_provider != "qdrant" or settings.embedding_provider not in {"local", "http"}:
            raise ValueError("Este script usa Qdrant y embeddings local o http")
        return True, "ok", {"pregunta": pregunta.strip(), "limite": limite, "settings": settings}
    except Exception as e:
        logger.error("Error en leer_configuracion: %s", e)
        return False, "No se pudo leer la configuración: revisar config.json y sus campos", {}


def extraer_originales(hits: list[Hit]) -> tuple[bool, str, list[dict[str, Any]]]:
    try:
        salida: list[dict[str, Any]] = []
        for hit in hits:
            original = hit.payload.get("original")
            if not isinstance(original, dict) or any(
                not isinstance(original.get(campo), str) or not original[campo].strip()
                for campo in HEADERS
            ):
                raise ValueError("Una carrera no contiene los siete campos originales completos")
            salida.append({"original": {campo: original[campo] for campo in HEADERS}})
        return True, "ok", salida
    except Exception as e:
        logger.error("Error en extraer_originales: %s", e)
        return False, "Qdrant devolvió una carrera sin los campos originales esperados", []


def guardar_respuesta(base_dir: Path, respuesta: list[dict[str, Any]],
                      nombre_salida: str = "respuesta.json") -> tuple[bool, str, str]:
    temporal: Path | None = None
    try:
        ruta_salida = Path(nombre_salida)
        salida_local = (ruta_salida.parent == Path("salidas/local") and ruta_salida.suffix == ".json"
                        and not ruta_salida.name.startswith("."))
        if nombre_salida not in {"respuesta.json", "local_salida.json"} and not salida_local:
            raise ValueError("Nombre de salida no permitido")
        destino = base_dir / nombre_salida
        destino.resolve().relative_to(base_dir.resolve())
        destino.parent.mkdir(parents=True, exist_ok=True)
        contenido = json.dumps(respuesta, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # Reemplazar el resultado solo cuando el JSON completo pudo escribirse.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destino.parent,
                                         prefix="respuesta_", suffix=".tmp", delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        os.replace(temporal, destino)
        return True, "ok", str(destino)
    except Exception as e:
        logger.error("Error en guardar_respuesta: %s", e)
        return False, "No se pudo guardar el archivo de respuesta", ""
    finally:
        if temporal is not None:
            try:
                temporal.unlink(missing_ok=True)
            except Exception as e:
                logger.error("Error en guardar_respuesta al limpiar temporal: %s", e)
                return False, "No se pudo limpiar el archivo temporal de respuesta", ""


def ejecutar(base_dir: Path) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, mensaje, config = leer_configuracion(base_dir)
        if not ok:
            return False, mensaje, {}
        return ejecutar_configuracion(base_dir, config)
    except Exception as e:
        logger.error("Error en ejecutar: %s", e)
        return False, "No se pudo completar la consulta de carreras", {}


def ejecutar_configuracion(base_dir: Path, config: dict[str, Any],
                           nombre_salida: str = "respuesta.json") -> tuple[bool, str, dict[str, Any]]:
    try:
        settings: Settings = config["settings"]
        ok, mensaje, consulta = interpretar_pregunta(config["pregunta"])
        if not ok:
            return False, mensaje, {}
        for aviso in consulta["avisos"]:
            logger.info("%s", aviso)
        ok, mensaje, modelo = create_embeddings(settings)
        if not ok or modelo is None:
            return False, mensaje, {}
        ok, mensaje, vectores = modelo.embed([config["pregunta"]])
        if not ok:
            return False, mensaje, {}
        motor = QdrantStore(settings.vectorial, settings.namespace, settings.vector_key,
                            HttpTransport(timeout=settings.timeout))
        ok, mensaje, hits = motor.search(vectores[0], consulta["constraints"], config["limite"], modelo.space)
        if not ok:
            return False, mensaje, {}
        ok, mensaje, catalogo = recuperar_catalogo(motor, consulta["constraints"])
        if not ok:
            return False, mensaje, {}
        ok, mensaje, hits = priorizar_carrera(consulta["tema"], catalogo, hits, config["limite"],
                                             consulta["solo_filtros"], consulta["solo_lugar"])
        if not ok:
            return False, mensaje, {}
        if not hits:
            logger.info("No se encontraron ofertas coincidentes en los campos del catálogo consultable")
        ok, mensaje, respuesta = extraer_originales(hits)
        if not ok:
            return False, mensaje, {}
        ok, mensaje, archivo = guardar_respuesta(base_dir, respuesta, nombre_salida)
        if not ok:
            return False, mensaje, {}
        return True, "ok", {"archivo": archivo, "cantidad": len(respuesta)}
    except Exception as e:
        logger.error("Error en ejecutar_configuracion: %s", e)
        return False, "No se pudo completar la consulta de carreras", {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    resultado, mensaje, salida = ejecutar(Path(__file__).resolve().parent)
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "salida": salida},
                     ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
