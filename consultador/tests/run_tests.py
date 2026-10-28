"""Suite aislada: python -I -S -X utf8 consultador/tests/run_tests.py."""

from __future__ import annotations

import ast
import json
import logging
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run
from carrerags_ingesta.domain import HEADERS, Hit, digest
from relevancia import priorizar_carrera, recuperar_catalogo

logger = logging.getLogger(__name__)
ORIGINAL = dict(zip(HEADERS, (
    "Licenciatura en Turismo", "Institución ficticia — Argentina", "Grado",
    "Gestión de actividades turísticas y planificación.", "Online", "Pública",
    "https://example.org/turismo",
)))


@dataclass
class FakeEmbeddings:
    space: str = "modelo-ficticio-normalizado"
    dimensions: int = 2
    calls: list[list[str]] = field(default_factory=list)
    failed: bool = False

    def embed(self: FakeEmbeddings, texts: list[str]) -> tuple[bool, str, list[list[float]]]:
        try:
            self.calls.append(texts)
            if self.failed:
                return False, "Fallo simulado del modelo", []
            return True, "ok", [[0.6, 0.8]]
        except Exception as e:
            logger.error("Error en FakeEmbeddings.embed: %s", e)
            return False, "Fallo del modelo ficticio", []


@dataclass
class FakeTransport:
    calls: list[dict[str, Any]] = field(default_factory=list)
    status: int = 200
    size: int = 2
    empty: bool = False
    incomplete: bool = False
    paginas: list[list[dict[str, Any]]] | None = None
    scroll_status: int = 200
    repetir_cursor: bool = False
    ignorar_filtros: bool = False
    legacy: bool = False

    def request(self: FakeTransport, method: str, url: str, headers: dict[str, str],
                body: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any]]:
        try:
            self.calls.append({"method": method, "url": url, "body": body})
            if self.status != 200:
                return False, "La API respondió con HTTP " + str(self.status), {
                    "http_status": self.status, "body": {}}
            if method == "GET":
                ok, mensaje, huella = digest("modelo-ficticio-normalizado")
                if not ok:
                    return False, mensaje, {}
                result: dict[str, Any] = {"config": {"params": {"vectors": {
                    "v_" + huella[:24]: {"size": self.size, "distance": "Cosine"}}}}}
            else:
                assert method == "POST" and url.endswith(("/points/query", "/points/scroll"))
                if url.endswith("/points/scroll") and self.scroll_status != 200:
                    return False, "La API respondió con HTTP " + str(self.scroll_status), {
                        "http_status": self.scroll_status, "body": {}}
                original = dict(ORIGINAL)
                if self.incomplete:
                    original.pop("URL")
                payload = {"catalog_scope": "all_active_offers", "active": True, "eligible": True, "modality": "distancia",
                           "admission": "desconocido", "original": original, "extra": "omitir"}
                if self.legacy:
                    payload.pop("catalog_scope")
                result = {"points": [] if self.empty else [
                    {"id": "oferta-ficticia", "score": 0.9, "payload": payload}]}
                if url.endswith("/points/scroll"):
                    if self.paginas is not None:
                        pagina = (body or {}).get("offset", 0)
                        result = {"points": self.paginas[pagina], "next_page_offset":
                                  pagina + 1 if pagina + 1 < len(self.paginas) else None}
                    if self.repetir_cursor:
                        result["next_page_offset"] = 1
                if not self.ignorar_filtros:
                    filtros = (body or {}).get("filter", {})
                    result["points"] = [p for p in result["points"] if
                        all((p["payload"].get(c["key"]) in c["match"]["any"] if "any" in c["match"]
                             else p["payload"].get(c["key"]) == c["match"]["value"]) for c in filtros.get("must", []))
                        and all(p["payload"].get(c["key"]) not in c["match"]["any"] for c in filtros.get("must_not", []))]
            return True, "ok", {"http_status": 200, "body": {"status": "ok", "result": result}}
        except Exception as e:
            logger.error("Error en FakeTransport.request: %s", e)
            return False, "Fallo del transporte ficticio", {}


