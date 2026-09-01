"""Process reviewed candidates into Sanity.

`ingest_selected()` takes the candidates the user ticked, runs Gemini enrichment
+ mapping + mutation for each, updates the dedup state, and reports progress
through a callback so any front-end (web UI, CLI) can render it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from clients.gemini_client import GeminiClient, GeminiError
from clients.sanity_client import SanityClient, SanityError
from core.data_mapper import build_game_document, make_download_link
from core.scanner import GameCandidate
from core.schema_validator import PayloadError, validate_gemini_output, validate_sanity_payload
from core.state_manager import StateManager

logger = logging.getLogger("ingest")

# progress event: (index, total, level, message)  level in {"info","ok","warn","error","done"}
ProgressFn = Callable[[int, int, str, str], None]


@dataclass
class IngestSummary:
    created: int = 0
    disc_appended: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "disc_appended": self.disc_appended,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def _noop(*_a) -> None:  # default progress sink
    pass


def _disc_sort_key(c: GameCandidate) -> tuple:
    n = 0
    if c.disc:
        digits = "".join(ch for ch in c.disc if ch.isdigit())
        n = int(digits) if digits else 0
    return (c.doc_id, n, c.drive_file.file_name)


def ingest_selected(
    candidates: list[GameCandidate],
    *,
    gemini: GeminiClient,
    sanity: SanityClient,
    state: StateManager,
    genre_whitelist: list[str],
    progress: ProgressFn = _noop,
) -> IngestSummary:
    summary = IngestSummary()
    # Disc 1 before Disc 2 so the first creates the doc and the rest append.
    ordered = sorted(candidates, key=_disc_sort_key)
    total = len(ordered)

    for i, cand in enumerate(ordered, start=1):
        label = f"{cand.title} [{cand.platform}]" + (f" — {cand.disc}" if cand.disc else "")
        progress(i, total, "info", f"Memproses: {label}")

        if not cand.selectable:
            summary.skipped += 1
            progress(i, total, "warn", f"Dilewati (status {cand.status}): {label}")
            continue

        try:
            _ingest_one(cand, gemini, sanity, state, genre_whitelist, summary, i, total, progress)
        except Exception as exc:  # noqa: BLE001 — one bad game must not stop the batch
            logger.exception("Unexpected error for %s", label)
            summary.errors.append(f"{label}: {exc}")
            summary.skipped += 1
            progress(i, total, "error", f"Gagal: {label} — {exc}")

    progress(
        total, total, "done",
        f"Selesai — {summary.created} dibuat, {summary.disc_appended} disc ditambahkan, "
        f"{summary.skipped} dilewati.",
    )
    return summary


def _ingest_one(
    cand: GameCandidate,
    gemini: GeminiClient,
    sanity: SanityClient,
    state: StateManager,
    genre_whitelist: list[str],
    summary: IngestSummary,
    i: int,
    total: int,
    progress: ProgressFn,
) -> None:
    label = f"{cand.title} [{cand.platform}]"
    df = cand.drive_file

    target_id = sanity.find_existing_game(
        slug_id=cand.doc_id, title=cand.title, platform_ref=cand.platform_ref
    )

    # ── multi-disc: append to the existing document ──
    if target_id:
        progress(i, total, "info", f"Menambahkan link disc ke dokumen: {label}")
        link_item = make_download_link(df, cand.cleaned)
        try:
            sanity.append_download_link(target_id, link_item)
        except SanityError as exc:
            raise RuntimeError(f"gagal patch downloadLinks: {exc}") from exc
        state.mark_processed(df.file_id)
        state.save()
        summary.disc_appended += 1
        progress(i, total, "ok", f"Disc ditambahkan: {label} ({cand.disc or 'link'})")
        return

    # ── new document: enrich with Gemini ──
    progress(i, total, "info", f"Meminta metadata Gemini: {label}")
    try:
        raw = gemini.enrich(cand.title, cand.platform, genre_whitelist)
    except GeminiError as exc:
        raise RuntimeError(f"Gemini gagal: {exc}") from exc
    enriched = validate_gemini_output(raw, game_label=label)

    doc, _ = build_game_document(
        drive_file=df, cleaned=cand.cleaned, enriched=enriched, sanity=sanity
    )

    try:
        validate_sanity_payload(doc)
    except PayloadError as exc:
        raise RuntimeError(f"payload tidak valid: {exc}") from exc

    progress(i, total, "info", f"Mengirim ke Sanity: {label}")
    try:
        sanity.create_if_not_exists(doc)
    except SanityError as exc:
        raise RuntimeError(f"mutasi Sanity gagal: {exc}") from exc

    sanity.register_new_game(doc["_id"])
    state.mark_processed(df.file_id)
    state.save()
    summary.created += 1
    progress(i, total, "ok", f"Dibuat: {label} → {doc['_id']}")
