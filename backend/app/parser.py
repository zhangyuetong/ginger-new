"""
Parse Ginger dictionary definition strings into structured JSON.

POS markers: only a closed whitelist (same strings as part-of-speech lemmas in the lexicon),
each followed by whitespace — so tokens like "asj." inside gloss text are never split as POS.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final

# Canonical Ginger part-of-speech lemmas (include trailing dot). Must match DB bootstrap rows.
PART_OF_SPEECH_LEXEMES: Final[tuple[str, ...]] = (
    "sj.",
    "k.",
    "e.",
    "i.",
    "a.",
    "hh.",
    "bu.",
    "p.",
    "q.",
    "cj.",
    "r.",
    "y.",
)

_POS_ALT = "|".join(re.escape(p) for p in sorted(PART_OF_SPEECH_LEXEMES, key=lambda s: (-len(s), s)))
_POS_BOUNDARY = re.compile(rf"(?:^|[\s\n])({_POS_ALT})\s+", re.MULTILINE)
_NUM_SENSE = re.compile(r"(?:^|[\s\n])(\d+)\s+", re.MULTILINE)


def parse_definition(raw: str | None) -> dict[str, Any]:
    warnings: list[str] = []
    if raw is None or not str(raw).strip():
        return {
            "error": True,
            "posBlocks": [],
            "parseWarnings": ["Empty definition"],
        }

    s = str(raw).strip()

    pos_splits: list[tuple[int, int, str]] = []
    # (match_start_full, inner_pos_with_dot_prefix_len from content start?)
    # We store (content_start_marker_start, content_start_marker_end, pos_label)
    for m in _POS_BOUNDARY.finditer(s):
        pos_label = m.group(1)
        marker_start = m.start()
        marker_end = m.end()
        pos_splits.append((marker_start, marker_end, pos_label))

    if not pos_splits:
        return {
            "error": False,
            "posBlocks": [
                {"pos": None, "senses": [{"n": None, "text": s}]},
            ],
            "parseWarnings": ["No known POS markers (sj., k., …); stored as single unstructured block"],
        }

    preamble = s[: pos_splits[0][0]].strip()
    if preamble:
        warnings.append(f"Non-whitespace preamble before first POS discarded: {preamble[:120]!r}")

    blocks: list[dict[str, Any]] = []

    for i, (_ms, me, pos_label) in enumerate(pos_splits):
        body_start = me
        body_end = pos_splits[i + 1][0] if i + 1 < len(pos_splits) else len(s)
        body = s[body_start:body_end]

        senses = _parse_pos_body(body.strip())
        blocks.append({"pos": pos_label, "senses": senses})

        if _looks_like_numbered_but_empty(senses):
            warnings.append(f"POS {pos_label!r}: parsed numbered senses yielded empty fragments")

    return {"error": False, "posBlocks": blocks, "parseWarnings": warnings}


def _looks_like_numbered_but_empty(senses: list[dict[str, Any]]) -> bool:
    return any(s.get("n") is not None and not str(s.get("text", "")).strip() for s in senses)


def _parse_pos_body(body: str) -> list[dict[str, Any | None]]:
    if not body:
        return [{"n": None, "text": ""}]

    matches = list(_NUM_SENSE.finditer(body))
    if not matches:
        return [{"n": None, "text": body}]

    senses: list[dict[str, Any | None]] = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        senses.append({"n": n, "text": text})
    return senses


def dumps_definition_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def loads_definition_json(s: str | None) -> dict[str, Any] | None:
    if not s:
        return None
    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
