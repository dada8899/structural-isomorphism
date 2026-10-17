"""One fixed Mint/WSJ HTML profile, DATA only; no fetching or source authority.

Selected DOM text is not a claim about CSS visibility or publisher permission.
Dollar signs remain unknown currency. This module creates no FinancialObservation.
"""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import hashlib
import json
import re
import unicodedata

PROFILE = "mint-wsj-bytedance-reported-20260916"
URL = "https://www.livemint.com/global/tiktok-parent-s-revenue-grows-as-ai-spending-pressures-profits/amp-11789549975990.html"
CANONICAL = "https://www.wsj.com/tech/tiktok-parents-revenue-grows-as-ai-spending-pressures-profits-d16c482e"
RAW_CAP = DECODED_CAP = 2 * 1024 * 1024
TEXT_CAP = 64 * 1024
OUTPUT_CAP = 128 * 1024
MAX_NODES, MAX_DEPTH = 50000, 128
TITLE_DIGEST = "74efed800d9bf9bc96d5c6a68a7ad07c5ee442a230eb13a70313e14738f3a134"
PUBLISHED = "2026-09-16T14:51:54+05:30"
DATE_TEXT = "Published16 Sep 2026, 02:51 PM IST"
AUTHOR = "Raffaele Huang"
REVISION = "mint-selected-dom-3p-v1"
# Full retained publisher paragraphs with ONLY monetary values replaced by
# <amount>. Hashes avoid copying the whole copyrighted prose into source code.
# These are not runtime options and grant no acquisition/source authority.
_CONTEXT_DIGESTS = (
    "9812bb307323eb95536d39f70135a004f1666283501f48b54c890022efe81407",
    "cec6c9c1fa7f86fde25e64226ff35a99ed82ce5890a541d92e43c5d94b2e20e1",
    "8fb0cfd31a5afc02f28e834fdebfefce34bfcdbe3e188cc9eef7a895eaa4e521",
)
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_UNSAFE = frozenset("script style template noscript iframe object embed form input button img br svg math".split())
_REASONS = frozenset(("unsupported", "ambiguous", "digest", "resource"))


