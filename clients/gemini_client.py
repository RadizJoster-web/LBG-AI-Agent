"""Gemini API wrapper — enrich a cleaned game title into structured JSON.

Model: config.GEMINI_MODEL (default gemini-3.5-flash-lite)
Enforces JSON output via response_mime_type = "application/json".
Rate-limited: sleeps config.GEMINI_DELAY_SECONDS between calls.
"""
from __future__ import annotations

import json
import logging
import time

import google.generativeai as genai

import config

logger = logging.getLogger("gemini_client")

_PROMPT_TEMPLATE = """You are a video game metadata database. Given a game title and its platform,
return ONLY a valid JSON object with the following fields.
Do not include any explanation, markdown formatting, or code fences.

Required JSON schema:
{{
  "fullDescription": "string - A 2-3 paragraph description of the game covering gameplay, story, and critical reception.",
  "developer": "string - The primary developer studio name.",
  "publisher": "string - The primary publisher name.",
  "releaseYear": "number - The original release year as a 4-digit integer (e.g. 2005). If unknown, use null.",
  "language": "string - The primary language of this game version (e.g. 'English', 'Japanese', 'Multi-Language'). If unknown, default to 'English'.",
  "genres": ["string"]
}}

For "genres": prefer names from this list: [{genre_whitelist}].
If none fit, you may return a concise standard genre name.

Game title: "{cleaned_title}"
Platform: "{platform_name}"
"""


class GeminiError(RuntimeError):
    pass


class GeminiClient:
    def __init__(self) -> None:
        genai.configure(api_key=config.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(
            config.GEMINI_MODEL,
            generation_config={"response_mime_type": "application/json"},
        )
        self._last_call: float = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        wait = config.GEMINI_DELAY_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)

    def enrich(self, cleaned_title: str, platform_name: str, genre_whitelist: list[str]) -> dict:
        prompt = _PROMPT_TEMPLATE.format(
            genre_whitelist=", ".join(genre_whitelist) or "Action, Adventure, RPG",
            cleaned_title=cleaned_title,
            platform_name=platform_name,
        )

        self._throttle()
        try:
            response = self._model.generate_content(prompt)
        except Exception as exc:  # google.api_core.exceptions.* and friends
            raise GeminiError(f"Gemini request failed: {exc}") from exc
        finally:
            self._last_call = time.monotonic()

        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise GeminiError("Gemini returned an empty response")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Gemini returned unparseable JSON for %r: %s", cleaned_title, text[:500])
            raise GeminiError(f"Gemini JSON parse error: {exc}") from exc
