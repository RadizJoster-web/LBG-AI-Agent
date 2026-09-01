"""Validation for Gemini output and the assembled Sanity payload.

Gemini validation is lenient: apply fallbacks, never raise.
Sanity validation is strict: raise PayloadError for fatal problems.
"""
from __future__ import annotations

import datetime as _dt
import logging

logger = logging.getLogger("schema_validator")

MAX_DESCRIPTION_CHARS = 5000


class PayloadError(ValueError):
    """Raised when an assembled Sanity payload is missing something fatal."""


def validate_gemini_output(data: dict, *, game_label: str) -> dict:
    """Return a normalised dict with guaranteed field types/fallbacks."""
    if not isinstance(data, dict):
        logger.error("Gemini output for %s is not an object; using full fallback", game_label)
        data = {}

    out: dict = {}

    desc = data.get("fullDescription")
    if isinstance(desc, str) and desc.strip():
        out["fullDescription"] = desc.strip()[:MAX_DESCRIPTION_CHARS]
    else:
        logger.warning("%s: missing fullDescription -> fallback", game_label)
        out["fullDescription"] = "No description available."

    for field in ("developer", "publisher"):
        val = data.get(field)
        out[field] = val.strip() if isinstance(val, str) and val.strip() else "Unknown"

    year = data.get("releaseYear")
    current_year = _dt.date.today().year
    if isinstance(year, bool):
        year = None
    if isinstance(year, (int, float)) and 1970 <= int(year) <= current_year + 1:
        out["releaseYear"] = int(year)
    else:
        if year not in (None, "", "null"):
            logger.warning("%s: invalid releaseYear %r -> null", game_label, year)
        out["releaseYear"] = None

    lang = data.get("language")
    out["language"] = lang.strip() if isinstance(lang, str) and lang.strip() else "English"

    genres = data.get("genres")
    if isinstance(genres, list):
        cleaned = [g.strip() for g in genres if isinstance(g, str) and g.strip()]
    else:
        cleaned = []
    if not cleaned:
        logger.warning("%s: no usable genres from Gemini -> ['Action']", game_label)
        cleaned = ["Action"]
    out["genres"] = cleaned

    return out


def validate_sanity_payload(doc: dict) -> None:
    """Raise PayloadError on any fatal issue."""
    if not doc.get("_id"):
        raise PayloadError("missing _id")

    platform = doc.get("platform") or {}
    if not platform.get("_ref"):
        raise PayloadError("platform reference not resolved")

    region = doc.get("region") or {}
    if not region.get("_ref"):
        raise PayloadError("region reference not resolved")

    if not doc.get("fileSize"):
        raise PayloadError("root-level fileSize missing")

    links = doc.get("downloadLinks") or []
    if not links or not all(l.get("url") for l in links):
        raise PayloadError("downloadLinks missing or has entry without url")

    if not all(l.get("fileSize") for l in links):
        raise PayloadError("a downloadLink entry is missing fileSize")

    if not doc.get("language"):
        logger.warning("%s: language empty -> 'English'", doc.get("_id"))
        doc["language"] = "English"

    if not doc.get("genre"):
        logger.warning("%s: no genres resolved; proceeding with empty genre array", doc.get("_id"))
