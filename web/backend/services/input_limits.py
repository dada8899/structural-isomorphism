"""Canonical user-input ceilings and Unicode guards for research workflows."""
from __future__ import annotations

import unicodedata


MAX_RESEARCH_QUERY_CHARS = 8000

_LAYOUT_CONTROLS = {"\t", "\n", "\r"}
_BIDI_CONTROL_CLASSES = {
    "BN", "LRE", "LRO", "RLE", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI",
}
_DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


def _is_default_ignorable(char: str) -> bool:
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in _DEFAULT_IGNORABLE_RANGES)


def _has_forbidden_unicode(value: str, *, allow_layout: bool) -> bool:
    for char in value:
        if allow_layout and char in _LAYOUT_CONTROLS:
            continue
        category = unicodedata.category(char)
        if category in {"Cc", "Cf", "Cs"}:
            return True
        if unicodedata.bidirectional(char) in _BIDI_CONTROL_CLASSES:
            return True
        if _is_default_ignorable(char):
            return True
    return False


def normalize_research_text(
    value: str,
    *,
    max_chars: int,
    allow_layout: bool = True,
    field_name: str = "text",
) -> str:
    """NFKC-normalize one bounded string and reject invisible control tricks.

    Layout whitespace may be accepted for user-authored multi-line input; it is
    collapsed to ordinary spaces before the length check. Model-authored public
    fields pass ``allow_layout=False`` and therefore cannot contain controls at
    all.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = unicodedata.normalize("NFKC", value)
    if _has_forbidden_unicode(value, allow_layout=allow_layout) or _has_forbidden_unicode(
        normalized, allow_layout=allow_layout,
    ):
        raise ValueError(f"{field_name} contains forbidden Unicode controls")
    if allow_layout:
        normalized = " ".join(normalized.split())
    else:
        normalized = normalized.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_chars:
        raise ValueError(f"{field_name} is too long")
    return normalized


def normalize_research_query(value: str) -> str:
    """Canonical public-query guard shared by request models."""
    return normalize_research_text(
        value,
        max_chars=MAX_RESEARCH_QUERY_CHARS,
        allow_layout=True,
        field_name="query",
    )
