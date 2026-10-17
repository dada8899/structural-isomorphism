"""Synthetic minimal DOM fixtures, not a whole article or acquired Source.

Only the necessary headline/attribution metadata and plain numerical facts are
retained. Paragraph prose below is synthetic. Whole-raw acceptance is separately
checked in private evidence; no private original or filesystem path lives here.
"""
import ast
import hashlib
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import pytest
from research.source_adapters import mint_reported_bytes as mint

TITLE = "TikTok parent’s revenue grows as AI spending pressures profits"
PARAGRAPHS = (
    "ByteDance discussed activity in the first half of the year.",
    "Revenue increased to $120 billion during the period. Net profit eased to $20 billion.",
    "Last year, ByteDance noted annual revenue growth of 29% to $200 billion while net profit rose to $42 billion.",
)


def fixture_html(paragraphs=PARAGRAPHS):
    body = "".join('<div id="article-index-' + str(i) + '" class="storyParagraph "><p>' + text + '</p></div>'
                   for i, text in enumerate(paragraphs))
    return ('<!DOCTYPE html><html><head><link rel="canonical" href="' + mint.CANONICAL + '">'
            '<meta property="og:url" content="' + mint.CANONICAL + '">'
            '<meta property="article:published_time" content="' + mint.PUBLISHED + '">'
            '</head><body><div class="storyBox storyBoxSchema"><h1>' + TITLE + '</h1>'
            '<div class="authorDesc"> ' + mint.AUTHOR + '( with inputs from The Wall Street Journal)'
            '<div class="date">' + mint.DATE_TEXT + '</div></div>'
            '<div class="storyContent">' + body + '</div></div></body></html>').encode()


def parse(raw=None, **overrides):
    if raw is None:
        raw = fixture_html()
    args = {"profile": mint.PROFILE, "expected_raw_digest": hashlib.sha256(raw).hexdigest()}
    args.update(overrides)
    return mint.parse_mint_reported_bytes(raw, **args)


def test_selected_dom_facts_unknown_currency_and_exact_unicode_spans():
    raw = fixture_html()
    result = parse(raw).data()
    selected = "\n\n".join(PARAGRAPHS)
    assert result["extracted_text"] == selected
    assert result["extraction_digest"] == hashlib.sha256(selected.encode()).hexdigest()
    assert result["raw_digest"] == hashlib.sha256(raw).hexdigest()
    assert result["raw_bytes"] == len(raw)
    assert [v["metric"] for v in result["facts"]] == ["revenue", "net_profit", "revenue", "net_profit"]
    assert [v["value"] for v in result["facts"]] == ["120", "20", "200", "42"]
    assert all(v["normalized_currency"] is None and v["currency_status"] == "unknown" for v in result["facts"])
    assert all(v["currency_literal"] == "$" and v["unit_literal"] == v["unit"] == "billion" for v in result["facts"])
    assert all(v["evidence_basis"] == "media_estimate" and "not_stated" in v["accounting_basis"] for v in result["facts"])
    assert [v["period"]["grain"] for v in result["facts"]] == ["interim", "interim", "annual", "annual"]
    assert [v["period"]["end"] for v in result["facts"]] == ["2026-06-30", "2026-06-30", "2025-12-31", "2025-12-31"]
    for fact in result["facts"]:
        where = fact["locator"]
        start, end = where["value_span"]
        assert selected[start:end] == where["quote"] == fact["raw_literal"]
        a, b = where["paragraph_span"]
        assert selected[a:b] in PARAGRAPHS
        assert a <= start < end <= b
    assert "not_css_visibility" in result["extraction_scope"]
    assert result["metadata"]["publication_chain"] == "Mint_with_WSJ_inputs_one_chain"
    assert not any(key in result for key in ("source_id", "computed", "trusted", "may_send_to_provider", "permission", "FinancialObservation"))
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= mint.OUTPUT_CAP


