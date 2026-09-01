"""Sanity CMS client — GROQ reference lookups + mutations.

- fetch_references(): builds {slug -> _id} caches for genre / platform / region
- document_exists(_id)
- create_if_not_exists(doc)
- append_download_link(doc_id, link)   (multi-disc)
- create_genre(title) -> _id           (dynamic whitelist growth)
"""
from __future__ import annotations

import logging

import requests
from slugify import slugify

import config

logger = logging.getLogger("sanity_client")

_TIMEOUT = 30


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
        # {slug -> _id}
        self.genres: dict[str, str] = {}
        self.platforms: dict[str, str] = {}
        self.regions: dict[str, str] = {}

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
        specs = (
            ("genre", self.genres),
            ("platform", self.platforms),
            ("region", self.regions),
        )
        for doc_type, cache in specs:
            rows = self._query(
                f'*[_type == "{doc_type}"]{{ _id, "slug": slug.current, title }}'
            )
            for row in rows:
                slug = row.get("slug") or slugify(row.get("title", ""))
                if slug and row.get("_id"):
                    cache[slug] = row["_id"]
            logger.info("Loaded %d %s reference(s)", len(cache), doc_type)

    def document_exists(self, doc_id: str) -> bool:
        rows = self._query(f'*[_id == "{doc_id}"][0]{{ _id }}')
        if isinstance(rows, dict):
            return bool(rows.get("_id"))
        return bool(rows)

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

    def create_genre(self, title: str) -> str:
        slug = slugify(title)
        doc_id = f"genre-{slug}"
        doc = {
            "_type": "genre",
            "_id": doc_id,
            "title": title.strip().title(),
            "slug": {"_type": "slug", "current": slug},
        }
        self._mutate([{"createIfNotExists": doc}])
        self.genres[slug] = doc_id
        logger.info("Created new Sanity genre: %s (%s)", title, doc_id)
        return doc_id
