from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entry, utc_now_iso
from app.parser import (
    PART_OF_SPEECH_LEXEMES,
    entry_has_pos,
    is_valid_pos_lexeme,
    loads_definition_json,
    normalize_pos_query,
    parse_definition,
)
from app.render import build_words_index, render_definition_struct, text_contains_lemma
from app.schemas import EntriesPage, EntryDetail, EntryListRow, GuessPatchBody, PosBlockDto, RenderedDto, SenseDto, SpanDto

router = APIRouter(prefix="/api/entries", tags=["entries"])

DEFAULT_LIMIT = 80
SCAN_BATCH = 200

SearchMode = Literal["lemma", "definition", "pos"]
WordMatch = Literal["prefix", "infix", "suffix"]


def _safe_json_load(s: str | None, default: dict[str, Any]) -> dict[str, Any]:
    if not s:
        return dict(default)
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else dict(default)
    except json.JSONDecodeError:
        return dict(default)


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _word_like_pattern(q: str, word_match: WordMatch) -> str:
    escaped = _escape_like(q)
    if word_match == "prefix":
        return escaped + "%"
    if word_match == "suffix":
        return "%" + escaped
    return "%" + escaped + "%"


def _all_nonempty_guesses(db: Session) -> list[tuple[str, str]]:
    rows = db.execute(select(Entry.word, Entry.guess_zh)).all()
    return [(w, str(g).strip()) for w, g in rows if w and g and str(g).strip()]


def _guess_zh_map(db: Session) -> dict[str, str]:
    return dict(_all_nonempty_guesses(db))


def _dto_from_rendered(blob: dict[str, Any], guess_zh_map: dict[str, str]) -> RenderedDto:
    blocks_out: list[PosBlockDto] = []
    for b in blob.get("posBlocks") or []:
        pos_label = b.get("pos")
        pos_zh = guess_zh_map.get(pos_label, None) if pos_label else None
        senses_out: list[SenseDto] = []
        for s in b.get("senses") or []:
            spans = [SpanDto.model_validate(sp) for sp in s.get("renderedSpans") or []]
            senses_out.append(
                SenseDto(
                    n=s.get("n"),
                    text=s.get("text") or "",
                    renderedSpans=spans,
                )
            )
        blocks_out.append(PosBlockDto(pos=pos_label, posGuessZh=pos_zh, senses=senses_out))
    return RenderedDto(posBlocks=blocks_out)


def _build_entry_detail(db: Session, e: Entry) -> EntryDetail:
    parsed = loads_definition_json(e.definition_json)
    if parsed is None:
        parsed = parse_definition(e.definition_raw)

    extras = _safe_json_load(e.extras_json, {})
    guess_pairs = _all_nonempty_guesses(db)
    guess_index = build_words_index(guess_pairs)
    rendered_blob = render_definition_struct(parsed, guess_index)
    rendered = _dto_from_rendered(rendered_blob, dict(guess_pairs))

    return EntryDetail(
        id=e.id,
        word=e.word,
        colorIdx=e.color_idx,
        definitionRaw=e.definition_raw,
        definition=parsed,
        extras=extras,
        rendered=rendered,
        guessZh=e.guess_zh,
        updatedAt=e.updated_at or "",
    )


def _entry_parsed(e: Entry) -> dict[str, Any]:
    parsed = loads_definition_json(e.definition_json)
    if parsed is None:
        parsed = parse_definition(e.definition_raw)
    return parsed


def _entry_matches_pos(e: Entry, pos_lexeme: str) -> bool:
    parsed = _entry_parsed(e)
    if parsed.get("error"):
        return False
    return entry_has_pos(parsed, pos_lexeme)


def _build_list_row(
    e: Entry,
    guess_index: dict[int, dict[str, str]],
    guess_map: dict[str, str],
) -> EntryListRow:
    parsed = loads_definition_json(e.definition_json)
    if parsed is None:
        parsed = parse_definition(e.definition_raw)

    rnd = render_definition_struct(parsed, guess_index)
    parts: list[str] = []
    for pb in rnd.get("posBlocks") or []:
        lbl = pb.get("pos")
        if lbl:
            zh_l = guess_map.get(lbl)
            prefix = f"[{lbl} {zh_l}] " if zh_l else f"[{lbl}] "
        else:
            prefix = ""
        for sens in pb.get("senses") or []:
            spans = sens.get("renderedSpans") or []
            merged_spans = "".join(sp.get("value", "") if isinstance(sp, dict) else "" for sp in spans)
            parts.append(prefix + merged_spans)
            if sum(len(x) for x in parts) > 400:
                break
        if sum(len(x) for x in parts) > 400:
            break

    preview = "".join(parts).strip()[:440] if parts else ""
    if not preview:
        preview = (e.definition_raw or "").strip()[:440]

    return EntryListRow(
        id=e.id,
        word=e.word,
        colorIdx=e.color_idx,
        guessZh=e.guess_zh,
        preview=preview or None,
        extras=None,
    )