def test_result_is_frozen_copy_data_not_a_capability():
    result = parse()
    data = result.data();data["facts"][0]["normalized_currency"] = "USD"
    assert result.data()["facts"][0]["normalized_currency"] is None
    assert "Revenue" not in repr(result)
    assert not any(hasattr(result, name) for name in ("send", "execute", "grant", "persist", "source"))


def test_entities_decomposed_unicode_and_whitespace_are_not_rewritten():
    paragraphs = list(PARAGRAPHS)
    paragraphs[0] = "ByteDance\t discussed cafe\u0301 activity\r\nin the first half of the year."
    raw = fixture_html(paragraphs).replace(b"$120", b"&#36;120")
    result = parse(raw).data()
    assert result["extracted_text"] == "\n\n".join(paragraphs)
    assert "cafe\u0301" in result["extracted_text"] and "caf\u00e9" not in result["extracted_text"]
    for fact in result["facts"]:
        start, end = fact["locator"]["value_span"]
        assert result["extracted_text"][start:end] == fact["raw_literal"]


@pytest.mark.parametrize("profile", [None, True, "other-url", "mint-wsj-bytedance-reported-20250916"])
def test_fixed_profile_only(profile):
    with pytest.raises(mint.MintReportedError) as err:parse(profile=profile)
    assert err.value.reason == "unsupported"


@pytest.mark.parametrize("digest", [None, False, "A" * 64, "x" * 64, "a" * 64, ""])
def test_expected_digest_is_strict_independent_data(digest):
    with pytest.raises(mint.MintReportedError) as err:parse(expected_raw_digest=digest)
    assert err.value.reason == "digest"


@pytest.mark.parametrize("mutation", ["title", "author", "visible_date", "published_year", "canonical", "og", "no_head", "missing_p", "truncated", "no_doctype", "extra_doctype"])
def test_all_required_header_and_structure_fail_after_rehash(mutation):
    raw = fixture_html()
    if mutation == "title":raw = raw.replace(TITLE.encode(), b"Different financial story")
    elif mutation == "author":raw = raw.replace(mint.AUTHOR.encode(), b"Other Writer")
    elif mutation == "visible_date":raw = raw.replace(b"16 Sep 2026", b"16 Sep 2025")
    elif mutation == "published_year":raw = raw.replace(mint.PUBLISHED.encode(), b"2025-09-16T14:51:54+05:30")
    elif mutation == "canonical":raw = raw.replace(('href="'+mint.CANONICAL+'"').encode(), b'href="https://example.invalid"')
    elif mutation == "og":raw = raw.replace(('content="'+mint.CANONICAL+'"').encode(), b'content="https://example.invalid"')
    elif mutation == "no_head":raw = raw.replace(b"<head>", b"<section>").replace(b"</head>", b"</section>")
    elif mutation == "missing_p":raw = raw.replace(b'<div id="article-index-1"', b'<div id="missing-1"')
    elif mutation == "truncated":raw = raw[:-10]
    elif mutation == "no_doctype":raw = raw.replace(b"<!DOCTYPE html>", b"")
    else:raw = b"<!DOCTYPE html>" + raw
    with pytest.raises(mint.MintReportedError):parse(raw)


@pytest.mark.parametrize("kind", ["paragraph", "paragraph_outside", "head_meta", "attribute", "title", "p", "author", "canonical"])
def test_duplicate_or_scope_ambiguity_is_whole_failure(kind):
    raw = fixture_html()
    if kind == "paragraph":raw = raw.replace(b'</body>', b'<div id="article-index-1" class="storyParagraph"><p>duplicate</p></div></body>')
    elif kind == "paragraph_outside":raw = raw.replace(b'<div class="storyContent">', b'<div id="article-index-1"></div><div class="storyContent">')
    elif kind == "head_meta":raw = raw.replace(b'</head>', ('<meta property="article:published_time" content="'+mint.PUBLISHED+'"></head>').encode())
    elif kind == "attribute":raw = raw.replace(b'id="article-index-1"', b'id="article-index-1" id="another"')
    elif kind == "title":raw = raw.replace(b'</h1>', b'</h1><h1>duplicate</h1>')
    elif kind == "p":raw = raw.replace(b'</p>', b'</p><p>extra</p>', 1)
    elif kind == "author":raw = raw.replace(b'<div class="storyContent">', b'<div class="authorDesc">duplicate</div><div class="storyContent">')
    else:raw = raw.replace(b'</head>', ('<link rel="canonical" href="'+mint.CANONICAL+'"></head>').encode())
    with pytest.raises(mint.MintReportedError):parse(raw)


