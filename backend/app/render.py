"""Render glossary text spans with longest-match lemmas that have guesses."""

from __future__ import annotations

import re
from typing import Any, TypedDict


class RenderSpan(TypedDict, total=False):
    kind: str  # 'text' | 'gloss'
    value: str
    lemma: str
    guessZh: str


TOKEN_RE = re.compile(r"[A-Za-z0-9_\u0080-\uFFFF']+|[^\s]| +")


def longest_match_candidates(words_by_len: dict[int, dict[str, str]]) -> list[int]:
    return sorted(words_by_len.keys(), reverse=True)


def build_words_index(guesses: list[tuple[str, str]]) -> dict[int, dict[str, str]]:
    """
    guesses: [(word, guess_zh), ...], only incl. non-empty guesses
    For each lemma length produce map lemma -> zh
    """
    by_len: dict[int, dict[str, str]] = {}
    for w, zh in guesses:
        if not w or not zh or not zh.strip():
            continue
        by_len.setdefault(len(w), {})[w] = zh.strip()
    return by_len


def _lexeme_char(ch: str) -> bool:
    """Characters treated as contiguous with a lexical form (prevent in‑word replacements)."""
    return ch.isalnum() or ch == "_" or ch in "'’"


def _is_word_boundary_left(text: str, idx: int) -> bool:
    if idx <= 0:
        return True
    return not _lexeme_char(text[idx - 1])


def _is_word_boundary_right(text: str, idx_after: int) -> bool:
    if idx_after >= len(text):
        return True
    return not _lexeme_char(text[idx_after])


def text_contains_lemma(text: str, lemma: str) -> bool:
    """True if lemma appears in text as a whole token (same boundaries as gloss matching)."""
    if not text or not lemma:
        return False
    ln = len(lemma)
    if ln > len(text):
        return False
    limit = len(text) - ln
    pos = 0
    while pos <= limit:
        if text[pos : pos + ln] == lemma:
            if _is_word_boundary_left(text, pos) and _is_word_boundary_right(text, pos + ln):
                return True
        pos += 1
    return False


def segment_to_spans(text: str, words_by_len: dict[int, dict[str, str]]) -> list[RenderSpan]:
    if not text:
        return []
    lens = longest_match_candidates(words_by_len)

    spans: list[RenderSpan] = []
    pos = 0
    length = len(text)

    while pos < length:
        ch = text[pos]
        if ch.isspace():
            ws_end = pos
            while ws_end < length and text[ws_end].isspace():
                ws_end += 1
            spans.append({"kind": "text", "value": text[pos:ws_end]})
            pos = ws_end
            continue

        if lens and _is_word_boundary_left(text, pos):
            matched: tuple[int, str, str] | None = None
            max_try = length - pos
            for ln in lens:
                if ln > max_try:
                    continue
                candidate = text[pos : pos + ln]
                lemma_map = words_by_len.get(ln)
                if not lemma_map or candidate not in lemma_map:
                    continue
                right = pos + ln
                if _is_word_boundary_right(text, right):
                    matched = (ln, candidate, lemma_map[candidate])
                    break
            if matched is not None:
                ln, lemma, zh = matched
                spans.append({"kind": "gloss", "value": zh, "lemma": lemma, "guessZh": zh})
                pos += ln
                continue

        m = TOKEN_RE.match(text, pos)
        if m:
            spans.append({"kind": "text", "value": m.group(0)})
            pos = m.end()
        else:
            spans.append({"kind": "text", "value": text[pos]})
            pos += 1

    merged = merge_adjacent_text(spans)
    return merged


def merge_adjacent_text(spans: list[RenderSpan]) -> list[RenderSpan]:
    if not spans:
        return []
    out: list[RenderSpan] = []
    buf = ""
    for sp in spans:
        if sp.get("kind") == "text":
            buf += sp.get("value", "")
        else:
            if buf:
                out.append({"kind": "text", "value": buf})
                buf = ""
            out.append(sp)
    if buf:
        out.append({"kind": "text", "value": buf})
    return out


def render_definition_struct(
    definition_json: dict[str, Any],
    words_by_len: dict[int, dict[str, str]],
) -> dict[str, Any]:
    rendered_pos_blocks = []
    for block in definition_json.get("posBlocks") or []:
        pos_label = block.get("pos")
        senses_out = []
        for sense in block.get("senses") or []:
            txt = sense.get("text") or ""
            spans = segment_to_spans(txt, words_by_len)
            senses_out.append({"n": sense.get("n"), "text": txt, "renderedSpans": spans})
        rendered_pos_blocks.append({"pos": pos_label, "senses": senses_out})
    return {"posBlocks": rendered_pos_blocks}
