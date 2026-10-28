"""Lector XLSX de solo lectura. No evalúa fórmulas, macros ni enlaces externos."""

from __future__ import annotations

import hashlib
from io import BytesIO
import logging
import posixpath
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .domain import HEADERS

logger = logging.getLogger(__name__)
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def safe_path(path: Path, suffix: str) -> tuple[bool, str, Path | None]:
    try:
        for candidate in (path.absolute(), path.resolve()):
            if any(re.search(r"^\.env(?:\.|$)|\.env$", part, re.IGNORECASE) for part in candidate.parts):
                raise ValueError("Ruta de configuración protegida")
        resolved = path.resolve()
        if resolved.suffix.lower() != suffix:
            raise ValueError("Extensión no permitida")
        return True, "ok", resolved
    except Exception as e:
        logger.error("Error en safe_path: %s", e)
        return False, "Ruta no permitida", None


def parse_sheet(archive: ZipFile, name: str, shared: list[str]) -> tuple[bool, str, list[dict[str, Any]]]:
    try:
        root = ET.fromstring(archive.read(name))
        rows: list[dict[str, Any]] = []
        for row in root.findall("s:sheetData/s:row", NS):
            values: dict[int, str] = {}
            for cell in row.findall("s:c", NS):
                reference = cell.get("r", "")
                letters = re.fullmatch(r"([A-Z]+)[0-9]+", reference)
                if letters is None:
                    raise ValueError("Referencia de celda inválida")
                column = 0
                for letter in letters.group(1):
                    column = column * 26 + ord(letter) - ord("A") + 1
                if column > 64:
                    raise ValueError("Demasiadas columnas")
                if cell.find("s:f", NS) is not None:
                    raise ValueError("Se requieren valores; no se aceptan fórmulas")
                value = cell.findtext("s:v", default="", namespaces=NS)
                if cell.get("t") == "s":
                    value = shared[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall("s:is//s:t", NS))
                elif cell.get("t") == "e":
                    raise ValueError("Celda con error de Excel")
                values[column - 1] = value
            if values and any(value.strip() for value in values.values()):
                rows.append({"row": int(row.get("r", "0")), "cells": [values.get(i, "") for i in range(max(values) + 1)]})
        return True, "ok", rows
    except Exception as e:
        logger.error("Error en parse_sheet: %s", e)
        return False, "Hoja inválida: " + str(e), []


def read_workbook(path: Path) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, message, resolved = safe_path(path, ".xlsx")
        if not ok or resolved is None:
            return False, message, {}
        if resolved.stat().st_size > 25_000_000:
            raise ValueError("Excel mayor de 25 MB")
        source_bytes = resolved.read_bytes()
        file_hash = hashlib.sha256(source_bytes).hexdigest()
        with ZipFile(BytesIO(source_bytes)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100_000_000:
                raise ValueError("Libro descomprimido mayor de 100 MB")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.text or "" for node in item.findall(".//s:t", NS)) for item in root.findall("s:si", NS)]
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {item.get("Id"): item.get("Target", "") for item in relationships if item.get("TargetMode") != "External"}
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets: dict[str, list[dict[str, Any]]] = {}
            for sheet in workbook.findall("s:sheets/s:sheet", NS):
                name = sheet.get("name", "")
                if name not in {"Todas las carreras", "Altas verificadas"}:
                    continue
                target = targets.get(sheet.get("{" + REL + "}id"), "")
                target = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
                if not target.startswith("xl/worksheets/") or not target.endswith(".xml"):
                    raise ValueError("Referencia a hoja no permitida")
                ok, message, rows = parse_sheet(archive, target, shared)
                if not ok:
                    return False, message, {}
                if not rows or tuple(rows[0]["cells"]) != HEADERS:
                    raise ValueError("Encabezados inesperados en " + name)
                sheets[name] = rows[1:]
            main = sheets.get("Todas las carreras", [])
            if not main:
                raise ValueError("El catálogo completo está vacío o falta la hoja principal")
            return True, "ok", {"file": resolved.name, "sha256": file_hash, "rows": main,
                                 "reviewed": [row["cells"] for row in sheets.get("Altas verificadas", [])]}
    except Exception as e:
        logger.error("Error en read_workbook: %s", e)
        return False, "No se pudo leer el Excel: " + str(e), {}
