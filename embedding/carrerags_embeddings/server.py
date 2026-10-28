"""HTTP JSON de biblioteca estándar; un proceso y una inferencia simultánea."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .constants import (DIMENSIONS, MAX_BODY_BYTES, MAX_TEXT_LENGTH, MAX_TEXTS,
                        MAX_TOTAL_CHARS, MODEL_ID, REVISION, SPACE)
from .model import Embeddings, load_model

logger = logging.getLogger(__name__)


def validate_texts(payload: Any) -> tuple[bool, str, list[str]]:
    try:
        if not isinstance(payload, dict) or set(payload) != {"texts"}:
            raise ValueError("Se requiere un objeto con la lista texts")
        texts = payload["texts"]
        if not isinstance(texts, list) or not 1 <= len(texts) <= MAX_TEXTS:
            raise ValueError(f"texts debe contener entre 1 y {MAX_TEXTS} textos")
        if any(not isinstance(t, str) or not t.strip() or len(t) > MAX_TEXT_LENGTH for t in texts):
            raise ValueError(f"Cada texto debe ser no vacío y tener hasta {MAX_TEXT_LENGTH} caracteres")
        if sum(len(t) for t in texts) > MAX_TOTAL_CHARS:
            raise ValueError("El lote supera el límite total de caracteres")
        return True, "ok", texts
    except Exception as e:
        logger.error("Error en validate_texts: %s", e)
        return False, str(e), []


class Handler(BaseHTTPRequestHandler):
    # Hooks HTTP: el servidor ignora sus retornos; se conserva el contrato interno.
    engine: Embeddings | None = None
    timeout = 30
    server_version = "carrerags-embeddings"
    sys_version = ""

    def log_message(self: Handler, format: str, *args: Any) -> tuple[bool, str, None]:
        try:
            # No registrar URL, cuerpos, textos ni cabeceras del solicitante.
            return True, "ok", None
        except Exception as e:
            logger.error("Error en Handler.log_message: %s", e)
            return False, "No se pudo procesar el registro HTTP", None

    def reply(self: Handler, status: int, success: bool, message: str,
              data: dict[str, Any]) -> tuple[bool, str, None]:
        try:
            content = json.dumps({"resultado": success, "mensaje": message, "salida": data},
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)
            return success, "ok" if success else message, None
        except Exception as e:
            logger.error("Error en Handler.reply: %s", e)
            return False, "No se pudo enviar la respuesta HTTP", None

    def send_error(self: Handler, code: int, message: str | None = None,
                   explain: str | None = None) -> tuple[bool, str, None]:
        try:
            if code == 501:
                return self.reply(405, False, "Método no admitido", {})
            return self.reply(code, False, "Solicitud HTTP inválida", {})
        except Exception as e:
            logger.error("Error en Handler.send_error: %s", e)
            return False, "No se pudo enviar el error HTTP", None

    def do_GET(self: Handler) -> tuple[bool, str, None]:
        try:
            if self.path == "/embeddings":
                return self.reply(405, False, "Usar POST para /embeddings", {})
            if self.path != "/health":
                return self.reply(404, False, "Ruta desconocida", {})
            if self.engine is None:
                return self.reply(503, False, "Modelo no disponible", {})
            return self.reply(200, True, "ok", {"model": MODEL_ID, "revision": REVISION,
                              "dimensions": DIMENSIONS, "space": SPACE})
        except Exception as e:
            logger.error("Error en Handler.do_GET: %s", e)
            return self.reply(500, False, "Error interno", {})

    def do_POST(self: Handler) -> tuple[bool, str, None]:
        try:
            if self.path == "/health":
                return self.reply(405, False, "Usar GET para /health", {})
            if self.path != "/embeddings":
                return self.reply(404, False, "Ruta desconocida", {})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, False, "Se requiere application/json", {})
            if self.headers.get("Transfer-Encoding"):
                return self.reply(400, False, "Transfer-Encoding no admitido", {})
            lengths = self.headers.get_all("Content-Length", [])
            if not lengths:
                return self.reply(411, False, "Falta Content-Length", {})
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                return self.reply(400, False, "Content-Length inválido", {})
            size = int(lengths[0])
            if size > MAX_BODY_BYTES:
                return self.reply(413, False, "Solicitud demasiado grande", {})
            try:
                content = self.rfile.read(size)
                if len(content) != size:
                    raise ValueError("Cuerpo incompleto")
                payload = json.loads(content)
            except (ValueError, UnicodeError) as e:
                logger.error("Error en Handler.do_POST al interpretar JSON: %s", e)
                return self.reply(400, False, "JSON inválido o incompleto", {})
            ok, message, texts = validate_texts(payload)
            if not ok:
                return self.reply(422, False, message, {})
            engine = self.engine
            if engine is None:
                return self.reply(503, False, "Modelo no disponible", {})
            if not engine.lock.acquire(blocking=False):
                return self.reply(503, False, "Servicio ocupado; reintentar más tarde", {})
            try:
                ok, message, vectors = engine.encode(texts)
            finally:
                engine.lock.release()
            if not ok:
                return self.reply(500, False, message, {})
            return self.reply(200, True, "ok", {"vectors": vectors, "space": SPACE, "dimensions": DIMENSIONS})
        except Exception as e:
            logger.error("Error en Handler.do_POST: %s", e)
            return self.reply(500, False, "Error interno", {})


def main() -> tuple[bool, str, None]:
    try:
        ok, message, engine = load_model()
        if not ok or engine is None:
            return False, message, None
        Handler.engine = engine
        with ThreadingHTTPServer(("0.0.0.0", 8081), Handler) as server:
            logger.info("Embeddings locales listos en puerto 8081; dimensión %s", DIMENSIONS)
            server.serve_forever()
        return True, "ok", None
    except Exception as e:
        logger.error("Error en main: %s", e)
        return False, "No se pudo iniciar el servicio HTTP", None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    success, message, _ = main()
    if not success:
        logger.error("%s", message)
    raise SystemExit(0 if success else 1)
