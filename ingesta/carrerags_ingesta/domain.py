"""Reglas del catálogo; sin dependencias de proveedores ni configuración."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
HEADERS = ("Título", "Lugar donde se cursa", "Nivel", "Descripción", "Tipo de cursada", "Pública/Privada", "URL")
SCHEMA_VERSION = "1"
RULES_VERSION = "2"


@dataclass
class Offer:
    id: str
    title: str
    institution: str
    location: str
    level: str
    description: str
    management: str
    modality: str
    exams: str
    practices: str
    admission: str
    eligible: bool
    exclusion_reasons: list[str]
    pending: list[str]
    source: dict[str, Any]
    original: dict[str, str]
    text: str
    independent_entry: bool = True


@dataclass
class Constraints:
    management: str | None = None
    no_travel: bool = False
    confirmed_admission: bool = False
    modality: str | None = None
    secondary_only: bool = False


@dataclass
class Point:
    id: str
    vector: list[float]
    payload: dict[str, Any]


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


def presence_status(mode: str, aspect: str) -> tuple[bool, str, str]:
    try:
        if aspect not in {"exams", "practices"}:
            raise ValueError("Aspecto de presencialidad inválido")
        subject = r"examenes|finales|evaluaciones" if aspect == "exams" else r"practicas|residencia"
        statuses: set[str] = set()
        for clause in re.split(r"[.;()]", mode):
            for mention in re.finditer(r"(?:" + subject + r")\b(.*?)(?=examenes|finales|evaluaciones|practicas|residencia|$)", clause):
                detail = mention.group(1)
                if re.search(r"confirmar|verificar|comprobar|corroborar|segun (?:carrera|plan)|cuando corresponda|eventual|remoto o", detail):
                    continue
                if "presencial" in detail:
                    statuses.add("presencial")
                elif re.search(r"online|remot", detail):
                    statuses.add("remoto")
        if len(statuses) == 1:
            return True, "ok", statuses.pop()
        return True, "ok", "desconocido"
    except Exception as e:
        logger.error("Error en presence_status: %s", e)
        return False, "No se pudo clasificar la presencialidad", "desconocido"


def normalize_offer(cells: list[str], source: dict[str, Any]) -> tuple[bool, str, Offer | None]:
    try:
        if len(cells) != len(HEADERS) or any(not isinstance(cell, str) or not cell.strip() for cell in cells):
            raise ValueError("Se requieren las siete columnas completas")
        title, place, level, description, modality, management, url = [cell.strip() for cell in cells]
        if management not in {"Pública", "Privada"}:
            raise ValueError("Gestión no reconocida")
        from urllib.parse import urlsplit

        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            raise ValueError("URL institucional inválida")
        institution, separator, location = place.partition(" — ")
        if not separator:
            raise ValueError("No se puede separar institución y ubicación")
        ok, message, identity = normalize("|".join((title, institution, location, level)))
        if not ok:
            return False, message, None
        offer_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "carrerags:offer:" + identity))
        ok, message, normalized = normalize(" | ".join((title, level, description, modality)))
        if not ok:
            return False, message, None
        ok, message, mode = normalize(modality)
        if not ok:
            return False, message, None
        reasons: list[str] = []
        pending: list[str] = []
        alternative_distance = mode.startswith("a distancia; la universidad tambien ofrece opcion semipresencial")
        hybrid = not alternative_distance and bool(re.search(r"hibrid|semipresencial|mixta:|modalidad combinada|presencial con porcentaje|presencial o", mode))
        distance = bool(re.search(r"distancia|online|virtual|remot", mode))
        if hybrid:
            reasons.append("Clases presenciales regulares o modalidad híbrida")
        if not distance:
            reasons.append("Cursada a distancia no identificada")
        prior_degree = bool(re.search(r"\bccc\b|complementacion|ciclo para (?:profesionales|graduados)|para profesionales|profesorado para tecnicos|requiere titul\w* previa|requiere titulo (?:superior )?previo|exige titulo previo|con titulo previo", normalized))
        restricted = "acceso restringido" in normalized or "destinada a personal" in normalized
        intermediate = "titulo intermedio" in normalized
        admission = "desconocido"
        if prior_degree:
            admission = "titulo_superior_previo"
            reasons.append("Requiere estudios superiores previos")
        if restricted:
            admission = "restringido"
            reasons.append("Acceso restringido a un colectivo específico")
        if intermediate:
            reasons.append("Título intermedio sin ingreso independiente confirmado")
        if admission == "desconocido":
            pending.append("Ingreso con secundario: requisitos específicos no confirmados")
        ok, message, exams = presence_status(mode, "exams")
        if not ok:
            return False, message, None
        ok, message, practices = presence_status(mode, "practices")
        if not ok:
            return False, message, None
        uncertain = bool(re.search(r"confirmar|verificar|comprobar|corroborar|segun|cuando corresponda|eventual|final remoto o", mode))
        # '100% online' sobre cursada no acredita prácticas remotas.
        if exams == "desconocido":
            pending.append("Presencialidad de exámenes no confirmada")
        if practices == "desconocido":
            pending.append("Presencialidad de prácticas no confirmada o no aplica; sin determinar")
        if "proximamente" in normalized:
            pending.append("Apertura de la cohorte pendiente de confirmar")
        pending.append("Inscripción y vacantes actuales no confirmadas")
        if source.get("review_group") == "heredado":
            pending.append("Registro heredado sin reauditoría individual")
        if uncertain:
            pending.append("La modalidad original contiene condiciones por verificar")
        original = dict(zip(HEADERS, cells))
        text = f"Carrera: {title}. Institución: {institution}. Nivel: {level}. Descripción: {description}."
        modality_value = ("semipresencial" if not alternative_distance and "semipresencial" in mode
                          else "hibrida" if hybrid else "distancia" if distance
                          else "presencial" if re.search(r"\bpresencial\b", mode) else "desconocida")
        offer = Offer(offer_id, title, institution, location, level, description, management,
                      modality_value,
                      exams, practices, admission, not reasons, reasons, pending,
                      {**source, "url": url, "verified_at": None}, original, text, not intermediate)
        return True, "ok", offer
    except Exception as e:
        logger.error("Error en normalize_offer: %s", e)
        return False, "No se pudo normalizar la oferta: " + str(e), None


def query_filter(constraints: Constraints) -> tuple[bool, str, dict[str, Any]]:
    try:
        values: dict[str, Any] = {"active": True}
        if constraints.management is not None:
            if constraints.management not in {"Pública", "Privada"}:
                raise ValueError("Filtro de gestión inválido")
            values["management"] = constraints.management
        if constraints.modality is not None:
            if constraints.modality not in {"distancia", "hibrida", "semipresencial", "presencial", "desconocida"}:
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
