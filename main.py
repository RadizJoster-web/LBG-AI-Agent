"""Headless CLI for the LBG ingestion pipeline.

For interactive review use the web UI instead:  python app.py

    python main.py                 # scan + print what WOULD be uploaded, then stop
    python main.py --today         # upload games added to Drive today (asks first)
    python main.py --all           # upload every new/disc candidate (asks first)
    python main.py --today --yes   # ...without the confirmation prompt
"""
from __future__ import annotations

import argparse
import logging

import config
from clients.drive_client import DriveClient
from clients.gemini_client import GeminiClient
from clients.sanity_client import SanityClient
from core.ingest import ingest_selected
from core.scanner import GameCandidate, build_candidates
from core.state_manager import StateManager
from logging_config import setup_logging

logger = logging.getLogger("main")


def _print_table(candidates: list[GameCandidate]) -> None:
    if not candidates:
        print("  (tidak ada file baru)")
        return
    print(f"  {'STATUS':<12} {'TODAY':<6} {'PLATFORM':<10} TITLE")
    print(f"  {'-'*12} {'-'*6} {'-'*10} {'-'*40}")
    for c in candidates:
        print(
            f"  {c.status:<12} {'yes' if c.is_today else '':<6} "
            f"{c.platform:<10} {c.title or c.drive_file.file_name}"
            + (f"  ({c.disc})" if c.disc else "")
        )
        for w in c.warnings:
            print(f"       ⚠ {w}")


def _cli_progress(index: int, total: int, level: str, message: str) -> None:
    prefix = {"ok": "  ✓", "warn": "  !", "error": "  ✗", "done": "==>"}.get(level, "  ·")
    print(f"{prefix} [{index}/{total}] {message}")


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="LBG ingestion pipeline (headless)")
    parser.add_argument("--today", action="store_true", help="upload only games added to Drive today")
    parser.add_argument("--all", action="store_true", help="upload every new/disc candidate")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    setup_logging()
    logger.info("=== LBG CLI start (dataset=%s, dry_run=%s) ===", config.SANITY_DATASET, config.DRY_RUN)

    sanity = SanityClient()
    sanity.fetch_references()
    sanity.fetch_existing_games()
    genre_whitelist = sorted(set(sanity.genre_names))
    state = StateManager()
    drive = DriveClient()

    candidates = build_candidates(drive, sanity, state)

    print(f"\nDitemukan {len(candidates)} file belum diproses "
          f"({sum(c.is_today for c in candidates)} di-upload hari ini):\n")
    _print_table(candidates)

    if not (args.today or args.all):
        print("\nTidak ada yang di-upload. Jalankan dengan --today / --all, atau pakai `python app.py`.")
        return

    if args.all:
        selected = [c for c in candidates if c.selectable]
    else:
        selected = [c for c in candidates if c.selectable and c.is_today]

    if not selected:
        print("\nTidak ada kandidat yang bisa di-upload untuk pilihan itu.")
        return

    print(f"\nAkan meng-upload {len(selected)} game:")
    for c in selected:
        print(f"  • {c.title} [{c.platform}]" + (f" — {c.disc}" if c.disc else ""))

    if not args.yes:
        try:
            answer = input("\nLanjutkan? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Dibatalkan.")
            return

    gemini = GeminiClient()
    summary = ingest_selected(
        selected,
        gemini=gemini,
        sanity=sanity,
        state=state,
        genre_whitelist=genre_whitelist,
        progress=_cli_progress,
    )
    print(
        f"\nSelesai — {summary.created} dibuat, {summary.disc_appended} disc ditambahkan, "
        f"{summary.skipped} dilewati, total di state: {len(state)}."
    )
    if summary.errors:
        print(f"{len(summary.errors)} error:")
        for e in summary.errors:
            print(f"  ✗ {e}")


if __name__ == "__main__":
    run()