def escribir_config(base_dir: Path, changes: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    try:
        valores = {"PREGUNTA": "¿Dónde puedo estudiar turismo?", "VECTORIAL": "http://example.invalid:6333",
                   "VECTORIAL_NAMESPACE": "catalogo_prueba", "LIMITE": 3, **changes}
        (base_dir / "config.json").write_text(json.dumps(valores, ensure_ascii=False), encoding="utf-8")
        return True, "ok", valores
    except Exception as e:
        logger.error("Error en escribir_config: %s", e)
        return False, "No se pudo crear la configuración ficticia", {}


def check_consulta_y_salida() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = escribir_config(base_dir, {})
            assert ok, mensaje
            modelo, transporte = FakeEmbeddings(), FakeTransport()
            with patch.object(run, "create_embeddings", return_value=(True, "ok", modelo)), \
                 patch.object(run, "HttpTransport", return_value=transporte):
                ok, mensaje, salida = run.ejecutar(base_dir)
            assert ok and mensaje == "ok", mensaje
            archivo = base_dir / "respuesta.json"
            assert salida == {"archivo": str(archivo), "cantidad": 1}
            assert json.loads(archivo.read_text(encoding="utf-8")) == [{"original": ORIGINAL}]
            assert modelo.calls == [["¿Dónde puedo estudiar turismo?"]]
            assert [call["method"] for call in transporte.calls] == ["GET", "POST", "POST"]
            llamada = transporte.calls[1]
            assert llamada["url"] == "http://example.invalid:6333/collections/catalogo_prueba/points/query"
            assert llamada["body"]["query"] == [0.6, 0.8]
            assert llamada["body"]["limit"] == 3
            assert llamada["body"]["with_payload"] is True
            filtros = llamada["body"]["filter"]
            assert {f["key"]: f["match"]["value"] for f in filtros["must"]} == {
                "active": True}
            assert "must_not" not in filtros
            scroll = transporte.calls[-1]
            assert scroll["url"].endswith("/points/scroll")
            assert scroll["body"]["with_vector"] is False
            assert scroll["body"]["filter"] == filtros
            assert not list(base_dir.glob("*.tmp"))
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_consulta_y_salida: %s", e)
        return False, "Falló la consulta o la proyección de originales: " + str(e), {}


def check_vacio_y_fallos() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = escribir_config(base_dir, {})
            assert ok, mensaje
            archivo = base_dir / "respuesta.json"
            for transporte in [FakeTransport(empty=True), FakeTransport(status=404),
                               FakeTransport(status=500), FakeTransport(size=384),
                               FakeTransport(incomplete=True), FakeTransport(scroll_status=503),
                               FakeTransport(repetir_cursor=True), FakeTransport(legacy=True)]:
                archivo.write_text('["resultado anterior"]', encoding="utf-8")
                with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                     patch.object(run, "HttpTransport", return_value=transporte):
                    ok, mensaje, salida = run.ejecutar(base_dir)
                if transporte.empty:
                    assert ok and salida["cantidad"] == 0, mensaje
                    assert json.loads(archivo.read_text(encoding="utf-8")) == []
                else:
                    assert not ok and salida == {} and mensaje != "ok"
                    assert json.loads(archivo.read_text(encoding="utf-8")) == ["resultado anterior"]
                    if transporte.status != 200:
                        assert str(transporte.status) in mensaje
            with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings(failed=True))), \
                 patch.object(run, "HttpTransport") as factory:
                ok, mensaje, salida = run.ejecutar(base_dir)
                assert not ok and salida == {} and "modelo" in mensaje
                factory.assert_not_called()
            with patch.object(run, "create_embeddings", return_value=(False, "Dependencia faltante", None)):
                ok, mensaje, salida = run.ejecutar(base_dir)
                assert not ok and mensaje == "Dependencia faltante" and salida == {}
            with patch.object(run.os, "replace", side_effect=OSError("Fallo simulado de escritura")):
                ok, mensaje, ruta = run.guardar_respuesta(base_dir, [])
                assert not ok and ruta == "" and mensaje != "ok"
                assert not list(base_dir.glob("*.tmp"))
                assert json.loads(archivo.read_text(encoding="utf-8")) == ["resultado anterior"]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_vacio_y_fallos: %s", e)
        return False, "Falló el manejo de vacío o errores: " + str(e), {}


