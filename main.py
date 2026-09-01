"""Entry point — orchestrates the Drive -> Gemini -> Sanity ingestion pipeline.

Run:  python main.py
"""
from __future__ import annotations

import logging

import config
from clients.drive_client import DriveClient, DriveFile
from clients.gemini_client import GeminiClient, GeminiError
from clients.sanity_client import SanityClient, SanityError
from core.data_mapper import build_game_document
from core.schema_validator import (
    PayloadError,
    validate_gemini_output,
    validate_sanity_payload,
)
from core.state_manager import StateManager
from core.title_cleaner import clean_title
from logging_config import setup_logging

logger = logging.getLogger("main")


class RunStats:
    def __init__(self) -> None:
        self.created = 0
        self.disc_appended = 0
        self.skipped_errors = 0
        self.skipped_existing = 0


def _process_file(
    drive_file: DriveFile,
    *,
    drive_new_ids_this_run: set[str],
    gemini: GeminiClient,
    sanity: SanityClient,
    genre_whitelist: list[str],
    stats: RunStats,
) -> bool:
    """Return True if the file_id should be marked processed."""
    label = f"{drive_file.file_name} ({drive_file.platform_folder_name})"
    cleaned = clean_title(drive_file.file_name)
    if not cleaned.title:
        logger.error("%s: title empty after cleaning — skipping", label)
        stats.skipped_errors += 1
        return False

    game_label = f"{cleaned.title} [{drive_file.platform_folder_name}]"

    # ── Gemini enrichment ──
    try:
        raw = gemini.enrich(cleaned.title, drive_file.platform_folder_name, genre_whitelist)
    except GeminiError as exc:
        logger.error("%s: Gemini failed (%s) — skipping", game_label, exc)
        stats.skipped_errors += 1
        return False
    enriched = validate_gemini_output(raw, game_label=game_label)

    # ── build payload ──
    doc, link_item = build_game_document(
        drive_file=drive_file, cleaned=cleaned, enriched=enriched, sanity=sanity
    )

    # ── multi-disc: append link to existing document instead of recreating ──
    doc_id = doc["_id"]
    already_present = doc_id in drive_new_ids_this_run
    if not already_present:
        try:
            already_present = sanity.document_exists(doc_id)
        except SanityError as exc:
            logger.error("%s: existence check failed (%s) — skipping", game_label, exc)
            stats.skipped_errors += 1
            return False

    if already_present:
        try:
            sanity.append_download_link(doc_id, link_item)
        except SanityError as exc:
            logger.error("%s: could not append disc link (%s) — skipping", game_label, exc)
            stats.skipped_errors += 1
            return False
        logger.info("%s: appended download link to existing document %s", game_label, doc_id)
        stats.disc_appended += 1
        drive_new_ids_this_run.add(doc_id)
        return True

    # ── validate + createIfNotExists ──
    try:
        validate_sanity_payload(doc)
    except PayloadError as exc:
        logger.error("%s: invalid payload (%s) — skipping", game_label, exc)
        stats.skipped_errors += 1
        return False

    try:
        sanity.create_if_not_exists(doc)
    except SanityError as exc:
        logger.error("%s: Sanity mutation failed (%s) — skipping", game_label, exc)
        stats.skipped_errors += 1
        return False

    logger.info("%s: created Sanity document %s", game_label, doc_id)
    stats.created += 1
    drive_new_ids_this_run.add(doc_id)
    return True


def run() -> None:
    setup_logging()
    logger.info("=== LBG ingestion pipeline start (dataset=%s, dry_run=%s) ===",
                config.SANITY_DATASET, config.DRY_RUN)

    state = StateManager()
    sanity = SanityClient()
    sanity.fetch_references()
    genre_whitelist = sorted({slug.replace("-", " ").title() for slug in sanity.genres})

    drive = DriveClient()
    all_files = drive.scan_all()

    new_files = [f for f in all_files if not state.is_processed(f.file_id)]
    logger.info("Scan complete: %d file(s) total, %d new", len(all_files), len(new_files))
    if not new_files:
        logger.info("Nothing to do.")
        logger.info("=== pipeline finished ===")
        return

    # Multi-disc: process in name order so "Disc 1" lands before "Disc 2"
    new_files.sort(key=lambda f: (f.platform_folder_name, f.file_name))

    gemini = GeminiClient()
    stats = RunStats()
    doc_ids_this_run: set[str] = set()

    for drive_file in new_files:
        try:
            ok = _process_file(
                drive_file,
                drive_new_ids_this_run=doc_ids_this_run,
                gemini=gemini,
                sanity=sanity,
                genre_whitelist=genre_whitelist,
                stats=stats,
            )
        except Exception:  # noqa: BLE001 — never let one file kill the run
            logger.exception("%s: unexpected error — skipping", drive_file.file_name)
            stats.skipped_errors += 1
            ok = False

        if ok:
            state.mark_processed(drive_file.file_id)
            state.save()  # persist incrementally so a crash keeps progress

    logger.info(
        "Summary — created: %d, disc links appended: %d, skipped (errors): %d, "
        "total in state: %d",
        stats.created, stats.disc_appended, stats.skipped_errors, len(state),
    )
    logger.info("=== pipeline finished ===")


if __name__ == "__main__":
    run()
