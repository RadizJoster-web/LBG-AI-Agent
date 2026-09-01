"""Local review UI for the LBG ingestion pipeline.

Not a public web app — it binds to 127.0.0.1 and exists only so a human can look
at what the Drive scan found and tick the games that should actually be uploaded.

Run:  python app.py
"""
from __future__ import annotations

import logging
import threading
import uuid
import webbrowser

from flask import Flask, jsonify, render_template, request

import config
from clients.drive_client import DriveClient
from clients.gemini_client import GeminiClient
from clients.sanity_client import SanityClient
from core.ingest import ingest_selected
from core.scanner import GameCandidate, build_candidates
from core.state_manager import StateManager
from logging_config import setup_logging

logger = logging.getLogger("web")

app = Flask(__name__, template_folder="templates", static_folder="static")


class Services:
    """Lazily-built singletons shared by all requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.drive: DriveClient | None = None
        self.sanity: SanityClient | None = None
        self.gemini: GeminiClient | None = None
        self.state: StateManager | None = None
        self.genre_whitelist: list[str] = []
        self.candidates: dict[str, GameCandidate] = {}

    def ensure_ready(self) -> None:
        with self._lock:
            if self.sanity is None:
                logger.info("Initialising Sanity client + references")
                self.sanity = SanityClient()
                self.sanity.fetch_references()
                self.sanity.fetch_existing_games()
                self.genre_whitelist = sorted(set(self.sanity.genre_names))
            if self.state is None:
                self.state = StateManager()
            if self.drive is None:
                logger.info("Initialising Google Drive client (may open a browser)")
                self.drive = DriveClient()
            if self.gemini is None:
                self.gemini = GeminiClient()


SERVICES = Services()


class Job:
    def __init__(self, total: int) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.total = total
        self.done = 0
        self.finished = False
        self.summary: dict | None = None
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def push(self, index: int, total: int, level: str, message: str) -> None:
        with self._lock:
            self.done = index
            self.total = total
            self.events.append({"index": index, "total": total, "level": level, "message": message})

    def snapshot(self, after: int = 0) -> dict:
        with self._lock:
            return {
                "job_id": self.id,
                "done": self.done,
                "total": self.total,
                "finished": self.finished,
                "summary": self.summary,
                "events": self.events[after:],
                "event_count": len(self.events),
            }


JOBS: dict[str, Job] = {}
_JOB_LOCK = threading.Lock()


@app.get("/")
def index():
    return render_template("index.html", dataset=config.SANITY_DATASET, dry_run=config.DRY_RUN)


@app.post("/api/scan")
def api_scan():
    try:
        SERVICES.ensure_ready()
        # refresh the existing-game index each scan so re-runs stay accurate
        SERVICES.sanity.fetch_existing_games()
        candidates = build_candidates(SERVICES.drive, SERVICES.sanity, SERVICES.state)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scan failed")
        return jsonify({"error": str(exc)}), 500

    SERVICES.candidates = {c.file_id: c for c in candidates}
    return jsonify(
        {
            "dataset": config.SANITY_DATASET,
            "dry_run": config.DRY_RUN,
            "count": len(candidates),
            "today": sum(c.is_today for c in candidates),
            "candidates": [c.to_dict() for c in candidates],
        }
    )


@app.post("/api/ingest")
def api_ingest():
    payload = request.get_json(silent=True) or {}
    file_ids = payload.get("file_ids") or []
    if not isinstance(file_ids, list) or not file_ids:
        return jsonify({"error": "Tidak ada game yang dipilih."}), 400

    with _JOB_LOCK:
        if any(not j.finished for j in JOBS.values()):
            return jsonify({"error": "Masih ada proses upload yang berjalan."}), 409

    selected = [SERVICES.candidates[f] for f in file_ids if f in SERVICES.candidates]
    unknown = [f for f in file_ids if f not in SERVICES.candidates]
    if unknown:
        logger.warning("Ignoring %d unknown file id(s) — scan again", len(unknown))
    if not selected:
        return jsonify({"error": "Pilihan tidak valid — scan ulang."}), 400

    # keep only rows we can actually send
    selected = [c for c in selected if c.selectable]
    if not selected:
        return jsonify({"error": "Tidak ada baris terpilih yang bisa di-upload."}), 400

    job = Job(total=len(selected))
    with _JOB_LOCK:
        JOBS[job.id] = job

    def worker() -> None:
        try:
            summary = ingest_selected(
                selected,
                gemini=SERVICES.gemini,
                sanity=SERVICES.sanity,
                state=SERVICES.state,
                genre_whitelist=SERVICES.genre_whitelist,
                progress=job.push,
            )
            job.summary = summary.as_dict()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ingest job crashed")
            job.push(job.done, job.total, "error", f"Proses berhenti: {exc}")
            job.summary = {"created": 0, "disc_appended": 0, "skipped": len(selected),
                           "errors": [str(exc)]}
        finally:
            job.finished = True
            # drop the consumed candidates so a stale re-submit can't double up
            for c in selected:
                SERVICES.candidates.pop(c.file_id, None)

    threading.Thread(target=worker, name=f"ingest-{job.id}", daemon=True).start()
    return jsonify({"job_id": job.id, "total": job.total})


@app.get("/api/ingest/<job_id>")
def api_ingest_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "job tidak ditemukan"}), 404
    after = request.args.get("after", default=0, type=int)
    return jsonify(job.snapshot(after=after))


def main() -> None:
    setup_logging()
    host, port = "127.0.0.1", 5000
    url = f"http://{host}:{port}/"
    logger.info("LBG review UI → %s", url)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
