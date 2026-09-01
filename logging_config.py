"""Logging setup — rotating file handler + stdout stream."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOG_FILE

_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Windows consoles default to cp1252 — make sure arrows / ✓ / ✗ don't crash output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # Quieten noisy third-party libraries
    for noisy in ("googleapiclient", "google", "urllib3", "google_auth_httplib2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
