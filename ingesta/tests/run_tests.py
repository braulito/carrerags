"""Ejecutar: python -I -S ingesta/tests/run_tests.py."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks
import check_startup

logger = logging.getLogger(__name__)


def run_suite() -> tuple[bool, str, dict[str, Any]]:
    try:
        tests = [checks.check_excel, checks.check_eligibility, checks.check_updates_and_cache,
                 checks.check_memory_contract, checks.check_qdrant_contract, checks.check_pipeline_failure,
                 checks.check_processing_offline, checks.check_http_transport, checks.check_configuration_and_extension,
                 checks.check_actual_catalog, checks.check_function_contracts,
                 check_startup.check_default_startup, check_startup.check_local_embeddings,
                 check_startup.check_env_configuration_flow]
        failures: list[str] = []
        for test in tests:
            ok, message, data = test()
            print(("PASS " if ok else "FAIL ") + test.__name__ + (" " + str(data) if data else ""))
            if not ok:
                failures.append(message)
        if failures:
            return False, "; ".join(failures), {"passed": len(tests) - len(failures), "failed": len(failures)}
        return True, "ok", {"passed": len(tests), "failed": 0}
    except Exception as e:
        logger.error("Error en run_suite: %s", e)
        return False, "No se pudo ejecutar la suite", {}


if __name__ == "__main__":
    # Los fallos deliberados se registran sin ensuciar la salida habitual.
    logging.basicConfig(level=logging.CRITICAL)
    success, message, result = run_suite()
    print(message, result)
    raise SystemExit(0 if success else 1)
