from app.parser import parse_definition


EXAMPLE = "k. 1 kyv kysi. 2 kakauka kyso. sj. kyv in sxresh in hgasi kyv f gega. k. kuuee."


def test_typical_definition_parse():
    d = parse_definition(EXAMPLE)
    assert d["error"] is False
    blocks = d["posBlocks"]
    assert blocks[0]["pos"] == "k."
    assert blocks[0]["senses"][0]["n"] == 1
    assert blocks[0]["senses"][0]["text"] == "kyv kysi."
    assert blocks[0]["senses"][1]["n"] == 2
    assert blocks[0]["senses"][1]["text"] == "kakauka kyso."
    assert blocks[1]["pos"] == "sj."
    assert blocks[1]["senses"][0]["n"] is None
    assert "kyv in sxresh" in blocks[1]["senses"][0]["text"]
    assert blocks[2]["pos"] == "k."
    assert blocks[2]["senses"][0]["text"] == "kuuee."


def test_empty_definition():
    d = parse_definition("   ")
    assert d["error"] is True
    assert any("Empty" in w for w in d["parseWarnings"])


def test_unstructured_fallback():
    d = parse_definition("just some text without POS markers abc")
    assert d["posBlocks"][0]["senses"][0]["text"]


def test_sentence_periods_vs_pos_whitelist():
    s = "sj. yra lela. yra ja asj. kat yra o gta z ja ahk je hji."
    d = parse_definition(s)
    assert d["error"] is False
    assert len(d["posBlocks"]) == 1
    assert d["posBlocks"][0]["pos"] == "sj."
    assert d["posBlocks"][0]["senses"][0]["n"] is None
    body = d["posBlocks"][0]["senses"][0]["text"]
    assert "asj." in body
    assert "lela." in body
