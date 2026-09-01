"""Turn a raw Drive scan into a reviewable list of game candidates.

Shared by both entry points (web UI and CLI). No Gemini calls here — this is
cheap metadata only, so the review form loads fast.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from slugify import slugify

import config
from clients.drive_client import DriveClient, DriveFile
from clients.sanity_client import SanityClient
from core.file_size_formatter import format_file_size
from core.state_manager import StateManager
from core.title_cleaner import CleanedTitle, clean_title

logger = logging.getLogger("scanner")


@dataclass
class GameCandidate:
    drive_file: DriveFile
    cleaned: CleanedTitle
    doc_id: str
    platform_ref: str | None
    region_slug: str
    region_ref: str | None
    existing_id: str | None          # matching game already in Sanity
    already_processed: bool          # file_id present in processed_files.json
    warnings: list[str] = field(default_factory=list)

    # ── convenience for the UI ──
    @property
    def file_id(self) -> str:
        return self.drive_file.file_id

    @property
    def title(self) -> str:
        return self.cleaned.title

    @property
    def platform(self) -> str:
        return self.drive_file.platform_folder_name

    @property
    def disc(self) -> str | None:
        return self.cleaned.disc_number

    @property
    def file_size(self) -> str | None:
        return format_file_size(self.drive_file.file_size_bytes)

    @property
    def uploaded_date(self) -> str | None:
        d = self.drive_file.uploaded_local_date
        return d.isoformat() if d else None

    @property
    def is_today(self) -> bool:
        return self.drive_file.is_uploaded_today

    @property
    def status(self) -> str:
        if not self.platform_ref or not self.region_ref or not self.cleaned.title:
            return "blocked"
        if self.existing_id and self.disc:
            return "disc-append"   # game exists; add this disc's download link
        if self.existing_id:
            return "exists"        # true duplicate — do not re-upload
        if self.disc:
            return "disc-new"      # new game, first disc seen
        return "new"

    @property
    def selectable(self) -> bool:
        """Can this row be uploaded at all?"""
        return self.status in {"new", "disc-new", "disc-append"}

    @property
    def default_checked(self) -> bool:
        """Pre-ticked in the form: uploaded to Drive today and safe to send."""
        return self.selectable and self.is_today

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "file_name": self.drive_file.file_name,
            "title": self.title,
            "platform": self.platform,
            "region": self.region_slug,
            "disc": self.disc,
            "file_size": self.file_size,
            "uploaded_date": self.uploaded_date,
            "is_today": self.is_today,
            "status": self.status,
            "selectable": self.selectable,
            "default_checked": self.default_checked,
            "existing_id": self.existing_id,
            "warnings": self.warnings,
        }


def _build_one(df: DriveFile, sanity: SanityClient, state: StateManager) -> GameCandidate:
    cleaned = clean_title(df.file_name)
    platform_slug = slugify(df.platform_folder_name)
    doc_id = slugify(f"{cleaned.title}-{platform_slug}") if cleaned.title else ""

    platform_ref = sanity.platforms.get(platform_slug)
    region_slug = cleaned.region_tag or config.DEFAULT_REGION_SLUG
    region_ref = sanity.regions.get(region_slug) or sanity.regions.get(config.DEFAULT_REGION_SLUG)

    warnings: list[str] = []
    if not cleaned.title:
        warnings.append("Judul kosong setelah dibersihkan")
    if not platform_ref:
        warnings.append(f"Platform '{df.platform_folder_name}' tidak ada di Sanity")
    if cleaned.region_tag is None:
        warnings.append(f"Tidak ada tag region di nama file — default '{region_slug}'")
    if not region_ref:
        warnings.append(f"Region '{region_slug}' tidak ada di Sanity")

    existing_id = None
    if doc_id:
        existing_id = sanity.find_existing_game(
            slug_id=doc_id, title=cleaned.title, platform_ref=platform_ref
        )

    return GameCandidate(
        drive_file=df,
        cleaned=cleaned,
        doc_id=doc_id,
        platform_ref=platform_ref,
        region_slug=region_slug,
        region_ref=region_ref,
        existing_id=existing_id,
        already_processed=state.is_processed(df.file_id),
        warnings=warnings,
    )


def build_candidates(
    drive: DriveClient, sanity: SanityClient, state: StateManager
) -> list[GameCandidate]:
    """All not-yet-processed Drive files as review candidates, newest upload first."""
    all_files = drive.scan_all()
    candidates = [
        _build_one(df, sanity, state)
        for df in all_files
        if not state.is_processed(df.file_id)
    ]
    # Today's uploads first; then newest createdTime; then platform/name.
    candidates.sort(
        key=lambda c: (
            not c.is_today,
            -(c.drive_file.created_time.timestamp() if c.drive_file.created_time else 0),
            c.platform,
            c.drive_file.file_name,
        )
    )
    logger.info(
        "Built %d candidate(s) — %d uploaded today, %d already in Sanity",
        len(candidates),
        sum(c.is_today for c in candidates),
        sum(bool(c.existing_id) for c in candidates),
    )
    return candidates
