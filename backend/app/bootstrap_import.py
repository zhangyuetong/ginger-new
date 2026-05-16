"""Load Ginger.xlsx from the repository root when the API starts."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ingest import ingest_excel_bytes
from app.models import Entry
from app.parser import dumps_definition_json, PART_OF_SPEECH_LEXEMES

log = logging.getLogger(__name__)

# backend/app → parents[2] == 仓库根 ginger-new/
_REPO_ROOT = Path(__file__).resolve().parents[2]

_STUB_POS_JSON = dumps_definition_json(
    {"error": False, "posBlocks": [], "parseWarnings": [], "posTagLexeme": True},
)


def default_spreadsheet_path() -> Path:
    override = os.environ.get("GINGER_XLSX_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / "Ginger.xlsx").resolve()


def ensure_part_of_speech_entries(db: Session) -> int:
    """Ensure POS lemmas exist as normal dictionary rows (guessable like any word)."""
    created = 0
    for w in PART_OF_SPEECH_LEXEMES:
        existing = db.execute(select(Entry.id).where(Entry.word == w)).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            Entry(
                word=w,
                color_idx=None,
                definition_raw=None,
                definition_json=_STUB_POS_JSON,
                extras_json=None,
                guess_zh=None,
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def run_startup_import() -> None:
    if os.environ.get("SKIP_GINGER_XLS_IMPORT", "").strip() in {"1", "true", "yes"}:
        log.info("SKIP_GINGER_XLS_IMPORT set; skipping local Ginger.xlsx import")
        return

    path = default_spreadsheet_path()
    if not path.is_file():
        log.warning("Ginger workbook not found at %s — no rows imported", path)
        return

    raw = path.read_bytes()
    db = SessionLocal()
    try:
        summary = ingest_excel_bytes(db, raw, filename=path.name)
        log.info(
            "Imported %s → created=%s updated=%s rows=%s (importRunId=%s)",
            path.name,
            summary["created"],
            summary["updated"],
            summary["rows"],
            summary["importRunId"],
        )
    finally:
        db.close()
