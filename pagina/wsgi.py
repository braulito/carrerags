"""Adaptador de arranque; no importar en las pruebas aisladas."""

from app import create_app

resultado, mensaje, app = create_app()
if not resultado or app is None:
    raise RuntimeError(mensaje)
