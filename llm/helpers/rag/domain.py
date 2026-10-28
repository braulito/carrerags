"""Primitivas de consulta trasladadas de ingesta para independizar llm."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
HEADERS = ("Título", "Lugar donde se cursa", "Nivel", "Descripción", "Tipo de cursada", "Pública/Privada", "URL")

@dataclass
class Constraints:
    institution: str | None = None
    location: str | None = None
    level: str | None = None
    management: str | None = None
    no_travel: bool = False
    confirmed_admission: bool = False
    modality: str | None = None
    secondary_only: bool = False

@dataclass
class Hit:
    id: str
    score: float
    payload: dict[str, Any]

def normalize(value: str) -> tuple[bool, str, str]:
    try:
        text = unicodedata.normalize("NFKD", value)
        text = "".join(char for char in text if not unicodedata.combining(char))
        return True, "ok", " ".join(text.casefold().split())
    except Exception as e:
        logger.error("Error en normalize: %s", e)
        return False, "No se pudo normalizar el texto", ""

def digest(value: Any) -> tuple[bool, str, str]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return True, "ok", hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except Exception as e:
        logger.error("Error en digest: %s", e)
        return False, "No se pudo calcular la huella", ""

def query_filter(constraints: Constraints) -> tuple[bool, str, dict[str, Any]]:
    try:
        values: dict[str, Any] = {"active": True}
        for key in ("institution", "location", "level"):
            value = getattr(constraints, key)
            if value is not None:
                values[key] = value
        if constraints.management is not None:
            if constraints.management not in {"Pública", "Privada"}:
                raise ValueError("Filtro de gestión inválido")
            values["management"] = constraints.management
        if constraints.modality is not None:
            if not isinstance(constraints.modality, str) or not constraints.modality.strip():
                raise ValueError("Filtro de modalidad inválido")
            values["modality"] = constraints.modality
        if constraints.confirmed_admission:
            values["admission"] = "secundario_confirmado"
        if constraints.no_travel:
            if constraints.modality not in {None, "distancia"}:
                raise ValueError("Sin viajar es incompatible con una modalidad presencial o híbrida")
            values.update({"modality": "distancia", "exams": "remoto"})
        if constraints.secondary_only:
            values["independent_entry"] = True
        filters: dict[str, Any] = {"must": [{"key": key, "match": {"value": value}} for key, value in values.items()]}
        if constraints.no_travel:
            filters["must"].append({"key": "practices", "match": {"any": ["remoto", "no_aplica"]}})
        if constraints.secondary_only:
            filters["must_not"] = [{"key": "admission", "match": {"any": ["titulo_superior_previo", "restringido"]}}]
        return True, "ok", filters
    except Exception as e:
        logger.error("Error en query_filter: %s", e)
        return False, "Filtros de consulta inválidos: " + str(e), {}

def matches(payload: dict[str, Any], constraints: Constraints) -> tuple[bool, str, bool]:
    try:
        ok, message, filters = query_filter(constraints)
        if not ok:
            return False, message, False
        accepted = True
        for condition in filters["must"]:
            rule = condition["match"]
            value = payload.get(condition["key"])
            accepted = accepted and (value in rule["any"] if "any" in rule else value == rule["value"])
        for condition in filters.get("must_not", []):
            accepted = accepted and payload.get(condition["key"]) not in condition["match"]["any"]
        return True, "ok", accepted
    except Exception as e:
        logger.error("Error en matches: %s", e)
        return False, "No se pudieron comprobar las restricciones", False
