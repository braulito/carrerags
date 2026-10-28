"""Cliente de embeddings HTTP: python run_e.py. El usuario configura .env."""

from __future__ import annotations

import json
import logging
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from run import ejecutar_configuracion
from carrerags_ingesta.config import read_settings

logger = logging.getLogger(__name__)
VARIABLES = {"VECTORIAL", "VECTORIAL_NAMESPACE", "VECTORIAL_API_KEY", "EMBEDDING_URL", "HTTP_TIMEOUT"}


def leer_variables(base_dir: Path) -> tuple[bool, str, dict[str, str]]:
    try:
        from dotenv import dotenv_values

        # Únicamente se llama en el arranque del usuario; las pruebas inyectan
        # valores o simulan dotenv. No buscar archivos en carpetas superiores.
        valores = dotenv_values(dotenv_path=base_dir / ".env", encoding="utf-8-sig", interpolate=False)
        return True, "ok", {clave: valor for clave, valor in valores.items()
                            if clave in VARIABLES and isinstance(valor, str)}
    except ModuleNotFoundError as e:
        logger.error("Error en leer_variables, dependencia faltante: %s", e)
        return False, "Instalar dependencias con python -m pip install -r reqs_e.txt", {}
    except Exception as e:
        logger.error("Error en leer_variables: %s", e)
        return False, "No se pudo cargar la configuración de run_e.py", {}


def leer_configuracion(base_dir: Path, valores: Mapping[str, str] | None = None) -> tuple[bool, str, dict[str, Any]]:
    try:
        if valores is None:
            ok, mensaje, fuente = leer_variables(base_dir)
            if not ok:
                return False, mensaje, {}
        else:
            fuente = {clave: valor for clave, valor in valores.items() if clave in VARIABLES}
        for clave in ("VECTORIAL", "EMBEDDING_URL"):
            direccion = fuente.get(clave, "").strip()
            if not direccion:
                raise ValueError("Falta configurar " + clave)
            url = urlsplit(direccion)
            if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                    or url.path not in {"", "/"} or url.query or url.fragment):
                raise ValueError(clave + " debe ser una URL HTTP sin credenciales ni ruta")
            _ = url.port
            fuente[clave] = direccion.rstrip("/")
        ok, mensaje, settings = read_settings({**fuente, "EMBEDDING_PROVIDER": "http"})
        if not ok or settings is None:
            return False, mensaje, {}
        datos = json.loads((base_dir / "local_pregunta.json").read_text(encoding="utf-8-sig"))
        if not isinstance(datos, dict):
            raise ValueError("local_pregunta.json debe contener un objeto JSON")
        pregunta = datos.get("PREGUNTA")
        limite = datos.get("LIMITE", 100)
        if not isinstance(pregunta, str) or not pregunta.strip():
            raise ValueError("PREGUNTA debe ser un texto no vacío")
        if type(limite) is not int or not 1 <= limite <= 100:
            raise ValueError("LIMITE debe ser un entero entre 1 y 100")
        return True, "ok", {"pregunta": pregunta.strip(), "limite": limite, "settings": settings}
    except Exception as e:
        logger.error("Error en run_e.leer_configuracion: %s", e)
        return False, "Revisar las variables de conexión y el JSON de local_pregunta.json", {}


def nombre_archivo(pregunta: str) -> tuple[bool, str, str]:
    try:
        nombre = re.sub(r'[<>:"/\\|?\x00-\x1f\x7f]', "", pregunta)
        nombre = nombre.replace("¿", "").strip().strip(". ")
        if not nombre:
            nombre = "consulta"
        if nombre.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                                             *{"COM" + str(i) for i in range(10)},
                                             *{"LPT" + str(i) for i in range(10)}}:
            nombre = "_" + nombre
        if len(nombre.encode("utf-16-le")) > 180:
            sufijo = hashlib.sha256(pregunta.encode("utf-8")).hexdigest()[:10]
            nombre = nombre.encode("utf-16-le")[:156].decode("utf-16-le", errors="ignore").rstrip(". ") + "_" + sufijo
        return True, "ok", nombre + ".json"
    except Exception as e:
        logger.error("Error en nombre_archivo: %s", e)
        return False, "No se pudo crear el nombre de salida de la pregunta", ""


def ejecutar(base_dir: Path, valores: Mapping[str, str] | None = None) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, mensaje, config = leer_configuracion(base_dir, valores)
        if not ok:
            return False, mensaje, {}
        ok, mensaje, nombre = nombre_archivo(config["pregunta"])
        if not ok:
            return False, mensaje, {}
        return ejecutar_configuracion(base_dir, config, "salidas/local/" + nombre)
    except Exception as e:
        logger.error("Error en run_e.ejecutar: %s", e)
        return False, "No se pudo completar la consulta con embeddings HTTP", {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    resultado, mensaje, salida = ejecutar(Path(__file__).resolve().parent)
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "salida": salida}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
