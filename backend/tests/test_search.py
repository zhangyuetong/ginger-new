from app.parser import entry_has_pos, is_valid_pos_lexeme, normalize_pos_query, parse_definition
from app.render import text_contains_lemma


def test_text_contains_lemma_word_boundary():
    text = "kyv kysi. kakauka kyso."
    assert text_contains_lemma(text, "kyv")
    assert text_contains_lemma(text, "kysi.")
    assert not text_contains_lemma(text, "ky")


def test_text_contains_lemma_not_inside_longer_token():
    body = "yra lela. yra ja asj. kat yra"
    assert not text_contains_lemma(body, "sj.")


def test_normalize_pos_query():
    assert normalize_pos_query("k") == "k."
    assert normalize_pos_query("sj.") == "sj."
    assert normalize_pos_query("  hh.  ") == "hh."


def test_is_valid_pos_lexeme():
    assert is_valid_pos_lexeme("k.")
    assert not is_valid_pos_lexeme("asj.")
    assert not is_valid_pos_lexeme("")


def test_entry_has_pos_any_block():
    raw = "k. 1 kyv kysi. sj. kyv in sxresh. k. kuuee."
    parsed = parse_definition(raw)
    assert entry_has_pos(parsed, "k.")
    assert entry_has_pos(parsed, "sj.")
    assert not entry_has_pos(parsed, "e.")
