"""Catálogo canónico, revisión de reemplazos y persistencia local independiente del índice."""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain import RULES_VERSION, SCHEMA_VERSION, digest, normalize_offer
from .excel import read_workbook, safe_path

logger = logging.getLogger(__name__)


def read_catalog(path: Path) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, message, resolved = safe_path(path, ".json")
        if not ok or resolved is None:
            return False, message, {}
        if not resolved.exists():
            return True, "ok", {"schema_version": SCHEMA_VERSION, "offers": {}}
        content = json.loads(resolved.read_text(encoding="utf-8"))
        if content.get("schema_version") != SCHEMA_VERSION or not isinstance(content.get("offers"), dict):
            raise ValueError("Versión o estructura del catálogo incompatible")
        for offer_id, entry in content["offers"].items():
            if entry.get("offer", {}).get("id") != offer_id or not isinstance(entry.get("active"), bool):
                raise ValueError("Registro de catálogo inválido")
        return True, "ok", content
    except Exception as e:
        logger.error("Error en read_catalog: %s", e)
        return False, "No se pudo leer el catálogo anterior; se cancela la actualización", {}


def write_json(path: Path, content: dict[str, Any]) -> tuple[bool, str, str]:
    temporary: str | None = None
    try:
        ok, message, resolved = safe_path(path, ".json")
        if not ok or resolved is None:
            return False, message, ""
        serialized = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=resolved.parent, suffix=".json", delete=False) as handle:
            temporary = handle.name
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, resolved)
        temporary = None
        return True, "ok", str(resolved)
    except Exception as e:
        logger.error("Error en write_json: %s", e)
        return False, "No se pudo guardar el archivo JSON", ""
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except Exception as e:
                logger.error("Error en write_json al limpiar el temporal: %s", e)
                return False, "No se pudo limpiar el archivo temporal", ""


def prepare_catalog(path: Path, previous: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, message, workbook = read_workbook(path)
        if not ok:
            return False, message, {}
        timestamp = datetime.now(timezone.utc).isoformat()
        offers: dict[str, Any] = {}
        changes: dict[str, list[str]] = {"added": [], "modified": [], "unchanged": [], "retired": []}
        reviewed = {tuple(cells) for cells in workbook["reviewed"]}
        main_rows = {tuple(row["cells"]) for row in workbook["rows"]}
        if not reviewed.issubset(main_rows):
            raise ValueError("Altas verificadas contiene ofertas ausentes o distintas de la hoja principal")
        for row in workbook["rows"]:
            review_group = "alta_revision" if tuple(row["cells"]) in reviewed else "heredado"
            source = {"file": workbook["file"], "sha256": workbook["sha256"], "sheet": "Todas las carreras",
                      "row": row["row"], "review_group": review_group}
            ok, message, offer = normalize_offer(row["cells"], source)
            if not ok or offer is None:
                return False, "Fila " + str(row["row"]) + ": " + message, {}
            if offer.id in offers:
                raise ValueError("Oferta duplicada en la fila " + str(row["row"]))
            data = asdict(offer)
            content = {key: value for key, value in data.items() if key != "source"}
            ok, message, content_hash = digest({"offer": content, "rules": RULES_VERSION})
            if not ok:
                return False, message, {}
            old = previous.get("offers", {}).get(offer.id, {})
            kind = "added" if not old or not old.get("active") else "unchanged" if old.get("content_hash") == content_hash else "modified"
            changes[kind].append(offer.id)
            offers[offer.id] = {"offer": data, "active": True, "content_hash": content_hash,
                                "first_seen": old.get("first_seen", timestamp), "last_seen": timestamp,
                                "vector_cache": copy.deepcopy(old.get("vector_cache", {}))}
        for offer_id, old in previous.get("offers", {}).items():
            if offer_id not in offers:
                retired = copy.deepcopy(old)
                if old.get("active"):
                    changes["retired"].append(offer_id)
                    retired["retired_at"] = timestamp
                retired["active"] = False
                retired["vector_cache"] = {}
                offers[offer_id] = retired
        active = [entry["offer"] for entry in offers.values() if entry["active"]]
        eligible = [offer for offer in active if offer["eligible"]]
        exclusions = [{"id": offer["id"], "title": offer["title"], "institution": offer["institution"],
                       "row": offer["source"]["row"], "reasons": offer["exclusion_reasons"]} for offer in active if not offer["eligible"]]
        report = {"rows": len(active), "eligible": len(eligible), "excluded": len(exclusions),
                  "management": dict(Counter(offer["management"] for offer in eligible)),
                  "review_groups": dict(Counter(offer["source"]["review_group"] for offer in active)),
                  "exclusion_reasons": dict(Counter(reason for offer in active for reason in offer["exclusion_reasons"])),
                  "no_travel_confirmed": sum(offer["exams"] == "remoto" and offer["practices"] in {"remoto", "no_aplica"} for offer in eligible),
                  "changes": {kind: len(ids) for kind, ids in changes.items()}, "change_ids": changes,
                  "exclusions": exclusions}
        return True, "ok", {"schema_version": SCHEMA_VERSION, "rules_version": RULES_VERSION,
                             "imported_at": timestamp, "source_file": workbook["file"], "source_sha256": workbook["sha256"],
                             "offers": offers, "report": report}
    except Exception as e:
        logger.error("Error en prepare_catalog: %s", e)
        return False, "No se pudo preparar el catálogo: " + str(e), {}
