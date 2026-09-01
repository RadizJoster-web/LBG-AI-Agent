"""Assemble the final Sanity `game` document from all upstream pieces.

Strictly follows the "Aturan Kritis Sanity CMS" section of CLAUDE.md:
  1. fullDescription  -> array of Portable Text blocks (never a raw string)
  2. platform         -> single reference object
  3. language         -> single string
  4. genre            -> array of reference objects with _key (key name: "genre")
  5. region           -> single reference object
  6. fileSize         -> BOTH root level AND inside each downloadLinks item
  7. thumbnail = null, screenshots = []
  8. popularityScore  -> hardcoded 0
"""
from __future__ import annotations

import logging
import uuid

from slugify import slugify

import config
from clients.drive_client import DriveFile
from clients.sanity_client import SanityClient
from core.file_size_formatter import format_file_size
from core.genre_resolver import resolve_genres
from core.title_cleaner import CleanedTitle

logger = logging.getLogger("data_mapper")


def _portable_text(description: str) -> list[dict]:
    """Split on blank lines into one block per paragraph."""
    paragraphs = [p.strip() for p in description.split("\n\n") if p.strip()] or [description.strip()]
    blocks: list[dict] = []
    for para in paragraphs:
        blocks.append(
            {
                "_type": "block",
                "_key": uuid.uuid4().hex[:12],
                "style": "normal",
                "markDefs": [],
                "children": [
                    {
                        "_type": "span",
                        "_key": uuid.uuid4().hex[:12],
                        "text": para,
                        "marks": [],
                    }
                ],
            }
        )
    return blocks


def make_download_link(drive_file: DriveFile, cleaned: CleanedTitle) -> dict:
    """A single `downloadLink` item (used for create and for multi-disc patch)."""
    size_str = format_file_size(drive_file.file_size_bytes) or ""
    link = {
        "_type": "downloadLink",
        "_key": f"dl-{drive_file.file_id[:16]}",
        "sourceName": "Google Drive",
        "sourceType": "google-drive",
        "url": drive_file.download_url,
        "fileSize": size_str,  # rule 6 — also inside each item
    }
    if cleaned.disc_number:
        link["optionalLabel"] = cleaned.disc_number
    return link


def build_game_document(
    *,
    drive_file: DriveFile,
    cleaned: CleanedTitle,
    enriched: dict,
    sanity: SanityClient,
) -> tuple[dict, dict]:
    """Return (full_document, download_link_item).

    The download_link_item is returned separately so multi-disc handling can
    patch it onto an existing document instead of re-creating.
    """
    platform_slug = slugify(drive_file.platform_folder_name)
    game_label = f"{cleaned.title} [{drive_file.platform_folder_name}]"

    doc_id = slugify(f"{cleaned.title}-{platform_slug}")

    # ── references ──
    platform_ref = sanity.platforms.get(platform_slug)
    if not platform_ref:
        logger.error("%s: platform %r not in Sanity", game_label, drive_file.platform_folder_name)

    region_slug = cleaned.region_tag or config.DEFAULT_REGION_SLUG
    if cleaned.region_tag is None:
        logger.warning("%s: no region tag in filename -> defaulting to %r", game_label, region_slug)
    region_ref = sanity.regions.get(region_slug) or sanity.regions.get(config.DEFAULT_REGION_SLUG)
    if not region_ref:
        logger.error("%s: region %r not in Sanity", game_label, region_slug)

    genre_refs = resolve_genres(enriched.get("genres", []), sanity, game_label=game_label)

    # ── file size (rule 6: root + per-link) ──
    size_str = format_file_size(drive_file.file_size_bytes)

    link_item = make_download_link(drive_file, cleaned)

    doc: dict = {
        "_type": "game",
        "_id": doc_id,
        "title": cleaned.title,
        "slug": {"_type": "slug", "current": doc_id},
        "fullDescription": _portable_text(enriched["fullDescription"]),
        "developer": enriched["developer"],
        "publisher": enriched["publisher"],
        "releaseYear": enriched["releaseYear"],
        "language": config.DEFAULT_LANGUAGE,  # rule 3 — single string, not from Gemini
        "popularityScore": 0,                                             # rule 8
        "fileSize": size_str,                                             # rule 6 (root)
        "thumbnail": None,                                                # rule 7
        "screenshots": [],                                               # rule 7
        "platform": {"_type": "reference", "_ref": platform_ref} if platform_ref else None,  # rule 2
        "region": {"_type": "reference", "_ref": region_ref} if region_ref else None,        # rule 5
        "genre": genre_refs,                                              # rule 4
        "downloadLinks": [link_item],
    }
    return doc, link_item
