"""Bounded, data-only SMIC bbox locations; never extraction or source proof."""
from dataclasses import dataclass, field
from decimal import Context, Decimal, localcontext
import hashlib
import json
import re
import unicodedata

PROFILE = "smic-2026q1-results-pdf"
INPUT_CAP = 4 * 1024 * 1024
TEXT_CAP = 1024 * 1024
OUTPUT_CAP = 128 * 1024
EXTRACTION_VERSION = "smic-bbox-text-v1"
TITLE = "CONDENSED CONSOLIDATED STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME"
UNIT = "(In US$ thousands)"
PERIOD = "For the three months ended"
CURRENT = "March 31, 2026"
PREVIOUS = "December 31, 2025"
ROWS = (("revenue", "Revenue"), ("operating_profit", "Profit from operations"),
        ("net_profit", "Profit for the period"))
_KEYS = ("x_min", "y_min", "x_max", "y_max")
_REASONS = frozenset(("unsupported", "ambiguous", "digest", "dependency", "resource"))


class CorporateParseError(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in _REASONS else "unsupported"
        super().__init__("Corporate number data could not be validated.")


def _fail(reason):
    try:
        raise CorporateParseError(reason) from None
    except CorporateParseError as safe:
        safe.__context__ = None
        safe.__cause__ = None
        safe.__suppress_context__ = False
        raise


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail("digest")
    return value


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        _fail("unsupported")


def _json_data(payload):
    if type(payload) is bytes:
        if len(payload) > INPUT_CAP:
            _fail("resource")
        payload = payload.decode("utf-8")
    if type(payload) is str:
        if len(payload) > INPUT_CAP or len(payload.encode("utf-8")) > INPUT_CAP:
            _fail("resource")

        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    _fail("unsupported")
                out[key] = value
            return out

        def reject(_):
            _fail("unsupported")

        def integer(value):
            if len(value.lstrip("-")) > 6:
                _fail("resource")
            return int(value)

        payload = json.loads(payload, object_pairs_hook=pairs, parse_float=reject,
                             parse_constant=reject, parse_int=integer)
    if type(payload) is not dict:
        _fail("unsupported")
    stack = [(payload, 0)]
    count = size = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if depth > 14 or count > 160000:
            _fail("resource")
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str:
                    _fail("unsupported")
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif type(value) is list:
            stack.extend((child, depth + 1) for child in value)
        elif type(value) is str:
            size += len(value.encode("utf-8"))
            if size > INPUT_CAP:
                _fail("resource")
        elif type(value) is int:
            if abs(value) > 999999:
                _fail("resource")
        else:
            _fail("unsupported")
    if len(canonical(payload)) > INPUT_CAP:
        _fail("resource")
    return payload


def _coordinate(value):
    if type(value) is not str or re.fullmatch(r"(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,6})?", value) is None:
        _fail("unsupported")
    return Decimal(value)


def _box(data, width, height):
    _fields(data, _KEYS)
    x0, y0, x1, y1 = (_coordinate(data[key]) for key in _KEYS)
    if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
        _fail("ambiguous")
    return x0, y0, x1, y1


def _line_key(box):
    return box[1], box[0], box[3], box[2]


def _word(value):
    if (type(value) is not str or not value or len(value) > 512 or value.isspace()
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)):
        _fail("unsupported")
    return value


def _number(text):
    if text in ("-", "—"):
        return None, "explicit_dash"
    negative = text.startswith("(") and text.endswith(")")
    value = text[1:-1] if negative else text
    if re.fullmatch(r"(?:0|[1-9][0-9]{0,17}|[1-9][0-9]{0,2}(?:,[0-9]{3}){1,5})(?:\.[0-9]{1,6})?", value) is None:
        _fail("ambiguous")
    value = value.replace(",", "")
    number = Decimal(value)
    if number > Decimal("1e18"):
        _fail("resource")
    if negative and number:
        value = "-" + value
    return value, None


@dataclass(frozen=True, slots=True)
class CorporateNumberData:
    """Content data only. Hashes, boxes and parser success attest no origin."""
    _json: bytes = field(repr=False)

    def data(self):
        return json.loads(self._json)


