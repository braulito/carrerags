"""Ejecutar desde ingesta: python run.py. La configuración se carga al arrancar."""

import json
import logging
from pathlib import Path

from carrerags_ingesta.bootstrap import execute

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    resultado, mensaje, salida = execute(Path(__file__).resolve().parent)
    #print(json.dumps({"resultado": resultado, "mensaje": mensaje, "salida": salida}, ensure_ascii=False, indent=2))
    print(json.dumps({"resultado": resultado, "mensaje": mensaje}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
