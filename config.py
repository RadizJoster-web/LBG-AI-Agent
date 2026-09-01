"""Central configuration — loads .env and exposes typed constants.

Import `config` anywhere; never read os.environ directly elsewhere.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# ─────────────── Google Drive ───────────────
GOOGLE_CREDS_PATH: Path = BASE_DIR / os.getenv("GOOGLE_CREDS_PATH", "credentials/client_secret.json")
GOOGLE_TOKEN_PATH: Path = BASE_DIR / os.getenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
DRIVE_PARENT_FOLDER_ID: str = _require("DRIVE_PARENT_FOLDER_ID")
DRIVE_SCOPES: list[str] = ["https://www.googleapis.com/auth/drive.readonly"]

# ─────────────── Gemini ───────────────
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_DELAY_SECONDS: float = float(os.getenv("GEMINI_DELAY_SECONDS", "4"))

# ─────────────── Sanity ───────────────
SANITY_PROJECT_ID: str = os.getenv("SANITY_PROJECT_ID", "liftuy21").strip()
SANITY_DATASET: str = os.getenv("SANITY_DATASET", "production").strip()
SANITY_TOKEN: str = _require("SANITY_TOKEN")
SANITY_API_VERSION: str = os.getenv("SANITY_API_VERSION", "2024-01-01").strip()
SANITY_QUERY_URL: str = (
    f"https://{SANITY_PROJECT_ID}.api.sanity.io/v{SANITY_API_VERSION}"
    f"/data/query/{SANITY_DATASET}"
)
SANITY_MUTATE_URL: str = (
    f"https://{SANITY_PROJECT_ID}.api.sanity.io/v{SANITY_API_VERSION}"
    f"/data/mutate/{SANITY_DATASET}"
)

# ─────────────── Behaviour ───────────────
CREATE_MISSING_GENRES: bool = _bool("CREATE_MISSING_GENRES", True)
DRY_RUN: bool = _bool("DRY_RUN", False)
# CLAUDE.md workflow #3: language is NOT requested from Gemini — always this value.
DEFAULT_LANGUAGE: str = "Inggris"
DEFAULT_REGION_SLUG: str = "usa"

# ─────────────── Paths ───────────────
STATE_FILE: Path = BASE_DIR / "state" / "processed_files.json"
LOG_FILE: Path = BASE_DIR / "logs" / "pipeline.log"

# Google Drive direct-download URL template (user-confirmed format)
DRIVE_DOWNLOAD_URL_TEMPLATE: str = "https://drive.google.com/uc?id={file_id}&export=download"
