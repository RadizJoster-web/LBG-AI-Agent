"""Gemini genre strings -> Sanity genre reference objects.

Behaviour on a genre missing from the Sanity whitelist is controlled by
config.CREATE_MISSING_GENRES:
  True  -> create the genre in Sanity, then reference it (user-confirmed default)
  False -> log a warning and discard it
"""
from __future__ import annotations

import logging
import uuid

from slugify import slugify

import config
from clients.sanity_client import SanityClient, SanityError

logger = logging.getLogger("genre_resolver")


def resolve_genres(
    genre_names: list[str], sanity: SanityClient, *, game_label: str
) -> list[dict]:
    refs: list[dict] = []
    seen_ids: set[str] = set()

    for name in genre_names:
        slug = slugify(name)
        if not slug:
            continue

        ref_id = sanity.genres.get(slug)

        if ref_id is None and config.CREATE_MISSING_GENRES:
            try:
                ref_id = sanity.create_genre(name)
            except SanityError as exc:
                logger.error("%s: could not create genre %r: %s", game_label, name, exc)
                continue

        if ref_id is None:
            logger.warning("%s: unknown genre %r -> discarded", game_label, name)
            continue

        if ref_id in seen_ids:
            continue
        seen_ids.add(ref_id)

        refs.append(
            {
                "_type": "reference",
                "_ref": ref_id,
                "_key": uuid.uuid4().hex[:12],
            }
        )

    return refs
