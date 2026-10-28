"""Página y proxy de CarreRAGs. Importar este módulo no carga configuración."""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import bleach
from dotenv import load_dotenv
from flask import Flask, Response, current_app, jsonify, render_template, request
from markdown_it import MarkdownIt
from werkzeug.exceptions import RequestEntityTooLarge

logger = logging.getLogger(__name__)
API_TIMEOUT_SECONDS = 240
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_QUESTION_LENGTH = 8000
MARKDOWN_TAGS = {
    "p", "br", "strong", "em", "s", "blockquote", "ul", "ol", "li", "a",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
}


@dataclass(frozen=True)
class Settings:
    """Configuración inyectable para no cargar archivos durante las pruebas."""

    url_api: str
    api_timeout_seconds: int = API_TIMEOUT_SECONDS


def build_endpoint(url_api: str) -> tuple[bool, str, str]:
    """Acepta una URL base o el endpoint completo, sin credenciales en la URL."""
    try:
        parsed = urlsplit(url_api.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return False, "URL_API debe ser una URL HTTP(S) sin credenciales, query ni fragmento", ""
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return False, "El puerto de URL_API no es válido", ""
        endpoint = url_api.strip().rstrip("/")
        if not endpoint.endswith("/llmrag/armador"):
            endpoint += "/llmrag/armador"
        return True, "ok", endpoint
    except Exception as e:
        logger.error("Error en build_endpoint: %s", e)
        return False, "No se pudo interpretar URL_API", ""


def read_settings() -> tuple[bool, str, Settings | None]:
    """Solo el arranque real carga el archivo local; el entorno tiene prioridad."""
    try:
        load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
        url_api = os.environ.get("URL_API", "").strip()
        if not url_api:
            return False, "Falta configurar URL_API", None
        resultado, mensaje, _ = build_endpoint(url_api)
        if not resultado:
            return False, mensaje, None
        return True, "ok", Settings(url_api=url_api)
    except Exception as e:
        logger.error("Error en read_settings: %s", e)
        return False, "No se pudo cargar la configuración de la página", None


def validate_question(payload: Any) -> tuple[bool, str, str]:
    try:
        if not isinstance(payload, dict) or not isinstance(payload.get("pregunta"), str):
            return False, "Enviá una pregunta de texto", ""
        pregunta = payload["pregunta"].strip()
        if not pregunta:
            return False, "Escribí qué te gustaría estudiar", ""
        if len(pregunta) > MAX_QUESTION_LENGTH:
            return False, f"La pregunta admite hasta {MAX_QUESTION_LENGTH} caracteres", ""
        return True, "ok", pregunta
    except Exception as e:
        logger.error("Error en validate_question: %s", e)
        return False, "No se pudo validar la pregunta", ""


def render_answer(markdown: str) -> tuple[bool, str, str]:
    """El navegador recibe HTML saneado, sin HTML crudo ni imágenes remotas."""
    try:
        renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
        html = renderer.render(markdown)
        safe_html = bleach.clean(
            html,
            tags=MARKDOWN_TAGS,
            attributes={"a": ["href", "title"], "ol": ["start"]},
            protocols={"http", "https"},
            strip=True,
        )
        return True, "ok", safe_html
    except Exception as e:
        logger.error("Error en render_answer: %s", e)
        return False, "No se pudo preparar la respuesta para mostrarla", ""


def decode_response(raw: bytes, status: int) -> tuple[bool, str, dict[str, Any]]:
    try:
        if len(raw) > MAX_RESPONSE_BYTES:
            return False, "La respuesta del servicio es demasiado grande", {}
        body = json.loads(raw.decode("utf-8"))
        if not isinstance(body, dict):
            return False, "El servicio devolvió una respuesta incompatible", {}
        if not 200 <= status < 300:
            body["resultado"] = False
            body.setdefault("mensaje", "No se pudo completar la consulta")
            return True, "ok", body
        if type(body.get("resultado")) is not bool:
            return False, "El servicio devolvió una respuesta incompatible", {}
        if body["resultado"]:
            salida = body.get("salida")
            if not isinstance(salida, dict) or not isinstance(salida.get("respuesta"), str):
                return False, "El servicio devolvió una respuesta incompleta", {}
            if not salida["respuesta"].strip():
                return False, "El servicio devolvió una respuesta vacía", {}
        if not isinstance(body.get("mensaje"), str):
            body["mensaje"] = "ok" if body["resultado"] else "No se pudo completar la consulta"
        return True, "ok", body
    except Exception as e:
        logger.error("Error en decode_response: %s", e)
        return False, "El servicio no devolvió un JSON válido", {}


def query_api(pregunta: str, settings: Settings) -> tuple[bool, str, dict[str, Any]]:
    """Una única llamada; conserva el estado HTTP recibido sin reintentos."""
    try:
        resultado, mensaje, endpoint = build_endpoint(settings.url_api)
        if not resultado:
            return False, mensaje, {"http_status": 500, "body": {}}
        upstream_request = Request(
            endpoint,
            data=json.dumps({"pregunta": pregunta}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(upstream_request, timeout=settings.api_timeout_seconds) as upstream:
                status = upstream.status
                raw = upstream.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as e:
            logger.error("Error en query_api, estado HTTP %s: %s", e.code, e)
            status = e.code
            with e:
                raw = e.read(MAX_RESPONSE_BYTES + 1)
        resultado, mensaje, body = decode_response(raw, status)
        if not resultado:
            # Un error HTTP externo conserva su código incluso sin cuerpo JSON.
            return False, mensaje, {
                "http_status": status if 400 <= status <= 599 else 502,
                "body": {},
            }
        return bool(body["resultado"]), body.get("mensaje", "ok"), {
            "http_status": status, "body": body,
        }
    except TimeoutError as e:
        logger.error("Error en query_api: %s", e)
        return False, "La consulta superó el tiempo de espera", {"http_status": 504, "body": {}}
    except URLError as e:
        logger.error("Error en query_api: %s", e)
        is_timeout = isinstance(e.reason, TimeoutError)
        return False, "La API no respondió a tiempo" if is_timeout else "No se pudo conectar con la API", {
            "http_status": 504 if is_timeout else 502, "body": {},
        }
    except Exception as e:
        logger.error("Error en query_api: %s", e)
        return False, "No se pudo consultar el servicio", {"http_status": 502, "body": {}}


def index() -> Response:
    """Adaptador público de Flask: entrega HTML, no la tupla interna."""
    try:
        return Response(render_template(
            "index.html",
            client_timeout_ms=(current_app.config["SETTINGS"].api_timeout_seconds + 10) * 1000,
            max_question_length=MAX_QUESTION_LENGTH,
        ), content_type="text/html; charset=utf-8")
    except Exception as e:
        logger.error("Error en index: %s", e)
        return Response("No se pudo cargar CarreRAGs", status=500, content_type="text/plain; charset=utf-8")


def health() -> Response:
    """Estado de la página; no consulta dependencias ni valida conectividad."""
    try:
        return jsonify(resultado=True, mensaje="ok", salida={"nombre": "carrerags-pagina", "estado": "ok"})
    except Exception as e:
        logger.error("Error en health: %s", e)
        return Response('{"resultado":false,"mensaje":"Error interno","salida":{}}', status=500, content_type="application/json")


def consulta() -> Response:
    """Adaptador público: conserva estados HTTP y agrega HTML seguro al JSON."""
    try:
        resultado, mensaje, pregunta = validate_question(request.get_json(silent=True))
        if not resultado:
            response = jsonify(resultado=False, mensaje=mensaje, salida={})
            response.status_code = 422
            return response
        resultado, mensaje, data = query_api(pregunta, current_app.config["SETTINGS"])
        status = data.get("http_status", 502)
        body = data.get("body") or {"resultado": False, "mensaje": mensaje, "salida": {}}
        if resultado:
            rendered, render_message, html = render_answer(body["salida"]["respuesta"])
            if not rendered:
                response = jsonify(resultado=False, mensaje=render_message, salida={})
                response.status_code = 500
                return response
            body["respuesta_html"] = html
        response = jsonify(body)
        response.status_code = status
        return response
    except RequestEntityTooLarge as e:
        logger.error("Error en consulta: %s", e)
        response = jsonify(resultado=False, mensaje="La consulta es demasiado grande", salida={})
        response.status_code = 413
        return response
    except Exception as e:
        logger.error("Error en consulta: %s", e)
        response = jsonify(resultado=False, mensaje="No se pudo procesar la consulta", salida={})
        response.status_code = 500
        return response


def security_headers(response: Response) -> Response:
    """Adaptador after_request de Flask."""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self'; connect-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'; object-src 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


def create_app(settings: Settings | None = None) -> tuple[bool, str, Flask | None]:
    try:
        if settings is None:
            resultado, mensaje, settings = read_settings()
            if not resultado or settings is None:
                return False, mensaje, None
        resultado, mensaje, _ = build_endpoint(settings.url_api)
        if not resultado:
            return False, mensaje, None
        app = Flask(__name__)
        app.config.update(SETTINGS=settings, MAX_CONTENT_LENGTH=32 * 1024)
        app.add_url_rule("/", view_func=index, methods=["GET"])
        app.add_url_rule("/health", view_func=health, methods=["GET"])
        app.add_url_rule("/api/consulta", view_func=consulta, methods=["POST"])
        app.after_request(security_headers)
        return True, "ok", app
    except Exception as e:
        logger.error("Error en create_app: %s", e)
        return False, "No se pudo iniciar CarreRAGs", None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    resultado, mensaje, application = create_app()
    if not resultado or application is None:
        raise SystemExit(mensaje)
    application.run(host="127.0.0.1", port=8080, debug=False)
