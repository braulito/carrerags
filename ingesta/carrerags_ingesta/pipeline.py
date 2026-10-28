"""Casos de uso locales y publicación con exclusión mutua entre importaciones."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, TextIO

from .catalog import prepare_catalog, read_catalog, write_json
from .contracts import Embedder, VectorStore
from .excel import safe_path
from .service import build_points

logger = logging.getLogger(__name__)


def analyze(path: Path, state_dir: Path) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, message, previous = read_catalog(state_dir / "catalog.json")
        if not ok:
            return False, message, {}
        ok, message, catalog = prepare_catalog(path, previous)
        if not ok:
            return False, message, {}
        return True, "ok", {"file": catalog["source_file"], "sha256": catalog["source_sha256"],
                             "rules_version": catalog["rules_version"], "report": catalog["report"]}
    except Exception as e:
        logger.error("Error en analyze: %s", e)
        return False, "No se pudo analizar el Excel", {}


def ingest(path: Path, state_dir: Path, embedder: Embedder, store: VectorStore) -> tuple[bool, str, dict[str, Any]]:
    lock: TextIO | None = None
    lock_path: Path | None = None
    try:
        ok, message, catalog_path = safe_path(state_dir / "catalog.json", ".json")
        if not ok or catalog_path is None:
            return False, message, {}
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = catalog_path.parent / "ingest.lock"
        lock = lock_path.open("x", encoding="utf-8")
        ok, message, previous = read_catalog(catalog_path)
        if not ok:
            return False, message, {}
        ok, message, catalog = prepare_catalog(path, previous)
        if not ok:
            return False, message, {}
        ok, message, health = store.health()
        if not ok:
            return False, message, health
        ok, message, points = build_points(catalog, embedder)
        if not ok:
            return False, message, {}
        snapshot = catalog_path.parent / "snapshots" / (uuid.uuid4().hex + ".json")
        catalog["publication"] = {"state": "prepared"}
        ok, message, archive_path = write_json(snapshot, catalog)
        if not ok:
            return False, message, {}
        ok, message, publication = store.replace(points, embedder.space, embedder.dimensions)
        if not ok:
            return False, message, {"snapshot": archive_path, "publication": publication}
        catalog["publication"] = {"state": "published", "details": publication}
        ok, message, _ = write_json(snapshot, catalog)
        if not ok:
            return False, "El índice fue publicado, pero no se pudo confirmar el historial local; reintentar la ingesta", {"snapshot": archive_path}
        ok, message, _ = write_json(catalog_path, catalog)
        if not ok:
            return False, "El índice fue publicado, pero no se pudo confirmar el catálogo local; reintentar la ingesta", {"snapshot": archive_path}
        return True, "ok", {"report": catalog["report"], "publication": publication, "snapshot": archive_path}
    except FileExistsError as e:
        logger.error("Error en ingest, bloqueo existente: %s", e)
        return False, "Hay otra ingesta en curso o un bloqueo pendiente de revisar", {}
    except Exception as e:
        logger.error("Error en ingest: %s", e)
        return False, "No se pudo completar la ingesta", {}
    finally:
        if lock is not None:
            try:
                lock.close()
                if lock_path is not None:
                    lock_path.unlink(missing_ok=True)
            except Exception as e:
                logger.error("Error en ingest al liberar el bloqueo: %s", e)
                return False, "No se pudo liberar el bloqueo local; comprobar el estado de publicación", {}
