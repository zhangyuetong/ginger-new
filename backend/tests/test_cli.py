import sqlite3

from cli import _part_of_speech_rows
from app.parser import PART_OF_SPEECH_LEXEMES


def test_part_of_speech_rows_preserve_parser_order():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE entries ("
        "id INTEGER PRIMARY KEY, "
        "word TEXT NOT NULL, "
        "guess_zh TEXT, "
        "definition_raw TEXT, "
        "definition_json TEXT, "
        "color_idx INTEGER, "
        "updated_at TEXT)"
    )

    inserted = [
        ("k.", "动词"),
        ("sj.", "名词"),
        ("q.", "疑问词"),
    ]
    for idx, (word, guess_zh) in enumerate(inserted, start=1):
        conn.execute(
            "INSERT INTO entries (id, word, guess_zh, definition_raw, definition_json, color_idx, updated_at) "
            "VALUES (?, ?, ?, '', NULL, NULL, NULL)",
            (idx, word, guess_zh),
        )

    rows = _part_of_speech_rows(conn)

    assert [r["word"] for r in rows] == [word for word in PART_OF_SPEECH_LEXEMES if word in {"sj.", "k.", "q."}]
    assert [r["guess_zh"] for r in rows] == ["名词", "动词", "疑问词"]
