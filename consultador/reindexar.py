"""Publicar el Excel completo usando config.json: python reindexar.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

# Importar run configura las rutas de los adaptadores sin ejecutar la consulta.
from run import leer_configuracion
from carrerags_ingesta.application import process_workbook

logger = logging.getLogger(__name__)


def actualizar_catalogo(base_dir: Path) -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, mensaje, _ = leer_configuracion(base_dir)
        if not ok:
            return False, mensaje, {}
        valores = json.loads((base_dir / "config.json").read_text(encoding="utf-8-sig"))
        configuracion: dict[str, str] = {clave: valor for clave, valor in valores.items() if isinstance(valor, str)}
        ingesta = base_dir.parent / "ingesta"
        libros = sorted(ingesta.glob("*.xlsx"))
        if len(libros) != 1:
            raise ValueError("Debe haber un único Excel .xlsx en ingesta")
        return process_workbook(excel=libros[0], state_dir=ingesta / ".state",
                                report_path=ingesta / ".artifacts" / "revision_catalogo.json",
                                publish_catalog=True, values=configuracion)
    except Exception as e:
        logger.error("Error en actualizar_catalogo: %s", e)
        return False, "No se pudo actualizar el catálogo completo: " + str(e), {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    resultado, mensaje, salida = actualizar_catalogo(Path(__file__).resolve().parent)
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "salida": salida}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