def _fetch_lemma_page(
    db: Session,
    query: str,
    word_match: WordMatch,
    cursor: int | None,
    lim: int,
) -> tuple[list[Entry], bool]:
    stmt = select(Entry)
    if cursor is not None:
        stmt = stmt.where(Entry.id > cursor)
    if query.strip():
        pattern = _word_like_pattern(query.strip(), word_match)
        stmt = stmt.where(Entry.word.like(pattern, escape="\\"))
    stmt = stmt.order_by(Entry.id.asc()).limit(lim + 1)
    fetched = list(db.execute(stmt).scalars().all())
    has_more = len(fetched) > lim
    return fetched[:lim], has_more


def _scan_entries_page(
    db: Session,
    cursor: int | None,
    lim: int,
    predicate,
    *,
    coarse_like: str | None = None,
) -> tuple[list[Entry], bool]:
    """Scan by id until lim+1 matches; optional SQL LIKE prefilter on definition_raw."""
    last_id = cursor if cursor is not None else 0
    matched: list[Entry] = []
    exhausted = False

    while len(matched) < lim + 1:
        stmt = select(Entry).where(Entry.id > last_id).order_by(Entry.id.asc()).limit(SCAN_BATCH)
        if coarse_like is not None:
            stmt = stmt.where(Entry.definition_raw.isnot(None)).where(
                Entry.definition_raw.like(coarse_like, escape="\\")
            )
        batch = list(db.execute(stmt).scalars().all())
        if not batch:
            exhausted = True
            break

        for e in batch:
            last_id = e.id
            if predicate(e):
                matched.append(e)
                if len(matched) > lim:
                    break

        if len(matched) > lim:
            break
        if len(batch) < SCAN_BATCH:
            exhausted = True
            break

    if len(matched) > lim:
        return matched[:lim], True

    if not exhausted and len(matched) == lim:
        probe = select(Entry).where(Entry.id > last_id).order_by(Entry.id.asc()).limit(SCAN_BATCH)
        if coarse_like is not None:
            probe = probe.where(Entry.definition_raw.isnot(None)).where(
                Entry.definition_raw.like(coarse_like, escape="\\")
            )
        for e in db.execute(probe).scalars().all():
            if predicate(e):
                return matched, True

    return matched, False


def _scan_definition_page(
    db: Session,
    lemma: str,
    cursor: int | None,
    lim: int,
) -> tuple[list[Entry], bool]:
    coarse = "%" + _escape_like(lemma) + "%"
    return _scan_entries_page(
        db,
        cursor,
        lim,
        lambda e: text_contains_lemma(e.definition_raw or "", lemma),
        coarse_like=coarse,
    )


@router.get("", response_model=EntriesPage)
def list_entries(
    query: str = "",
    cursor: int | None = None,
    limit: int = DEFAULT_LIMIT,
    searchMode: SearchMode = "lemma",
    wordMatch: WordMatch = "prefix",
    db: Session = Depends(get_db),
):
    lim = min(max(limit, 1), 200)
    q = query.strip()

    if searchMode == "pos" and q:
        pos_lexeme = normalize_pos_query(q)
        if not is_valid_pos_lexeme(pos_lexeme):
            allowed = ", ".join(PART_OF_SPEECH_LEXEMES)
            raise HTTPException(
                status_code=400,
                detail=f"Unknown part of speech {pos_lexeme!r}. Allowed: {allowed}",
            )
        page_rows, has_more = _scan_entries_page(
            db, cursor, lim, lambda e: _entry_matches_pos(e, pos_lexeme)
        )
    elif searchMode == "definition" and q:
        page_rows, has_more = _scan_definition_page(db, q, cursor, lim)
    else:
        page_rows, has_more = _fetch_lemma_page(db, query, wordMatch, cursor, lim)

    guess_pairs = _all_nonempty_guesses(db)
    guess_index = build_words_index(guess_pairs)
    guess_map = dict(guess_pairs)

    items = [_build_list_row(e, guess_index, guess_map) for e in page_rows]
    next_cursor = page_rows[-1].id if has_more and page_rows else None

    return EntriesPage(items=items, nextCursor=next_cursor)


@router.get("/{entry_id:int}", response_model=EntryDetail)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.get(Entry, entry_id)
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    return _build_entry_detail(db, e)


@router.patch("/{entry_id:int}/guess", response_model=EntryDetail)
def patch_guess(entry_id: int, body: GuessPatchBody, db: Session = Depends(get_db)):
    e = db.get(Entry, entry_id)
    if not e:
        raise HTTPException(status_code=404, detail="Not found")

    s = body.guessZh.strip()
    e.guess_zh = None if s == "" else s
    e.updated_at = utc_now_iso()
    db.commit()
    db.refresh(e)
    return _build_entry_detail(db, e)