@pytest.mark.parametrize("attribute", ['hidden', 'aria-hidden="true"', 'class="hidden"', 'style="display:none"',
    'style="visibility:hidden"', 'style="opacity:0.0"', 'style="display:/**/none"', 'style="d\\69splay:none"', 'onload="alert(1)"'])
def test_known_hidden_or_event_content_is_rejected(attribute):
    raw = fixture_html().replace(b'<div id="article-index-1"', ('<div '+attribute+' id="article-index-1"').encode())
    with pytest.raises(mint.MintReportedError):parse(raw)


@pytest.mark.parametrize("tag", ["script", "template", "style", "noscript", "iframe", "svg", "form"])
def test_active_or_nontext_selected_children_never_supply_numbers(tag):
    raw = fixture_html().replace(PARAGRAPHS[1].encode(), ('<'+tag+'>'+PARAGRAPHS[1]+'</'+tag+'>').encode())
    with pytest.raises(mint.MintReportedError):parse(raw)


def test_external_scripts_and_json_do_not_supply_a_missing_body():
    raw = fixture_html()
    script = ('<script src="https://example.invalid/tracker">'+PARAGRAPHS[1]+'</script>').encode()
    with patch("socket.socket", side_effect=AssertionError("no fetch")):
        assert parse(raw.replace(b'</body>', script+b'</body>')).data()["facts"][0]["value"] == "120"
        with pytest.raises(mint.MintReportedError):parse(raw.replace(PARAGRAPHS[1].encode(), b"").replace(b'</body>', script+b'</body>'))


@pytest.mark.parametrize("old,new", [
    ("$120 billion", "$120 million"), ("$120 billion", "$120 billion billion"),
    ("$120 billion", "$120,000 billion"), ("$120 billion", "$１２０ billion"),
    ("$120 billion", "$12\u200b0 billion"), ("$120 billion", "$120* billion"),
    ("$120 billion", "$NaN billion"), ("$120 billion", "$-120 billion"),
    ("Net profit", "Operating profit"), ("Net profit eased", "Net profit for TikTok eased"),
    ("first half of the year", "full year"), ("first half of the year", "second half of the year"),
    ("during the period", "during the period in 2025"), ("during the period", "during the period FY2026"),
    ("Last year, ByteDance", "In 2026, ByteDance"), ("annual revenue", "H1 revenue"),
    ("$200 billion", "$200 USD billion"), ("$42 billion", "$42 billion and $1 billion"),
])
def test_metric_period_unit_and_amount_ambiguity_after_rehash(old,new):
    raw = fixture_html().replace(old.encode(), new.encode())
    with pytest.raises(mint.MintReportedError):parse(raw)


@pytest.mark.parametrize("amount", ["0", "120.125", "999999999999999999"])
def test_decimal_literal_is_parsed_not_answer_hardcoded(amount):
    raw = fixture_html().replace(b"$120 billion", ("$"+amount+" billion").encode())
    result = parse(raw).data()
    assert result["facts"][0]["value"] == amount
    assert result["facts"][0]["normalized_currency"] is None


