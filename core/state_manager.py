"""Persistent dedup state — the set of already-processed Drive file IDs.

Stored as a JSON list at config.STATE_FILE. Written atomically (temp file +
os.replace) so a crash mid-write cannot corrupt it.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile

import config

logger = logging.getLogger("state_manager")


class StateManager:
    def __init__(self) -> None:
        self._path = config.STATE_FILE
        self._ids: set[str] = self._load()

    def _load(self) -> set[str]:
        if not self._path.exists():
            logger.info("No state file at %s — first run, treating all files as new", self._path)
            return set()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return set(data if isinstance(data, list) else data.get("processed", []))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Could not read state file (%s); starting empty", exc)
            return set()

    def is_processed(self, file_id: str) -> bool:
        return file_id in self._ids

    def mark_processed(self, file_id: str) -> None:
        self._ids.add(file_id)

    def save(self) -> None:
        if config.DRY_RUN:
            logger.info("[DRY_RUN] skipping state save (%d ids)", len(self._ids))
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(sorted(self._ids), fh, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        logger.info("State saved: %d processed file id(s)", len(self._ids))

    def __len__(self) -> int:
        return len(self._ids)