def check_abogacia_y_relevancia() -> tuple[bool, str, dict[str, Any]]:
    try:
        puntos: list[dict[str, Any]] = []
        for numero in range(7):
            puntos.append({"id": "abogacia-" + str(numero), "payload": {
                "catalog_scope": "all_active_offers", "active": True, "eligible": True, "modality": "distancia", "admission": "desconocido",
                "original": {**ORIGINAL, "Título": "Abogacía", "Lugar donde se cursa":
                             "Institución ficticia " + str(numero) + " — Argentina"}}})
        gerontologia = Hit("ajena", 0.99, {"original": {**ORIGINAL, "Título": "Licenciatura en Gerontología Social",
                                                     "Descripción": "Formación en gerontología social.",
                                                     "URL": "https://example.org/gerontologia"}})
        catalogo = [gerontologia] + [Hit(p["id"], 0.0, p["payload"]) for p in puntos]
        for pregunta in ["donde puedo estudiar abogacia", "¿Dónde puedo estudiar ABOGACÍA?", "Abogacía"]:
            ok, mensaje, hits = priorizar_carrera(pregunta, catalogo, [gerontologia], 10)
            assert ok and len(hits) == 7, mensaje
            assert all(hit.payload["original"]["Título"] == "Abogacía" for hit in hits)
        ok, mensaje, hits = priorizar_carrera("abogacia", catalogo, [gerontologia, catalogo[4]], 2)
        assert ok and len(hits) == 2 and hits[0].id == catalogo[4].id, mensaje
        ok, mensaje, hits = priorizar_carrera("quiero ayudar a personas mayores", catalogo, [gerontologia], 10)
        assert ok and hits == [], mensaje
        turismo = Hit("turismo", 0.7, {"original": ORIGINAL})
        ok, mensaje, hits = priorizar_carrera("donde puedo estudiar turismo", [turismo, gerontologia], [gerontologia], 10)
        assert ok and hits == [turismo], mensaje
        ok, mensaje, hits = priorizar_carrera("abogacias", catalogo, [gerontologia], 10)
        assert ok and hits == [], mensaje  # No confundir subcadenas de palabras.
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = escribir_config(base_dir, {"PREGUNTA": "donde puedo estudiar abogacia", "LIMITE": 10})
            assert ok, mensaje
            transporte = FakeTransport(paginas=[puntos[:3], puntos[3:]])
            with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                 patch.object(run, "HttpTransport", return_value=transporte):
                ok, mensaje, salida = run.ejecutar(base_dir)
            assert ok and salida["cantidad"] == 7, mensaje
            respuesta = json.loads((base_dir / "respuesta.json").read_text(encoding="utf-8"))
            assert len(respuesta) == 7 and all(r["original"]["Título"] == "Abogacía" for r in respuesta)
            assert transporte.calls[-1]["body"]["offset"] == 1
        # El control local también rechaza registros inactivos devueltos por un motor defectuoso.
        puntos[0]["payload"]["active"] = False
        motor = run.QdrantStore("http://example.invalid", transport=FakeTransport(paginas=[puntos], ignorar_filtros=True))
        ok, mensaje, hits = recuperar_catalogo(motor)
        assert not ok and hits == [] and mensaje != "ok"
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_abogacia_y_relevancia: %s", e)
        return False, "Falló la regresión de Abogacía o la relevancia por título: " + str(e), {}


