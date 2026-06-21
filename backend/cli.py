#!/usr/bin/env python3
"""
Ginger 词典 CLI —— 给 Coding Agent 用的查词脚手架。

直接读取 SQLite（backend/data/ginger.sqlite3），无需启动后端服务。
搜索 / gloss 中文替换的语义与前端界面完全一致，因为复用了
backend/app 下的 parser.py、render.py。

用法见仓库根目录的 CLI.md，或 `python cli.py --help`。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# 让本脚本无论从何处运行都能 import app.parser / app.render
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from app.parser import (  # noqa: E402
    PART_OF_SPEECH_LEXEMES,
    entry_has_pos,
    is_valid_pos_lexeme,
    loads_definition_json,
    normalize_pos_query,
    parse_definition,
)
from app.render import (  # noqa: E402
    build_words_index,
    render_definition_struct,
    segment_to_spans,
    text_contains_lemma,
)

DEFAULT_DB = _HERE / "data" / "ginger.sqlite3"

# Windows 控制台默认不是 UTF-8，Ginger 释义里有中文推测，强制 UTF-8 输出。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# DB 访问
# --------------------------------------------------------------------------- #
def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(f"找不到数据库：{db_path}\n（用 --db 指定路径，或先启动一次后端以生成数据库）")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _all_guess_pairs(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """所有非空中文推测 (word, guess_zh)，即 gloss 替换词典。"""
    rows = conn.execute(
        "SELECT word, guess_zh FROM entries "
        "WHERE guess_zh IS NOT NULL AND trim(guess_zh) <> ''"
    ).fetchall()
    return [(r["word"], str(r["guess_zh"]).strip()) for r in rows]


def _parsed_for(row: sqlite3.Row) -> dict[str, Any]:
    parsed = loads_definition_json(row["definition_json"])
    if parsed is None:
        parsed = parse_definition(row["definition_raw"])
    return parsed


def _part_of_speech_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """按 parser 中定义的顺序返回词性占位词条。"""
    placeholders = ",".join("?" for _ in PART_OF_SPEECH_LEXEMES)
    rows = conn.execute(
        f"SELECT * FROM entries WHERE word IN ({placeholders})",
        PART_OF_SPEECH_LEXEMES,
    ).fetchall()
    by_word = {str(r["word"]): r for r in rows}
    return [by_word[word] for word in PART_OF_SPEECH_LEXEMES if word in by_word]


# --------------------------------------------------------------------------- #
# 渲染（与后端 _build_list_row / _build_entry_detail 同语义）
# --------------------------------------------------------------------------- #
def _preview(row: sqlite3.Row, guess_index: dict[int, dict[str, str]], guess_map: dict[str, str]) -> str:
    """列表预览：拼接已替换中文的义项文本，截断到 ~440 字。"""
    parsed = _parsed_for(row)
    rnd = render_definition_struct(parsed, guess_index)
    parts: list[str] = []
    for pb in rnd.get("posBlocks") or []:
        lbl = pb.get("pos")
        if lbl:
            zh = guess_map.get(lbl)
            prefix = f"[{lbl} {zh}] " if zh else f"[{lbl}] "
        else:
            prefix = ""
        for sens in pb.get("senses") or []:
            spans = sens.get("renderedSpans") or []
            merged = "".join(sp.get("value", "") for sp in spans if isinstance(sp, dict))
            parts.append(prefix + merged)
            if sum(len(x) for x in parts) > 400:
                break
        if sum(len(x) for x in parts) > 400:
            break
    preview = "".join(parts).strip()[:440] if parts else ""
    if not preview:
        preview = (row["definition_raw"] or "").strip()[:440]
    return preview


def _rendered_lines(row: sqlite3.Row, guess_index: dict[int, dict[str, str]], guess_map: dict[str, str]) -> list[str]:
    """详情：逐义项输出，gloss 命中处用《》括起替换的中文，便于人/agent 一眼看出。"""
    parsed = _parsed_for(row)
    rnd = render_definition_struct(parsed, guess_index)
    lines: list[str] = []
    for pb in rnd.get("posBlocks") or []:
        lbl = pb.get("pos")
        if lbl:
            zh = guess_map.get(lbl)
            head = f"<{lbl}>" + (f" {zh}" if zh else "")
        else:
            head = "<unstructured>"
        lines.append(head)
        for sens in pb.get("senses") or []:
            n = sens.get("n")
            spans = sens.get("renderedSpans") or []
            buf = ""
            for sp in spans:
                if not isinstance(sp, dict):
                    continue
                if sp.get("kind") == "gloss":
                    buf += "《" + sp.get("value", "") + "》"
                else:
                    buf += sp.get("value", "")
            marker = f"  {n}. " if isinstance(n, int) else "  · "
            lines.append(marker + buf.strip())
    return lines


def _render_inline_spans(spans: list[dict[str, str]]) -> str:
    buf = ""
    for sp in spans:
        if sp.get("kind") == "gloss":
            buf += "《" + sp.get("value", "") + "》"
        else:
            buf += sp.get("value", "")
    return buf


def _translate_text(conn: sqlite3.Connection, text: str) -> tuple[str, list[dict[str, str]]]:
    guess_index = build_words_index(_all_guess_pairs(conn))
    spans = segment_to_spans(text, guess_index)
    return _render_inline_spans(spans), spans


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def _emit_rows(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    as_json: bool,
    has_more: bool = False,
) -> None:
    pairs = _all_guess_pairs(conn)
    guess_index = build_words_index(pairs)
    guess_map = dict(pairs)

    if as_json:
        out = {
            "items": [
                {
                    "id": r["id"],
                    "word": r["word"],
                    "colorIdx": r["color_idx"],
                    "guessZh": r["guess_zh"],
                    "preview": _preview(r, guess_index, guess_map),
                }
                for r in rows
            ],
            "count": len(rows),
            "hasMore": has_more,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("(无结果)")
        return
    for r in rows:
        guess = f"  →{r['guess_zh']}" if r["guess_zh"] else ""
        print(f"#{r['id']:<5} {r['word']}{guess}")
        pv = _preview(r, guess_index, guess_map)
        if pv:
            print(f"        {pv[:200]}")
    if has_more:
        print(f"\n(显示前 {len(rows)} 条，还有更多；用 --limit 调大)")
    else:
        print(f"\n({len(rows)} 条)")


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #
def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def cmd_word(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    q = args.query.strip()
    esc = _escape_like(q)
    if args.match == "prefix":
        pattern = esc + "%"
    elif args.match == "suffix":
        pattern = "%" + esc
    else:
        pattern = "%" + esc + "%"
    rows = conn.execute(
        "SELECT * FROM entries WHERE word LIKE ? ESCAPE '\\' ORDER BY id ASC LIMIT ?",
        (pattern, args.limit + 1),
    ).fetchall()
    has_more = len(rows) > args.limit
    _emit_rows(conn, rows[: args.limit], args.json, has_more)


def cmd_def(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    lemma = args.word.strip()
    coarse = "%" + _escape_like(lemma) + "%"
    candidates = conn.execute(
        "SELECT * FROM entries WHERE definition_raw IS NOT NULL "
        "AND definition_raw LIKE ? ESCAPE '\\' ORDER BY id ASC",
        (coarse,),
    ).fetchall()
    # 整词 + 词界过滤（与后端 text_contains_lemma 一致）
    rows = [r for r in candidates if text_contains_lemma(r["definition_raw"] or "", lemma)]
    has_more = len(rows) > args.limit
    _emit_rows(conn, rows[: args.limit], args.json, has_more)


def cmd_pos(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    pos = normalize_pos_query(args.pos)
    if not is_valid_pos_lexeme(pos):
        sys.exit(f"未知词性 {pos!r}。可用：{', '.join(PART_OF_SPEECH_LEXEMES)}")
    rows: list[sqlite3.Row] = []
    has_more = False
    for r in conn.execute("SELECT * FROM entries ORDER BY id ASC").fetchall():
        parsed = _parsed_for(r)
        if not parsed.get("error") and entry_has_pos(parsed, pos):
            if len(rows) >= args.limit:
                has_more = True
                break
            rows.append(r)
    _emit_rows(conn, rows, args.json, has_more)


def cmd_abbr(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = _part_of_speech_rows(conn)
    if args.json:
        print(json.dumps(
            [
                {
                    "id": r["id"],
                    "word": r["word"],
                    "guessZh": r["guess_zh"],
                }
                for r in rows
            ],
            ensure_ascii=False, indent=2,
        ))
        return

    if not rows:
        print("(无词性标记)")
        return

    for r in rows:
        meaning = (r["guess_zh"] or "").strip() or "(未推测)"
        print(f"{r['word']} {meaning}")


def cmd_translate(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    translated, spans = _translate_text(conn, args.text)
    if args.json:
        print(json.dumps(
            {
                "source": args.text,
                "translated": translated,
                "spans": spans,
            },
            ensure_ascii=False, indent=2,
        ))
        return

    print(translated)


def _resolve(conn: sqlite3.Connection, ref: str) -> sqlite3.Row | None:
    if ref.isdigit():
        return conn.execute("SELECT * FROM entries WHERE id = ?", (int(ref),)).fetchone()
    return conn.execute("SELECT * FROM entries WHERE word = ?", (ref,)).fetchone()


def cmd_show(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    r = _resolve(conn, args.ref)
    if r is None:
        sys.exit(f"找不到词条：{args.ref!r}")

    pairs = _all_guess_pairs(conn)
    guess_index = build_words_index(pairs)
    guess_map = dict(pairs)
    parsed = _parsed_for(r)

    if args.json:
        out = {
            "id": r["id"],
            "word": r["word"],
            "colorIdx": r["color_idx"],
            "guessZh": r["guess_zh"],
            "definitionRaw": r["definition_raw"],
            "definition": parsed,
            "rendered": render_definition_struct(parsed, guess_index),
            "updatedAt": r["updated_at"],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    guess = f"  →{r['guess_zh']}" if r["guess_zh"] else "  （未推测）"
    print(f"#{r['id']}  {r['word']}{guess}")
    # if r["color_idx"] is not None:
    #     print(f"colorIdx: {r['color_idx']}    updated: {r['updated_at']}")
    print(f"\n[原文] {r['definition_raw']}")
    warns = parsed.get("parseWarnings") or []
    if parsed.get("error"):
        print("[警告] 解析结果为 error，请核对原文")
    for w in warns:
        print(f"[警告] {w}")
    if not args.raw:
        print("\n[释义]")
        for line in _rendered_lines(r, guess_index, guess_map):
            print(line)


def cmd_guesses(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = conn.execute(
        "SELECT id, word, guess_zh FROM entries "
        "WHERE guess_zh IS NOT NULL AND trim(guess_zh) <> '' ORDER BY word ASC"
    ).fetchall()
    if args.json:
        print(json.dumps(
            [{"id": r["id"], "word": r["word"], "guessZh": r["guess_zh"]} for r in rows],
            ensure_ascii=False, indent=2,
        ))
        return
    for r in rows:
        print(f"{r['word']}\t{r['guess_zh']}")
    print(f"\n({len(rows)} 个已推测词)")


def cmd_set(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    r = _resolve(conn, args.ref)
    if r is None:
        sys.exit(f"找不到词条：{args.ref!r}")
    val = args.guess.strip()
    conn.execute(
        "UPDATE entries SET guess_zh = ?, updated_at = datetime('now') WHERE id = ?",
        (None if val == "" else val, r["id"]),
    )
    conn.commit()
    shown = val if val else "(已清空)"
    print(f"已保存 #{r['id']} {r['word']} 的推测：{shown}")


def cmd_stats(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    total = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
    guessed = conn.execute(
        "SELECT count(*) FROM entries WHERE guess_zh IS NOT NULL AND trim(guess_zh) <> ''"
    ).fetchone()[0]
    info = {
        "db": str(args.db),
        "total": total,
        "guessed": guessed,
        "remaining": total - guessed,
        "posLexemes": list(PART_OF_SPEECH_LEXEMES),
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    print(f"数据库：{args.db}")
    print(f"词条总数：{total}    已推测：{guessed}    未推测：{total - guessed}")
    print(f"词性标记：{', '.join(PART_OF_SPEECH_LEXEMES)}")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ginger",
        description="Ginger 词典查词 CLI（直接读 SQLite，语义同前端）。",
    )
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"SQLite 路径（默认 {DEFAULT_DB}）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("word", help="按词条搜索（前缀/中缀/后缀）")
    sp.add_argument("query")
    sp.add_argument("--match", choices=["prefix", "infix", "suffix"], default="prefix")
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_word)

    sp = sub.add_parser("def", help="搜索释义中作为整词出现某词的词条")
    sp.add_argument("word")
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_def)

    sp = sub.add_parser("pos", help="搜索含某词性块的词条（如 k. 或 sj.）")
    sp.add_argument("pos")
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_pos)

    sp = sub.add_parser("abbr", help="列出全部词性标记及其中文含义")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_abbr)

    sp = sub.add_parser("translate", help="分词并用已推测词义渲染任意 Ginger 句子")
    sp.add_argument("text")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("show", help="查看词条详情（id 或精确词形）")
    sp.add_argument("ref")
    sp.add_argument("--raw", action="store_true", help="只看 Ginger 原文，不做中文替换")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("guesses", help="列出全部已推测词（即 gloss 替换词典）")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_guesses)

    sp = sub.add_parser("set", help="设置/清空某词的中文推测（写库）")
    sp.add_argument("ref")
    sp.add_argument("guess", help="中文推测，传空串 '' 表示清空")
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("stats", help="词典统计概览")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stats)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    conn = _connect(args.db)
    try:
        args.func(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