@pytest.mark.parametrize("kind", ["raw", "nodes", "depth", "text_utf8", "bad_utf8", "declaration"])
def test_resource_limits_are_enforced_and_non_utf8_safe(kind):
    raw = fixture_html()
    if kind == "raw":raw = b"x" * (mint.RAW_CAP+1)
    elif kind == "nodes":raw = raw.replace(b'</body>', b'<i></i>'*(mint.MAX_NODES+1)+b'</body>')
    elif kind == "depth":raw = raw.replace(b'</body>', b'<section>'*129+b'</section>'*129+b'</body>')
    elif kind == "text_utf8":raw = fixture_html((PARAGRAPHS[0]+"观"*22000, *PARAGRAPHS[1:]))
    elif kind == "bad_utf8":raw = raw.replace(b"activity", b"\xed\xa0\x80")
    else:raw = raw.replace(b'<!DOCTYPE html>', b'<!DOCTYPE html [<!ENTITY ex SYSTEM "file:///private/secret">]>')
    with pytest.raises(mint.MintReportedError) as err:parse(raw)
    if kind in {"raw","nodes","depth","text_utf8"}:assert err.value.reason == "resource"


@pytest.mark.parametrize("caller", ["value", "json"])
@pytest.mark.parametrize("failure", ["digest", "dom", "decode"])
def test_safe_failure_has_no_outer_exception_or_private_input(caller,failure):
    canary = "PRIVATE-MINT-CANARY"
    try:
        if caller == "value":raise ValueError(canary)
        json.loads(canary)
    except ValueError:
        raw = fixture_html()
        if failure == "dom":raw = raw.replace(b"article-index-1", canary.encode())
        if failure == "decode":raw = b"\xed\xa0\x80" + raw
        with pytest.raises(mint.MintReportedError) as stopped:
            parse(raw, **({"expected_raw_digest":canary} if failure == "digest" else {}))
        safe = stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None and safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


def test_pure_no_external_io_env_loader_or_authority():
    raw = fixture_html()
    with patch("socket.socket",side_effect=AssertionError("no network")),patch("subprocess.Popen",side_effect=AssertionError("no tool")),patch("sqlite3.connect",side_effect=AssertionError("no DB")),patch("builtins.open",side_effect=AssertionError("no file")):
        assert parse(raw).data()["facts"][0]["normalized_currency"] is None
    tree = ast.parse(Path(mint.__file__).read_text());modules=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):modules.update(v.name for v in node.names)
        if isinstance(node,ast.ImportFrom):modules.add(node.module)
    assert modules=={"dataclasses","html.parser","hashlib","json","re","unicodedata"}
    with pytest.raises(TypeError):mint.parse_mint_reported_bytes(raw,profile=mint.PROFILE,expected_raw_digest=hashlib.sha256(raw).hexdigest(),currency="USD")


@pytest.mark.parametrize("kind", ["outside_root", "misplaced_doctype", "outside_p", "selected_comment", "meta_template", "hidden_canonical", "prefix_other_entity", "meta_hidden"])
def test_complete_scope_has_no_unparsed_corrections_or_hidden_metadata(kind):
    raw = fixture_html()
    if kind == "outside_root":raw += b'<div>extra document</div>'
    elif kind == "misplaced_doctype":raw = raw.replace(b'<!DOCTYPE html>', b'').replace(b'<body>', b'<body><!DOCTYPE html>')
    elif kind == "outside_p":raw = raw.replace(b'<div id="article-index-1" class="storyParagraph ">', b'<div id="article-index-1" class="storyParagraph ">unparsed correction')
    elif kind == "selected_comment":raw = raw.replace(PARAGRAPHS[1].encode(), b'<!--comment-->'+PARAGRAPHS[1].encode())
    elif kind == "meta_template":raw = raw.replace(b'<link rel="canonical"', b'<template><link rel="canonical"').replace(b'<meta property="og:url"', b'</template><meta property="og:url"')
    elif kind == "hidden_canonical":raw = raw.replace(b'<link rel="canonical"', b'<link hidden rel="canonical"')
    elif kind == "prefix_other_entity":raw = raw.replace(PARAGRAPHS[1].encode(), b'Another entity said '+PARAGRAPHS[1].encode())
    else:raw = raw.replace(b'<meta property="article:published_time"', b'<meta aria-hidden="true" property="article:published_time"')
    with pytest.raises(mint.MintReportedError):parse(raw)
