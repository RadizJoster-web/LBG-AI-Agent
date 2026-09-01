"""Regex-based file name -> clean game title + region tag + disc number.

Example:
    "Tekken 5 (USA) [PS2].iso" -> CleanedTitle(title="Tekken 5", region_tag="USA", disc_number=None)
    "Final Fantasy VII (Disc 1) (USA).bin" -> title="Final Fantasy VII", region="USA", disc="Disc 1"
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Known ROM / archive extensions (lower-case, no dot)
_EXTENSIONS = {
    "iso", "bin", "cue", "img", "mdf", "mds", "nrg",
    "cso", "chd", "pbp", "pkg", "rvz",
    "zip", "7z", "rar", "gz", "tar", "001",
}

# Region tags -> canonical Sanity-friendly slug
_REGION_MAP: dict[str, str] = {
    "usa": "usa", "us": "usa", "u": "usa", "ntsc-u": "usa", "america": "usa",
    "europe": "europe", "eur": "europe", "e": "europe", "pal": "europe",
    "japan": "japan", "jpn": "japan", "jap": "japan", "j": "japan", "ntsc-j": "japan",
    "world": "world", "w": "world",
    "asia": "asia",
    "australia": "australia", "aus": "australia",
    "korea": "korea", "k": "korea",
    "china": "china",
    "germany": "germany", "france": "france", "spain": "spain", "italy": "italy",
}

# Language-only tags to strip (not regions) e.g. (En,Fr,De)
_LANG_TOKEN = re.compile(r"^(?:[a-z]{2})(?:,[a-z]{2})+$", re.IGNORECASE)

_BRACKET_GROUP = re.compile(r"[\(\[\{]([^\(\)\[\]\{\}]*)[\)\]\}]")
_DISC_RE = re.compile(r"\b(?:disc|disk|cd|dvd)\s*[-_ ]?\s*(\d+)\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class CleanedTitle:
    title: str
    region_tag: str | None      # canonical slug, e.g. "usa"; None if not found
    disc_number: str | None     # e.g. "Disc 1"; None for single-disc


def _strip_extension(name: str) -> str:
    # Strip potentially chained extensions like ".tar.gz" or "game.iso.zip"
    parts = name.split(".")
    while len(parts) > 1 and parts[-1].lower() in _EXTENSIONS:
        parts.pop()
    return ".".join(parts)


def clean_title(file_name: str) -> CleanedTitle:
    name = _strip_extension(file_name.strip())

    region_tag: str | None = None
    disc_number: str | None = None

    def _replace(match: re.Match[str]) -> str:
        nonlocal region_tag, disc_number
        content = match.group(1).strip()
        low = content.lower()

        disc_match = _DISC_RE.search(content)
        if disc_match:
            disc_number = f"Disc {int(disc_match.group(1))}"
            return " "

        if low in _REGION_MAP:
            # keep the first region encountered
            if region_tag is None:
                region_tag = _REGION_MAP[low]
            return " "

        if _LANG_TOKEN.match(low) or low in {"en", "multi", "multi-language", "ntsc", "pal"}:
            return " "

        # Unknown bracket group (revision tags, dumper tags, etc.) -> drop
        return " "

    cleaned = _BRACKET_GROUP.sub(_replace, name)

    # Standalone "Disc 1" without brackets
    disc_inline = _DISC_RE.search(cleaned)
    if disc_inline and disc_number is None:
        disc_number = f"Disc {int(disc_inline.group(1))}"
    cleaned = _DISC_RE.sub(" ", cleaned)

    cleaned = cleaned.replace("_", " ")
    cleaned = _WS_RE.sub(" ", cleaned).strip(" -–—")

    return CleanedTitle(title=cleaned, region_tag=region_tag, disc_number=disc_number)
