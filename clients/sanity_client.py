"""Sanity CMS client — GROQ reference lookups + mutations.

- fetch_references(): builds {lookup key -> _id} caches for genre / platform / region.
  genre & platform key on slug + slugify(name); region keys on code + name + aliases
  (the real region schema has no slug field).
- document_exists(_id)
- create_if_not_exists(doc)
- append_download_link(doc_id, link)   (multi-disc)
- create_genre(name) -> _id            (dynamic whitelist growth; schema field is `name`)
"""
from __future__ import annotations

import logging

import requests
from slugify import slugify

import config

logger = logging.getLogger("sanity_client")

_TIMEOUT = 30

# Filename region tags (as normalised by title_cleaner) grouped by the Sanity
# region `code`. Every alias in a group resolves to that region's _id.
_REGION_ALIAS_GROUPS: dict[str, set[str]] = {
    "usa": {"usa", "us", "u", "ntsc-u", "america", "amerika"},
    "eur": {"eur", "europe", "europa", "pal", "e"},
    "jpn": {"jpn", "japan", "jepang", "jp", "j", "ntsc-j"},
    "uk": {"uk", "inggris", "england", "gb", "united-kingdom"},
    "aus": {"aus", "australia"},
    "kor": {"kor", "korea", "k"},
    "asia": {"asia"},
    "world": {"world", "w", "dunia"},
}


class SanityError(RuntimeError):
    pass


class SanityClient:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.SANITY_TOKEN}",
                "Content-Type": "application/json",
            }
        )
        # {lookup key -> _id}
        self.genres: dict[str, str] = {}
        self.platforms: dict[str, str] = {}
        self.regions: dict[str, str] = {}
        # human-readable genre names, for the Gemini whitelist prompt
        self.genre_names: list[str] = []
        # existing `game` docs, for duplicate detection
        self._existing_ids: set[str] = set()
        self._existing_by_title_platform: dict[tuple[str, str], str] = {}

    # ─────────────── queries ───────────────
    def _query(self, groq: str) -> list[dict]:
        try:
            resp = self._session.get(
                config.SANITY_QUERY_URL, params={"query": groq}, timeout=_TIMEOUT
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SanityError(f"GROQ query failed: {exc}") from exc
        return resp.json().get("result", []) or []

    def fetch_references(self) -> None:
        self._fetch_named("genre", self.genres, collect_names=self.genre_names)
        self._fetch_named("platform", self.platforms)
        self._fetch_regions()

    def _fetch_named(
        self, doc_type: str, cache: dict[str, str], *, collect_names: list | None = None
    ) -> None:
        """genre / platform: keyed by slug.current and by slugify(name/title)."""
        rows = self._query(
            f'*[_type == "{doc_type}"]{{ _id, "slug": slug.current, name, title }}'
        )
        for row in rows:
            _id = row.get("_id")
            if not _id:
                continue
            label = row.get("name") or row.get("title") or ""
            keys = {k for k in (row.get("slug"), slugify(label)) if k}
            if not keys:
                logger.warning("%s %s has no slug/name — skipped", doc_type, _id)
                continue
            for key in keys:
                cache[key] = _id
            if collect_names is not None and label:
                collect_names.append(label)
        logger.info(
            "Loaded %d %s(s) (%d lookup keys)",
            len({v for v in cache.values()}),
            doc_type,
            len(cache),
        )

    def _fetch_regions(self) -> None:
        """region: no slug in schema — keyed by `code`, `name`, and known aliases."""
        rows = self._query('*[_type == "region"]{ _id, code, name, "slug": slug.current }')
        for row in rows:
            _id = row.get("_id")
            if not _id:
                continue
            code = (row.get("code") or "").strip().lower()
            name_slug = slugify(row.get("name") or "")
            keys: set[str] = {k for k in (code, name_slug, row.get("slug")) if k}
            # expand with the alias group this region belongs to
            for group_code, aliases in _REGION_ALIAS_GROUPS.items():
                if code == group_code or code in aliases or name_slug in aliases:
                    keys |= aliases
                    keys.add(group_code)
            for key in keys:
                self.regions[key] = _id
        logger.info(
            "Loaded %d region(s) (%d lookup keys)",
            len({v for v in self.regions.values()}),
            len(self.regions),
        )

    def document_exists(self, doc_id: str) -> bool:
        rows = self._query(f'*[_id == "{doc_id}"][0]{{ _id }}')
        if isinstance(rows, dict):
            return bool(rows.get("_id"))
        return bool(rows)

    # ─────────────── existing-game index (duplicate detection) ───────────────
    def fetch_existing_games(self) -> None:
        """Index every existing `game` doc by _id and by (title-slug, platform-ref).

        Studio-created games use random UUID _ids, so matching the pipeline's slug
        _id alone would miss them and create duplicates.
        """
        rows = self._query(
            '*[_type == "game"]{ _id, title, "platform": platform._ref }'
        )
        self._existing_ids = set()
        self._existing_by_title_platform = {}
        for row in rows:
            _id = row.get("_id")
            if not _id:
                continue
            self._existing_ids.add(_id)
            title = row.get("title") or ""
            platform_ref = row.get("platform") or ""
            if title and platform_ref:
                self._existing_by_title_platform[(slugify(title), platform_ref)] = _id
        logger.info("Indexed %d existing game document(s)", len(self._existing_ids))

    def find_existing_game(
        self, *, slug_id: str, title: str, platform_ref: str | None
    ) -> str | None:
        """Return the _id of a matching existing game, or None."""
        if slug_id in self._existing_ids:
            return slug_id
        if platform_ref:
            key = (slugify(title), platform_ref)
            return self._existing_by_title_platform.get(key)
        return None

    def register_new_game(self, doc_id: str) -> None:
        """Record a just-created game so a later disc in the same run matches it."""
        self._existing_ids.add(doc_id)

    # ─────────────── mutations ───────────────
    def _mutate(self, mutations: list[dict], *, return_ids: bool = False) -> dict:
        if config.DRY_RUN:
            logger.info("[DRY_RUN] would send mutations: %s", mutations)
            return {}
        params = {"returnIds": "true"} if return_ids else {}
        try:
            resp = self._session.post(
                config.SANITY_MUTATE_URL,
                params=params,
                json={"mutations": mutations},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise SanityError(f"Mutation request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise SanityError(f"Mutation HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def create_if_not_exists(self, doc: dict) -> dict:
        return self._mutate([{"createIfNotExists": doc}])

    def append_download_link(self, doc_id: str, link: dict) -> dict:
        patch = {
            "patch": {
                "id": doc_id,
                "setIfMissing": {"downloadLinks": []},
                "insert": {"after": "downloadLinks[-1]", "items": [link]},
            }
        }
        return self._mutate([patch])

    def create_genre(self, name: str) -> str:
        slug = slugify(name)
        doc_id = f"genre-{slug}"
        doc = {
            "_type": "genre",
            "_id": doc_id,
            "name": name.strip().title(),  # real schema field is `name`, not `title`
            "slug": {"_type": "slug", "current": slug},
        }
        self._mutate([{"createIfNotExists": doc}])
        self.genres[slug] = doc_id
        self.genre_names.append(name.strip().title())
        logger.info("Created new Sanity genre: %s (%s)", name, doc_id)
        return doc_id