def _parse(payload, expected_raw_digest, expected_bbox_digest,
           expected_source_bbox_digest, expected_extractor_revision):
    raw_digest = _digest(expected_raw_digest)
    bbox_digest = _digest(expected_bbox_digest)
    source_digest = _digest(expected_source_bbox_digest)
    if (type(expected_extractor_revision) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", expected_extractor_revision) is None):
        _fail("dependency")
    data = _json_data(payload)
    _fields(data, ("schema_version", "profile", "raw_digest", "source_bbox_digest",
                   "extractor_revision", "source_page_count", "pages"))
    if data["schema_version"] != "corporate-bbox-data-v1" or data["profile"] != PROFILE:
        _fail("unsupported")
    if data["raw_digest"] != raw_digest or data["source_bbox_digest"] != source_digest:
        _fail("digest")
    if data["extractor_revision"] != expected_extractor_revision:
        _fail("dependency")
    if hashlib.sha256(canonical(data)).hexdigest() != bbox_digest:
        _fail("digest")
    total = data["source_page_count"]
    if type(total) is not int or not 9 <= total <= 200:
        _fail("resource")
    pages = data["pages"]
    if type(pages) is not list or not 1 <= len(pages) <= 200:
        _fail("resource")
    line_total = word_total = 0
    prepared = []
    for page in pages:
        _fields(page, ("page_index", "width", "height", "lines"))
        index = page["page_index"]
        if type(index) is not int or not 1 <= index <= total:
            _fail("unsupported")
        width, height = _coordinate(page["width"]), _coordinate(page["height"])
        if width <= 0 or height <= 0:
            _fail("unsupported")
        if type(page["lines"]) is not list or not page["lines"]:
            _fail("ambiguous")
        lines = []
        for line in page["lines"]:
            line_total += 1
            if line_total > 12000:
                _fail("resource")
            _fields(line, ("box", "words"))
            box = _box(line["box"], width, height)
            if type(line["words"]) is not list or not line["words"]:
                _fail("ambiguous")
            words = []
            for item in line["words"]:
                word_total += 1
                if word_total > 20000:
                    _fail("resource")
                _fields(item, ("box", "text"))
                word_box = _box(item["box"], width, height)
                if not (box[0] <= word_box[0] < word_box[2] <= box[2]
                        and box[1] <= word_box[1] < word_box[3] <= box[3]):
                    _fail("ambiguous")
                words.append({"box": word_box, "source_box": item["box"], "text": _word(item["text"])})
            words.sort(key=lambda w: w["box"])
            if len({w["box"] for w in words}) != len(words):
                _fail("ambiguous")
            union = (min(w["box"][0] for w in words), min(w["box"][1] for w in words),
                     max(w["box"][2] for w in words), max(w["box"][3] for w in words))
            if box != union:
                _fail("ambiguous")
            lines.append({"box": box, "source_box": line["box"], "words": words,
                          "text": " ".join(w["text"] for w in words)})
        lines.sort(key=lambda line: _line_key(line["box"]))
        if len({line["box"] for line in lines}) != len(lines):
            _fail("ambiguous")
        prepared.append((index, page, lines))
    prepared.sort(key=lambda p: p[0])
    if len({p[0] for p in prepared}) != len(prepared):
        _fail("ambiguous")
    # Canonical text covers ONLY supplied bbox pages/lines, not the whole PDF.
    chunks = []
    cursor = 0
    target = None
    for page_no, page, lines in prepared:
        if chunks:
            chunks.append("\n\n")
            cursor += 2
        for ordinal, line in enumerate(lines):
            if ordinal:
                chunks.append("\n")
                cursor += 1
            line["span"] = [cursor, cursor + len(line["text"])]
            for word in line["words"]:
                word["span"] = [cursor, cursor + len(word["text"])]
                cursor += len(word["text"]) + 1
            cursor -= 1
            chunks.append(line["text"])
        if page_no == 9:
            target = (page, lines)
    text = "".join(chunks)
    if len(text.encode("utf-8")) > TEXT_CAP:
        _fail("resource")
    if target is None:
        _fail("ambiguous")
    page, lines = target
    if Decimal(page["width"]) != Decimal("595.320000") or Decimal(page["height"]) != Decimal("841.920000"):
        _fail("unsupported")

    def unique(label):
        found = [line for line in lines if line["text"] == label]
        if len(found) != 1:
            _fail("ambiguous")
        return found[0]

    title, unit, period, current, previous, footer = map(unique, (TITLE, UNIT, PERIOD, CURRENT, PREVIOUS, "- 9 -"))
    if not (title["box"][3] < unit["box"][1] < period["box"][1] < current["box"][1]
            and current["box"][1::2] == previous["box"][1::2] and previous["box"][3] < footer["box"][1]):
        _fail("ambiguous")

    def column(box):
        center = (box[0] + box[2]) / 2
        if center in (Decimal(350), Decimal(448)):
            _fail("ambiguous")
        low, high = (Decimal(0), Decimal(350)) if center < 350 else ((Decimal(350), Decimal(448)) if center < 448 else (Decimal(448), Decimal("595.32")))
        if not low <= box[0] < box[2] <= high:
            _fail("ambiguous")
        return low

    if column(current["box"]) != 350 or column(previous["box"]) != 448:
        _fail("ambiguous")

    def location(line):
        return {"quote": line["text"], "span": line["span"], "box": line["source_box"],
                "word_boxes": [w["source_box"] for w in line["words"]]}

    facts = []
    for metric, label in ROWS:
        row = unique(label)
        if column(row["box"]) != 0 or not current["box"][3] < row["box"][1] < footer["box"][1]:
            _fail("ambiguous")
        same_row = []
        for line in lines:
            if line is row:
                continue
            box = line["box"]
            if max(box[1], row["box"][1]) < min(box[3], row["box"][3]):
                if box[1::2] != row["box"][1::2]:
                    _fail("ambiguous")
                same_row.append(line)
        if len(same_row) != 2:
            _fail("ambiguous")
        columns = {}
        for item in same_row:
            band = column(item["box"])
            if band not in (350, 448) or band in columns or len(item["words"]) != 1:
                _fail("ambiguous")
            _number(item["text"])  # Validate comparison column as well.
            columns[band] = item
        if set(columns) != {Decimal(350), Decimal(448)}:
            _fail("ambiguous")
        cell = columns[Decimal(350)]
        value, missing = _number(cell["text"])
        facts.append({"metric": metric, "raw_literal": cell["text"], "value": value,
                      "missing_reason": missing, "currency": "USD", "unit": "thousand",
                      "period": {"start": "2026-01-01", "end": "2026-03-31", "label": current["text"]},
                      "entity_scope": "group", "accounting_basis": "IFRS_unaudited",
                      "locator": {"page_index": 9, "printed_page_label": "-9-",
                                  "page_width": page["width"], "page_height": page["height"],
                                  "coordinate_system": "top_left_pdf_points",
                                  "table_heading": location(title), "unit_heading": location(unit),
                                  "period_heading": location(period), "row_label": location(row),
                                  "period_column": location(current), "comparison_column": location(previous),
                                  "page_footer": location(footer), "value_cell": location(cell)}})
    output = {"schema_version": "corporate-number-data-v1", "profile": PROFILE,
              "raw_digest": raw_digest, "source_bbox_digest": source_digest, "bbox_data_digest": bbox_digest,
              "extractor_revision": expected_extractor_revision, "parser_revision": EXTRACTION_VERSION,
              "extraction_scope": "provided_bbox_only", "extraction_digest": hashlib.sha256(text.encode()).hexdigest(),
              "extracted_text": text, "source_page_count": total, "provided_page_indices": [p[0] for p in prepared],
              "facts": facts, "limitations": ["Provided bbox data do not attest source, extraction, permission or runtime isolation.",
                                                "Values concern the specified unaudited quarterly statement, not an annual period."]}
    encoded = canonical(output)
    if len(encoded) > OUTPUT_CAP:
        _fail("resource")
    return CorporateNumberData(encoded)


def parse_corporate_bbox(payload, *, expected_raw_digest, expected_bbox_digest,
                         expected_source_bbox_digest, expected_extractor_revision):
    """Compare bounded content with independent DATA expectations; no authority."""
    reason = None
    try:
        # Coordinate membership cannot depend on a caller's Decimal precision.
        with localcontext(Context(prec=50)):
            result = _parse(payload, expected_raw_digest, expected_bbox_digest,
                            expected_source_bbox_digest, expected_extractor_revision)
    except CorporateParseError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        reason = "unsupported"
    if reason:
        _fail(reason)
    return result
