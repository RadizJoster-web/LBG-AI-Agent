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

_PROMPT_TEMPLATE = """Kamu adalah basis data metadata video game. Diberi judul game dan platform-nya,
kembalikan HANYA satu objek JSON valid dengan field berikut.
Jangan sertakan penjelasan, format markdown, atau pagar kode.

Skema JSON yang diminta:
{{
  "fullDescription": "string - Deskripsi game 2-3 paragraf DALAM BAHASA INDONESIA yang mencakup gameplay, cerita, dan penerimaan kritikus. WAJIB ditulis dalam Bahasa Indonesia yang natural meskipun game aslinya berbahasa Inggris. Pisahkan antar-paragraf dengan satu baris kosong.",
  "developer": "string - Nama studio pengembang utama (biarkan sesuai nama aslinya, jangan diterjemahkan).",
  "publisher": "string - Nama penerbit utama (biarkan sesuai nama aslinya, jangan diterjemahkan).",
  "releaseYear": "number - Tahun rilis asli sebagai bilangan bulat 4 digit (mis. 2005). Jika tidak diketahui, gunakan null.",
  "genres": ["string"]
}}

Untuk "genres": utamakan nama dari daftar ini: [{genre_whitelist}].
Jika tidak ada yang cocok, kembalikan satu nama genre standar yang ringkas (dalam bahasa Inggris, seperti daftar di atas).

Judul game: "{cleaned_title}"
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