class MintReportedError(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in _REASONS else "unsupported"
        super().__init__("Reported financial data could not be validated.")


def _fail(reason):
    try:
        raise MintReportedError(reason) from None
    except MintReportedError as safe:
        safe.__context__ = None
        safe.__cause__ = None
        safe.__suppress_context__ = False
        raise


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(eq=False)
class _Node:
    tag: str
    attrs: dict
    parent: object
    children: list = field(default_factory=list)


class _Document(HTMLParser):
    """Build counts/depth while parsing, not after building an unlimited tree."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {}, None)
        self.stack = [self.root]
        self.nodes = []
        self.count = 0
        self.doctype = 0

    def tick(self):
        self.count += 1
        if self.count > MAX_NODES:
            _fail("resource")

    def handle_decl(self, decl):
        self.tick()
        if decl.casefold() != "doctype html" or self.doctype or len(self.stack) != 1 or self.nodes:
            _fail("unsupported")
        self.doctype += 1

    def unknown_decl(self, _):
        _fail("unsupported")

    def handle_pi(self, _):
        _fail("unsupported")

    def handle_comment(self, _):
        self.tick()
        self.stack[-1].children.append(None)

    def handle_starttag(self, tag, attrs):
        self.tick()
        if len(attrs) != len({k for k, _ in attrs}):
            _fail("ambiguous")
        node = _Node(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag not in _VOID:
            if len(self.stack) > MAX_DEPTH:
                _fail("resource")
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            _fail("ambiguous")
        self.stack.pop()

    def handle_data(self, value):
        self.tick()
        self.stack[-1].children.append(value)

    def finish(self):
        self.close()
        if len(self.stack) != 1 or self.doctype != 1:
            _fail("ambiguous")
        if any((type(c) is _Node and c.tag != "html") or (type(c) is str and c.strip())
               for c in self.root.children):
            _fail("ambiguous")


def _classes(node):
    return (node.attrs.get("class") or "").split()


def _within(node, ancestor):
    current = node.parent
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _unique(nodes):
    nodes = list(nodes)
    if len(nodes) != 1:
        _fail("ambiguous")
    return nodes[0]


def _safe(node):
    current = node
    while current is not None:
        if current.tag in _UNSAFE:
            _fail("unsupported")
        attrs = current.attrs
        if "hidden" in attrs or (attrs.get("aria-hidden") or "").casefold() in {"true", "1"}:
            _fail("ambiguous")
        if set(_classes(current)) & {"hidden", "d-none", "sr-only"}:
            _fail("ambiguous")
        style = re.sub(r"\s+", "", attrs.get("style") or "").casefold()
        if "\\" in style or "/*" in style or "url(" in style:
            _fail("ambiguous")
        if re.search(r"(?:^|;)(?:display:none|visibility:(?:hidden|collapse)|content-visibility:hidden|opacity:(?:0(?:\.0*)?|\.0+))(?:;|$|!)", style):
            _fail("ambiguous")
        for key, value in attrs.items():
            if key.startswith("on"):
                _fail("unsupported")
            if key in {"href", "src", "action", "xlink:href"}:
                target = re.sub(r"\s+", "", value or "").casefold()
                if target.startswith(("javascript:", "data:", "file:", "vbscript:")):
                    _fail("unsupported")
        current = current.parent


def _text(node, cap=TEXT_CAP):
    chunks = []
    size = 0
    stack = [node]
    while stack:
        item = stack.pop()
        if type(item) is _Node:
            _safe(item)
            stack.extend(reversed(item.children))
        elif type(item) is str:
            if any(unicodedata.category(c) in {"Cf", "Cs"} or unicodedata.category(c) == "Cc" and c not in "\t\n\r" for c in item):
                _fail("unsupported")
            size += len(item.encode("utf-8"))
            if size > cap:
                _fail("resource")
            chunks.append(item)
        else:
            _fail("ambiguous")
    return "".join(chunks)


_DECIMAL = r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?"
_AMOUNT = r"(?P<literal>\$(?P<value>" + _DECIMAL + r") billion)"


def _context_slots(paragraphs):
    slots = []
    for index, paragraph in enumerate(paragraphs):
        matches = list(re.finditer(_AMOUNT, paragraph))
        if len(matches) != (0 if index == 0 else 2):
            _fail("ambiguous")
        parts = []
        cursor = 0
        for match in matches:
            start, end = match.span("value")
            parts.extend((paragraph[cursor:start], "<amount>"))
            cursor = end
        parts.append(paragraph[cursor:])
        # Compare the ENTIRE context, including entity, period, unit suffixes,
        # qualifications and punctuation. No unexamined prefix/suffix survives.
        if _hash("".join(parts).encode("utf-8")) != _CONTEXT_DIGESTS[index]:
            _fail("ambiguous")
        slots.append(matches)
    return slots


@dataclass(frozen=True, slots=True)
class MintReportedData:
    _json: bytes = field(repr=False)

    def data(self):
        return json.loads(self._json)


def _parse(raw, profile, expected_raw_digest):
    if type(raw) is not bytes or type(profile) is not str or profile != PROFILE:
        _fail("unsupported")
    if len(raw) > RAW_CAP:
        _fail("resource")
    if type(expected_raw_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_raw_digest) is None:
        _fail("digest")
    if _hash(raw) != expected_raw_digest:
        _fail("digest")
    text = raw.decode("utf-8", errors="strict")
    if len(text.encode("utf-8")) > DECODED_CAP:
        _fail("resource")
    document = _Document()
    document.feed(text)
    document.finish()
    html = _unique(n for n in document.nodes if n.tag == "html" and n.parent is document.root)
    head = _unique(n for n in document.nodes if n.tag == "head" and n.parent is html)
    body = _unique(n for n in document.nodes if n.tag == "body" and n.parent is html)
    box = _unique(n for n in document.nodes if {"storyBox", "storyBoxSchema"} <= set(_classes(n)) and _within(n, body))
    content = _unique(n for n in document.nodes if "storyContent" in _classes(n) and _within(n, box))
    title_node = _unique(n for n in document.nodes if n.tag == "h1" and _within(n, box))
    title = _text(title_node, 1000)
    if _hash(title.encode()) != TITLE_DIGEST:
        _fail("ambiguous")
    canonical = _unique(n for n in document.nodes if n.tag == "link" and n.attrs.get("rel") == "canonical" and _within(n, head))
    og = _unique(n for n in document.nodes if n.tag == "meta" and n.attrs.get("property") == "og:url" and _within(n, head))
    published = _unique(n for n in document.nodes if n.tag == "meta" and n.attrs.get("property") == "article:published_time" and _within(n, head))
    for metadata_node in (canonical, og, published):
        _safe(metadata_node)
    if canonical.attrs.get("href") != CANONICAL or og.attrs.get("content") != CANONICAL or published.attrs.get("content") != PUBLISHED:
        _fail("ambiguous")
    author = _unique(n for n in document.nodes if "authorDesc" in _classes(n) and _within(n, box))
    date = _unique(n for n in document.nodes if "date" in _classes(n) and _within(n, author))
    author_text, date_text = _text(author, 1000), _text(date, 200)
    if date_text != DATE_TEXT or author_text != " " + AUTHOR + "( with inputs from The Wall Street Journal)" + DATE_TEXT:
        _fail("ambiguous")
    paragraphs = []
    for ordinal in range(3):
        pid = "article-index-" + str(ordinal)
        scope = _unique(n for n in document.nodes if n.attrs.get("id") == pid)
        if not _within(scope, content) or "storyParagraph" not in _classes(scope):
            _fail("ambiguous")
        _safe(scope)
        paragraph = _unique(n for n in document.nodes if n.tag == "p" and _within(n, scope))
        if paragraph.parent is not scope or any(c is not paragraph and (type(c) is not str or c.strip())
                                               for c in scope.children):
            _fail("ambiguous")
        value = _text(paragraph)
        if not value:
            _fail("ambiguous")
        paragraphs.append(value)
    selected = "\n\n".join(paragraphs)
    if len(selected.encode()) > TEXT_CAP:
        _fail("resource")
    slots = _context_slots(paragraphs)
    facts = []
    bases = (0, len(paragraphs[0]) + 2, len(paragraphs[0]) + len(paragraphs[1]) + 4)
    # Context hashes above fix the exact metric/period/entity of these four
    # slots; only their bounded decimal monetary values may differ.
    for ordinal, slot, metric, year in ((1, 0, "revenue", 2026), (1, 1, "net_profit", 2026),
                                       (2, 0, "revenue", 2025), (2, 1, "net_profit", 2025)):
        value = paragraphs[ordinal]
        match = slots[ordinal][slot]
        start, end = match.span("literal")
        start, end = start + bases[ordinal], end + bases[ordinal]
        facts.append({"metric": metric, "raw_literal": match["literal"], "value": match["value"],
                      "currency_literal": "$", "normalized_currency": None, "currency_status": "unknown",
                      "unit_literal": "billion", "unit": "billion", "entity_scope": "ByteDance_group_reported",
                      "accounting_basis": "not_stated_in_selected_dom_text", "evidence_basis": "media_estimate",
                      "period": {"start": str(year) + "-01-01", "end": str(year) + ("-06-30" if ordinal == 1 else "-12-31"),
                                 "grain": "interim" if ordinal == 1 else "annual", "basis": "paragraph_context_and_original_publication_date"},
                      "locator": {"paragraph_id": "article-index-" + str(ordinal),
                                  "paragraph_span": [bases[ordinal], bases[ordinal] + len(value)],
                                  "value_span": [start, end], "quote": match["literal"]}})
    output = {"schema_version": "mint-reported-data-v1", "profile": PROFILE, "parser_revision": REVISION,
              "raw_digest": expected_raw_digest, "raw_bytes": len(raw), "source_url": URL,
              "metadata": {"title": title, "author": AUTHOR, "author_dom_text": author_text,
                           "published_at": PUBLISHED, "published_dom_text": date_text,
                           "canonical_reference": CANONICAL, "publication_chain": "Mint_with_WSJ_inputs_one_chain"},
              "extraction_scope": "selected_dom_text_paragraphs_0_1_2_not_css_visibility",
              "extracted_text": selected, "extraction_digest": _hash(selected.encode()), "facts": facts,
              "limitations": ["Data parsing does not attest source acquisition, permission, computation or source independence.",
                               "Dollar currency is unresolved; USD financial consumption remains closed.",
                               "Media-reported net profit is not operating profit; accounting basis and conflicts remain unverified."]}
    encoded = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > OUTPUT_CAP:
        _fail("resource")
    return MintReportedData(encoded)


def parse_mint_reported_bytes(raw, *, profile, expected_raw_digest):
    """Deterministic fixed HTML content parser. Expectations grant no authority."""
    reason = None
    try:
        result = _parse(raw, profile, expected_raw_digest)
    except MintReportedError:
        raise
    except (ValueError, TypeError, KeyError, AssertionError, OverflowError, RecursionError, UnicodeError):
        reason = "unsupported"
    if reason:
        _fail(reason)
    return result
