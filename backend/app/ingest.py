"""Pandas-based Excel ingest with Ginger column naming."""

from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entry, ImportRun, utc_now_iso
from app.parser import dumps_definition_json, parse_definition


def normalize_col(name: Any) -> str:
    return re.sub(r"\s+", "", str(name).strip()).lower()


GUESS_COLUMN_SIGNATURES = frozenset(
    {
        "guess_zh",
        "guesszh",
        "guess_cn",
        "guesscn",
        "cn_guess",
        "zh_guess",
        "guess",
        "chinese_guess",
        "中文猜测",
        "猜测",
        "中文",
        "翻译",
    }
)


def _cell_plain(val: Any):
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            return val
    return val


def ingest_excel_bytes(db: Session, content: bytes, filename: str | None = None) -> dict[str, Any]:
    df = pd.read_excel(BytesIO(content), engine="openpyxl")
    if df.empty:
        run = ImportRun(filename=filename, rows_total=0, created_at=utc_now_iso())
        db.add(run)
        db.commit()
        db.refresh(run)
        return {"importRunId": run.id, "rows": 0, "updated": 0, "created": 0}

    ncol_map: dict[str, str] = {}
    for c in df.columns:
        ncol_map[normalize_col(str(c))] = str(c)

    wcol = ncol_map.get("word")
    dcol = ncol_map.get("definition")
    ccol = ncol_map.get("coloridx")

    if not wcol or not dcol:
        raise ValueError(f"Excel must contain word + definition columns. Got: {list(df.columns)}")

    guess_source_col: str | None = None
    if "guess_zh" in ncol_map:
        guess_source_col = ncol_map["guess_zh"]
    else:
        for nc, orig in ncol_map.items():
            if nc in GUESS_COLUMN_SIGNATURES:
                guess_source_col = orig
                break

    created = 0
    updated = 0

    for _idx, row in df.iterrows():
        word_val = row.get(wcol)
        word = "" if word_val is None or (isinstance(word_val, float) and pd.isna(word_val)) else str(word_val).strip()
        if not word:
            continue

        def_raw = row.get(dcol)
        definition = None if def_raw is None or (isinstance(def_raw, float) and pd.isna(def_raw)) else str(def_raw)

        ci_raw = row.get(ccol) if ccol else None
        ci = _cell_plain(ci_raw)
        color_idx = None if ci is None else int(ci) if str(ci).strip() != "" else None

        extras_obj: dict[str, Any] = {}
        skip = {wcol, dcol}
        if ccol:
            skip.add(ccol)
        for c in df.columns:
            cstr = str(c)
            if cstr in skip:
                continue
            val = row.get(c)
            extras_obj[cstr] = None if isinstance(val, float) and pd.isna(val) else _cell_plain(val)

        parsed = parse_definition(definition)
        def_json = dumps_definition_json(parsed)
        extras_json = json.dumps(extras_obj, ensure_ascii=False)

        seed_guess: str | None = None
        if guess_source_col:
            gv = row.get(guess_source_col)
            if gv is not None and not (isinstance(gv, float) and pd.isna(gv)):
                g = str(gv).strip()
                seed_guess = g if g else None

        stmt = select(Entry).where(Entry.word == word)
        existing = db.execute(stmt).scalar_one_or_none()

        if existing:
            existing.color_idx = color_idx
            existing.definition_raw = definition
            existing.definition_json = def_json
            existing.extras_json = extras_json
            if seed_guess is not None:
                existing.guess_zh = seed_guess
            updated += 1
        else:
            ent = Entry(
                word=word,
                color_idx=color_idx,
                definition_raw=definition,
                definition_json=def_json,
                extras_json=extras_json,
                guess_zh=seed_guess,
            )
            db.add(ent)
            created += 1

    run = ImportRun(filename=filename, rows_total=len(df.index), created_at=utc_now_iso())
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"importRunId": run.id, "rows": len(df.index), "created": created, "updated": updated}