def check_medicina_ausente() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = escribir_config(base_dir, {"PREGUNTA": "Dónde puedo estudiar medicina", "LIMITE": 10})
            assert ok, mensaje
            (base_dir / "respuesta.json").write_text('["resultado anterior"]', encoding="utf-8")
            puntos: list[dict[str, Any]] = []
            for numero, titulo in enumerate(["Licenciatura en Fonoaudiología", "Licenciatura en Gerontología",
                                             "Licenciatura en Enfermería", "Técnico Superior en Seguros"]):
                puntos.append({"id": str(numero), "payload": {
                    "catalog_scope": "all_active_offers", "active": True, "eligible": True, "modality": "distancia", "admission": "desconocido",
                    "original": {**ORIGINAL, "Título": titulo}}})
            transporte = FakeTransport(paginas=[puntos])
            with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                 patch.object(run, "HttpTransport", return_value=transporte):
                ok, mensaje, salida = run.ejecutar(base_dir)
            assert ok and mensaje == "ok" and salida["cantidad"] == 0
            assert json.loads((base_dir / "respuesta.json").read_text(encoding="utf-8")) == []
            # Cuando la carrera sí existe, tampoco depende de su puesto vectorial.
            puntos.append({"id": "medicina", "payload": {"original": {**ORIGINAL, "Título": "Medicina"}}})
            catalogo = [Hit(p["id"], 0.0, p["payload"]) for p in puntos]
            ok, mensaje, hits = priorizar_carrera("Dónde puedo estudiar medicina", catalogo, catalogo[:4], 10)
            assert ok and [hit.id for hit in hits] == ["medicina"], mensaje
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_medicina_ausente: %s", e)
        return False, "Falló la regresión de Medicina ausente: " + str(e), {}


def check_ingenieria_general_y_especifica() -> tuple[bool, str, dict[str, Any]]:
    try:
        titulos = ["Ingeniería Electrónica", "Ingeniería en Ciencia de Datos", "Ingeniería en Informática",
                   "Ingeniería en Inteligencia Artificial", "Ingeniería en Telecomunicaciones", "Ingeniería Industrial"]
        puntos: list[dict[str, Any]] = []
        for numero, titulo in enumerate(titulos + ["Licenciatura en Informática", "Abogacía"]):
            puntos.append({"id": str(numero), "payload": {
                "catalog_scope": "all_active_offers", "active": True, "eligible": True, "modality": "distancia", "admission": "desconocido",
                "original": {**ORIGINAL, "Título": titulo}}})
        catalogo = [Hit(p["id"], 0.0, p["payload"]) for p in puntos]
        for pregunta in ["Dónde puedo estudiar ingeniería", "Dónde puedo estudiar ingenieria", "Ingeniería",
                         "¿Dónde estudiar una ingeniería?", "carreras de ingeniería"]:
            ok, mensaje, hits = priorizar_carrera(pregunta, catalogo, catalogo[6:], 10)
            assert ok and len(hits) == 6, mensaje
            assert {hit.payload["original"]["Título"] for hit in hits} == set(titulos)
        for pregunta, esperados in [
            ("Dónde puedo estudiar ingeniería industrial", {"Ingeniería Industrial"}),
            ("Dónde puedo estudiar ingeniería en informática", {"Ingeniería en Informática"}),
            ("Dónde puedo estudiar informática", {"Ingeniería en Informática", "Licenciatura en Informática"}),
            ("Dónde puedo estudiar ingeniería biomédica", set()),
            ("Dónde puedo estudiar medicina", set()),
        ]:
            ok, mensaje, hits = priorizar_carrera(pregunta, catalogo, catalogo, 10)
            assert ok and {hit.payload["original"]["Título"] for hit in hits} == esperados, mensaje
        ok, mensaje, hits = priorizar_carrera("ingeniería", catalogo, [catalogo[5], catalogo[6]], 2)
        assert ok and len(hits) == 2 and hits[0].id == catalogo[5].id, mensaje
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            for pregunta in ["Dónde puedo estudiar ingeniería", "Dónde puedo estudiar ingenieria"]:
                ok, mensaje, _ = escribir_config(base_dir, {"PREGUNTA": pregunta, "LIMITE": 10})
                assert ok, mensaje
                transporte = FakeTransport(paginas=[puntos[:3], puntos[3:]])
                with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                     patch.object(run, "HttpTransport", return_value=transporte):
                    ok, mensaje, salida = run.ejecutar(base_dir)
                assert ok and salida["cantidad"] == 6, mensaje
                respuesta = json.loads((base_dir / "respuesta.json").read_text(encoding="utf-8"))
                assert {r["original"]["Título"] for r in respuesta} == set(titulos)
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_ingenieria_general_y_especifica: %s", e)
        return False, "Falló la búsqueda general o específica de Ingeniería: " + str(e), {}


