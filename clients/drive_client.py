"""Google Drive API v3 wrapper — read-only folder/file scanning.

Auth: OAuth 2.0 installed-app flow. First run opens a browser for consent and
saves a refreshable token to GOOGLE_TOKEN_PATH for later headless runs.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger("drive_client")

_FOLDER_MIME = "application/vnd.google-apps.folder"


def _parse_rfc3339(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class DriveFile:
    file_id: str
    file_name: str
    file_size_bytes: int | None
    platform_folder_name: str
    created_time: _dt.datetime | None = None   # UTC, when the file was added to Drive
    modified_time: _dt.datetime | None = None  # UTC

    @property
    def download_url(self) -> str:
        return config.DRIVE_DOWNLOAD_URL_TEMPLATE.format(file_id=self.file_id)

    @property
    def uploaded_local_date(self) -> _dt.date | None:
        """created_time converted to the machine's local date."""
        if self.created_time is None:
            return None
        return self.created_time.astimezone().date()

    @property
    def is_uploaded_today(self) -> bool:
        return self.uploaded_local_date == _dt.date.today()


class DriveClient:
    def __init__(self) -> None:
        self._service = build("drive", "v3", credentials=self._get_credentials(), cache_discovery=False)

    # ─────────────── auth ───────────────
    @staticmethod
    def _get_credentials() -> Credentials:
        creds: Credentials | None = None
        token_path = config.GOOGLE_TOKEN_PATH

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), config.DRIVE_SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google Drive token")
            creds.refresh(Request())
        else:
            if not config.GOOGLE_CREDS_PATH.exists():
                raise RuntimeError(
                    f"Google client secret not found at {config.GOOGLE_CREDS_PATH}"
                )
            logger.info("Starting Google OAuth consent flow (browser)")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.GOOGLE_CREDS_PATH), config.DRIVE_SCOPES
            )
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Saved Google Drive token to %s", token_path)
        return creds

    # ─────────────── queries ───────────────
    def _list(self, query: str, fields: str) -> list[dict]:
        results: list[dict] = []
        page_token: str | None = None
        while True:
            try:
                resp = (
                    self._service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields=f"nextPageToken, {fields}",
                        pageSize=200,
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
            except HttpError as exc:
                logger.error("Drive API error for query %r: %s", query, exc)
                raise
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                return results

    def list_platform_folders(self) -> list[dict]:
        query = (
            f"'{config.DRIVE_PARENT_FOLDER_ID}' in parents "
            f"and mimeType = '{_FOLDER_MIME}' and trashed = false"
        )
        folders = self._list(query, "files(id, name)")
        logger.info("Found %d platform folder(s): %s", len(folders), [f["name"] for f in folders])
        return folders

    def list_files_in_folder(self, folder_id: str, folder_name: str) -> list[DriveFile]:
        query = (
            f"'{folder_id}' in parents "
            f"and mimeType != '{_FOLDER_MIME}' and trashed = false"
        )
        raw = self._list(query, "files(id, name, size, createdTime, modifiedTime)")
        files = [
            DriveFile(
                file_id=f["id"],
                file_name=f["name"],
                file_size_bytes=int(f["size"]) if f.get("size") is not None else None,
                platform_folder_name=folder_name,
                created_time=_parse_rfc3339(f.get("createdTime")),
                modified_time=_parse_rfc3339(f.get("modifiedTime")),
            )
            for f in raw
        ]
        logger.info("Folder %s: %d file(s)", folder_name, len(files))
        return files

    def scan_all(self) -> list[DriveFile]:
        out: list[DriveFile] = []
        for folder in self.list_platform_folders():
            out.extend(self.list_files_in_folder(folder["id"], folder["name"]))
        return out
