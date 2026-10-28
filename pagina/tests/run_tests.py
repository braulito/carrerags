"""Verificaciones aisladas: nunca importar wsgi ni cargar configuración real."""

import io
import json
import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Settings, build_endpoint, create_app, render_answer  # noqa: E402

logger = logging.getLogger(__name__)


def fake_upstream(payload: Any, status: int = 200) -> tuple[bool, str, MagicMock | None]:
    try:
        response = MagicMock()
        response.status = status
        response.read.return_value = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        return True, "ok", response
    except Exception as e:
        logger.error("Error en fake_upstream: %s", e)
        return False, "No se pudo crear la respuesta simulada", None


def check_http_contract() -> tuple[bool, str, list[str]]:
    try:
        resultado, mensaje, application = create_app(Settings("http://api-interna.invalid:8021"))
        assert resultado and application is not None, mensaje
        client = application.test_client()
        checks: list[str] = []

        page = client.get("/")
        assert page.status_code == 200
        assert "CarreRAGs" in page.get_data(as_text=True)
        assert "api-interna.invalid" not in page.get_data(as_text=True)
        assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
        assert page.headers["Cache-Control"] == "no-store"
        checks.append("HTML, cabeceras y configuración privada")
        assert client.get("/health").json["resultado"] is True
        for name in ("styles.css", "chat.mjs", "api.mjs", "favicon.svg"):
            assert client.get(f"/static/{name}").status_code == 200, name
        checks.append("health y recursos locales")

        for payload in ({}, {"pregunta": None}, {"pregunta": 123}, {"pregunta": "  "}, [], {"pregunta": "a" * 8001}):
            response = client.post("/api/consulta", json=payload)
            assert response.status_code == 422
            assert response.json["resultado"] is False
        assert client.post("/api/consulta", data="{", content_type="application/json").status_code == 422
        assert client.post("/api/consulta", data="a" * 40000, content_type="application/json").status_code == 413
        assert client.get("/api/consulta").status_code == 405
        checks.append("entradas inválidas, tamaño y método HTTP")

        payload = {
            "resultado": True, "mensaje": "ok", "pregunta": "Diseño a distancia",
            "salida": {"respuesta": "## Tus opciones\n\n[Institución](https://universidad.invalid/carrera)\n\n- Diseño", "modalidad": "distancia"},
        }
        ready, _, upstream = fake_upstream(payload)
        assert ready
        with patch("app.urlopen", return_value=upstream) as call:
            response = client.post("/api/consulta", json={"pregunta": " Diseño a distancia "})
            assert response.status_code == 200
            assert response.json["resultado"] is True
            assert "<h2>Tus opciones</h2>" in response.json["respuesta_html"]
            assert response.json["salida"]["modalidad"] == "distancia"
            sent = call.call_args.args[0]
            assert sent.full_url == "http://api-interna.invalid:8021/llmrag/armador"
            assert sent.method == "POST"
            assert json.loads(sent.data) == {"pregunta": "Diseño a distancia"}
            assert call.call_args.kwargs["timeout"] == 240
            assert call.call_count == 1
        checks.append("consulta correcta, POST UTF-8, timeout y llamada única")

        for status in (401, 404, 422, 429, 500, 502, 503):
            error_body = {"resultado": False, "mensaje": "Fallo simulado", "salida": {}}
            if status == 422:
                error_body = {"detail": [{"msg": "Entrada inválida"}]}
            error = HTTPError("http://api-interna.invalid", status, "Fallo simulado", {}, io.BytesIO(json.dumps(error_body).encode()))
            with patch("app.urlopen", side_effect=error) as call:
                response = client.post("/api/consulta", json={"pregunta": "Diseño"})
                assert response.status_code == status, (status, response.status_code)
                assert response.json["resultado"] is False
                assert call.call_count == 1
        error = HTTPError("http://api-interna.invalid", 503, "Fallo simulado", {}, io.BytesIO(b"<html>no disponible</html>"))
        with patch("app.urlopen", side_effect=error):
            response = client.post("/api/consulta", json={"pregunta": "Diseño"})
            assert response.status_code == 503
            assert response.json["resultado"] is False
        checks.append("estados HTTP externos y validación FastAPI conservados")

        for body in (b"no-json", [], {"resultado": True}, {"resultado": True, "salida": {"respuesta": " "}}, {"salida": {}}):
            _, _, upstream = fake_upstream(body)
            with patch("app.urlopen", return_value=upstream):
                response = client.post("/api/consulta", json={"pregunta": "Diseño"})
                assert response.status_code == 502
                assert response.json["resultado"] is False
        _, _, upstream = fake_upstream({"resultado": False, "mensaje": "Fallo simulado", "salida": {}})
        with patch("app.urlopen", return_value=upstream):
            response = client.post("/api/consulta", json={"pregunta": "Diseño"})
            assert response.status_code == 200 and response.json["resultado"] is False
        checks.append("JSON inválido, respuestas incompletas y resultado false con HTTP 200")

        for exception, expected in ((TimeoutError("Timeout simulado"), 504), (URLError(TimeoutError("Timeout simulado")), 504), (URLError("Conexión simulada"), 502), (ValueError("Fallo simulado"), 502)):
            with patch("app.urlopen", side_effect=exception) as call:
                response = client.post("/api/consulta", json={"pregunta": "Diseño"})
                assert response.status_code == expected
                assert response.json["resultado"] is False
                assert call.call_count == 1
        checks.append("timeouts, conexión fallida y ausencia de reintentos")

        _, _, upstream = fake_upstream(payload)
        with patch("app.urlopen", return_value=upstream), patch("app.render_answer", return_value=(False, "Error simulado", "")):
            response = client.post("/api/consulta", json={"pregunta": "Diseño"})
            assert response.status_code == 500
        checks.append("fallo local de presentación conserva HTTP 500")
        return True, "ok", checks
    except Exception as e:
        logger.error("Error en check_http_contract: %s", e, exc_info=True)
        return False, "Falló el contrato HTTP", []