def check_configuracion_y_contrato() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            for changes in [{"PREGUNTA": "  "}, {"PREGUNTA": 5}, {"LIMITE": True},
                            {"LIMITE": 0}, {"LIMITE": 101}, {"VECTORIAL": ""},
                            {"VECTORIAL_PROVIDER": "otro"}, {"EMBEDDING_PROVIDER": "otro"}]:
                ok, mensaje, _ = escribir_config(base_dir, changes)
                assert ok, mensaje
                with patch.object(run, "create_embeddings") as factory:
                    ok, mensaje, salida = run.ejecutar(base_dir)
                    assert not ok and salida == {} and mensaje != "ok"
                    factory.assert_not_called()
            for contenido in ["[]", "{json roto"]:
                (base_dir / "config.json").write_text(contenido, encoding="utf-8")
                ok, mensaje, salida = run.leer_configuracion(base_dir)
                assert not ok and salida == {} and mensaje != "ok"
            ok, mensaje, valores = escribir_config(base_dir, {"HTTP_TIMEOUT": "12"})
            assert ok, mensaje
            (base_dir / "config.json").write_text(json.dumps(valores), encoding="utf-8-sig")
            with patch.dict(run.os.environ, {"VECTORIAL": "http://ignorar.invalid", "EMBEDDING_MODEL": "ignorar"}):
                ok, mensaje, config = run.leer_configuracion(base_dir)
                assert ok, mensaje
                assert config["settings"].vectorial == valores["VECTORIAL"]
                assert config["settings"].timeout == 12
                assert config["settings"].embedding_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            arbol = ast.parse(Path(run.__file__).read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.FunctionDef):
                    assert nodo.returns is not None and ast.unparse(nodo.returns).startswith("tuple[bool, str,")
                    assert all(arg.annotation is not None for arg in nodo.args.args)
                    assert isinstance(nodo.body[0], (ast.Try, ast.AnnAssign))
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_configuracion_y_contrato: %s", e)
        return False, "Falló la validación de configuración o contratos: " + str(e), {}


def run_suite() -> tuple[bool, str, dict[str, int]]:
    try:
        fallos: list[str] = []
        pruebas = [check_consulta_y_salida, check_vacio_y_fallos, check_abogacia_y_relevancia, check_medicina_ausente,
                   check_ingenieria_general_y_especifica, check_configuracion_y_contrato]
        from check_reglas import check_interpretacion, check_filtros_en_consulta, check_reindexacion, check_profesorados_json
        pruebas.extend([check_interpretacion, check_filtros_en_consulta, check_reindexacion, check_profesorados_json])
        from check_run_e import check_run_e_configuracion, check_run_e_consulta, check_run_e_fallos, check_run_e_entradas
        pruebas.extend([check_run_e_configuracion, check_run_e_consulta, check_run_e_fallos, check_run_e_entradas])
        from check_run_e import check_run_e_nombres_y_reemplazo
        pruebas.append(check_run_e_nombres_y_reemplazo)
        from check_campos import check_todos_los_campos, check_ubicaciones_y_catalogo, check_consulta_por_lugar
        pruebas.extend([check_todos_los_campos, check_ubicaciones_y_catalogo, check_consulta_por_lugar])
        for prueba in pruebas:
            ok, mensaje, _ = prueba()
            print(("PASS " if ok else "FAIL ") + prueba.__name__)
            if not ok:
                fallos.append(mensaje)
        if fallos:
            return False, "; ".join(fallos), {"passed": len(pruebas) - len(fallos), "failed": len(fallos)}
        return True, "ok", {"passed": len(pruebas), "failed": 0}
    except Exception as e:
        logger.error("Error en run_suite: %s", e)
        return False, "No se pudo ejecutar la suite", {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)
    resultado, mensaje, salida = run_suite()
    print(mensaje, salida)
    raise SystemExit(0 if resultado else 1)
