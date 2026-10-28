"""Dobles y libros sintéticos; nunca carga configuración ni servicios reales."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from carrerags_ingesta.adapters.http import HttpTransport
from carrerags_ingesta.domain import HEADERS
from carrerags_ingesta.config import Settings
from carrerags_ingesta.contracts import Embedder

logger = logging.getLogger(__name__)
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def offer_row(title: str = "Tecnicatura en Programación", mode: str = "A distancia", description: str = "Programación y desarrollo de software.", level: str = "Pregrado", management: str = "Pública") -> tuple[bool, str, list[str]]:
    try:
        return True, "ok", [title, "Instituto de Ejemplo — Ciudad, Provincia", level, description, mode, management, "https://institucion.example/carreras"]
    except Exception as e:
        logger.error("Error en offer_row: %s", e)
        return False, "No se pudo preparar la fila ficticia", []


def workbook(path: Path, rows: list[list[str]], reviewed: list[list[str]] | None = None, shared: bool = False, formula: bool = False) -> tuple[bool, str, Path | None]:
    try:
        sheets = {"Todas las carreras": rows}
        if reviewed is not None:
            sheets["Altas verificadas"] = reviewed
        book = ET.Element("{" + S + "}workbook")
        sheet_list = ET.SubElement(book, "{" + S + "}sheets")
        relationships = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
        strings: list[str] = []
        with ZipFile(path, "w") as archive:
            for number, (name, data) in enumerate(sheets.items(), start=1):
                ET.SubElement(sheet_list, "{" + S + "}sheet", {"name": name, "sheetId": str(number), "{" + R + "}id": "r" + str(number)})
                ET.SubElement(relationships, "Relationship", {"Id": "r" + str(number), "Target": "worksheets/sheet" + str(number) + ".xml"})
                sheet = ET.Element("{" + S + "}worksheet")
                sheet_data = ET.SubElement(sheet, "{" + S + "}sheetData")
                for row_number, values in enumerate([list(HEADERS), *data], start=1):
                    row = ET.SubElement(sheet_data, "{" + S + "}row", r=str(row_number))
                    for column, value in enumerate(values):
                        if value == "":
                            continue
                        cell = ET.SubElement(row, "{" + S + "}c", r=chr(65 + column) + str(row_number), t="s" if shared else "inlineStr")
                        if formula and row_number == 2 and column == 0:
                            ET.SubElement(cell, "{" + S + "}f").text = "1+1"
                        if shared:
                            strings.append(value)
                            ET.SubElement(cell, "{" + S + "}v").text = str(len(strings) - 1)
                        else:
                            inline = ET.SubElement(cell, "{" + S + "}is")
                            ET.SubElement(inline, "{" + S + "}t").text = value
                archive.writestr("xl/worksheets/sheet" + str(number) + ".xml", ET.tostring(sheet))
            if shared:
                root = ET.Element("{" + S + "}sst")
                for value in strings:
                    item = ET.SubElement(root, "{" + S + "}si")
                    ET.SubElement(item, "{" + S + "}t").text = value
                archive.writestr("xl/sharedStrings.xml", ET.tostring(root))
            archive.writestr("xl/workbook.xml", ET.tostring(book))
            archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(relationships))
        return True, "ok", path
    except Exception as e:
        logger.error("Error en workbook: %s", e)
        return False, "No se pudo generar el libro ficticio", None


@dataclass
class TestEmbeddings:
    space: str = "test:v1:2"
    dimensions: int = 2
    count: int = 0
    fail: bool = False

    def embed(self: TestEmbeddings, texts: list[str]) -> tuple[bool, str, list[list[float]]]:
        try:
            if self.fail:
                return False, "Fallo simulado de embeddings", []
            self.count += len(texts)
            vectors = [[1.0] + [float(len(text) % 19 + index + 1) for index in range(self.dimensions - 1)] for text in texts]
            return True, "ok", vectors
        except Exception as e:
            logger.error("Error en TestEmbeddings.embed: %s", e)
            return False, "Fallo del doble de embeddings", []


@dataclass
class TestQdrantHTTP(HttpTransport):
    fail_on: str = ""
    fail_method: str = ""
    wrong_count: bool = False
    collections: dict[str, dict[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    requests: list[dict[str, Any]] = field(default_factory=list)
    query_points: list[dict[str, Any]] = field(default_factory=list)

    def request(self: TestQdrantHTTP, method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any]]:
        try:
            from urllib.parse import urlsplit

            self.requests.append({"method": method, "url": url, "body": copy.deepcopy(body)})
            if self.fail_on and self.fail_on in url and (not self.fail_method or self.fail_method == method):
                return False, "La API respondió con HTTP 503", {"http_status": 503, "body": {}}
            path = urlsplit(url).path
            result: Any = True
            if path == "/aliases" and method == "GET":
                result = {"aliases": [{"alias_name": name, "collection_name": target} for name, target in self.aliases.items()]}
            elif path == "/collections" and method == "GET":
                result = {"collections": [{"name": name} for name in self.collections]}
            elif path == "/collections/aliases" and method == "POST":
                for action in body["actions"]:
                    if set(action) != {"delete_alias"}:
                        raise ValueError("El reemplazo no debe crear alias nuevos")
                    self.aliases.pop(action["delete_alias"]["alias_name"])
            else:
                parts = path.strip("/").split("/")
                if len(parts) < 2 or parts[0] != "collections":
                    raise ValueError("Ruta HTTP no simulada")
                name = parts[1]
                if len(parts) == 2 and method == "PUT":
                    if name in self.collections or name in self.aliases:
                        return False, "HTTP 409", {"http_status": 409, "body": {}}
                    self.collections[name] = {"vectors": body["vectors"], "points": {}, "indexes": []}
                elif name not in self.collections:
                    return False, "HTTP 404", {"http_status": 404, "body": {}}
                elif len(parts) == 2 and method == "DELETE":
                    del self.collections[name]
                    self.aliases = {alias: target for alias, target in self.aliases.items() if target != name}
                elif len(parts) == 2 and method == "GET":
                    result = {"config": {"params": {"vectors": self.collections[name]["vectors"]}}}
                elif parts[2:] == ["index"] and method == "PUT":
                    self.collections[name]["indexes"].append(body["field_name"])
                elif parts[2:] == ["points"] and method == "PUT":
                    for point in body["points"]:
                        self.collections[name]["points"][point["id"]] = copy.deepcopy(point)
                elif parts[2:] == ["points", "count"]:
                    result = {"count": -1 if self.wrong_count else len(self.collections[name]["points"])}
                elif parts[2:] == ["points", "payload"]:
                    for point in self.collections[name]["points"].values():
                        point["payload"].update(body["payload"])
                elif parts[2:] == ["points", "query"]:
                    result = {"points": self.query_points}
                elif parts[2:] == ["points"] and method == "POST":
                    result = [point for point_id, point in self.collections[name]["points"].items() if point_id in body["ids"]]
                else:
                    raise ValueError("Operación HTTP no simulada")
            return True, "ok", {"http_status": 200, "body": {"status": "ok", "result": result}}
        except Exception as e:
            logger.error("Error en TestQdrantHTTP.request: %s", e)
            return False, "Fallo del doble HTTP", {}


def create_test_embeddings(settings: Settings) -> tuple[bool, str, Embedder | None]:
    try:
        return True, "ok", TestEmbeddings()
    except Exception as e:
        logger.error("Error en create_test_embeddings: %s", e)
        return False, "No se pudo crear el módulo externo ficticio", None