def check_content_and_configuration() -> tuple[bool, str, list[str]]:
    try:
        for url in ("http://servidor.invalid:8021", "https://servidor.invalid/llmrag/armador/"):
            resultado, mensaje, endpoint = build_endpoint(url)
            assert resultado, mensaje
            assert endpoint.endswith("/llmrag/armador")
            assert endpoint.count("/llmrag/armador") == 1
        for url in ("", "file:///archivo", "https://usuario:valor-ficticio@servidor.invalid", "https://servidor.invalid?clave=ficticia", "https://servidor.invalid#dato", "http://servidor.invalid:70000"):
            assert build_endpoint(url)[0] is False
        assert create_app(Settings(""))[0] is False

        markdown = (
            '## Opciones\n\n<script>alert(1)</script>\n\n'
            '<iframe src="https://externo.invalid"></iframe>\n\n'
            '[Peligroso](javascript:alert(1))\n\n![Imagen](https://externo.invalid/pixel)\n\n'
            '[Institución](https://universidad.invalid)\n\n'
            '| Carrera | Modalidad |\n|---|---|\n| Diseño | Distancia |'
        )
        resultado, mensaje, html = render_answer(markdown)
        assert resultado, mensaje
        assert "<script" not in html and "<iframe" not in html and "<img" not in html
        assert 'href="javascript:' not in html
        assert 'href="https://universidad.invalid"' in html
        assert "<table>" in html and "<h2>Opciones</h2>" in html
        return True, "ok", ["URL base y completa, rechazo de credenciales", "Markdown con tablas y enlaces; HTML y protocolos peligrosos bloqueados"]
    except Exception as e:
        logger.error("Error en check_content_and_configuration: %s", e, exc_info=True)
        return False, "Falló la validación de contenido/configuración", []


def run_tests() -> tuple[bool, str, dict[str, Any]]:
    try:
        checks: list[str] = []
        # Estos guardas bloquean cualquier carga accidental o conexión real.
        with patch("app.load_dotenv", side_effect=AssertionError("No se permite cargar configuración real en pruebas")), patch("app.urlopen", side_effect=AssertionError("No se permiten conexiones reales en pruebas")):
            for check in (check_http_contract, check_content_and_configuration):
                resultado, mensaje, salida = check()
                if not resultado:
                    return False, mensaje, {"checks": checks}
                checks.extend(salida)
        return True, "ok", {"checks": checks, "cantidad": len(checks)}
    except Exception as e:
        logger.error("Error en run_tests: %s", e, exc_info=True)
        return False, "Fallaron las verificaciones", {}


if __name__ == "__main__":
    resultado, mensaje, salida = run_tests()
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "salida": salida}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
