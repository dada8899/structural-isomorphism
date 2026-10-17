"""Closed raw-PDF entry until an Ops-owned controlled extractor is integrated.

The separate bbox port validates data only. Neither public entry mints source,
grant, extraction proof, financial registry records or runtime capabilities.
"""
import hashlib

from .corporate_locations import PROFILE, CorporateParseError, _digest, _fail, parse_corporate_bbox

RAW_CAP = 8 * 1024 * 1024


def parse_corporate_bytes(raw, *, profile, expected_raw_digest):
    """No subprocess, loader, environment flag or caller-injected callback."""
    if type(raw) is not bytes or type(profile) is not str or profile != PROFILE:
        _fail("unsupported")
    if len(raw) > RAW_CAP:
        _fail("resource")
    expected_raw_digest = _digest(expected_raw_digest)
    if hashlib.sha256(raw).hexdigest() != expected_raw_digest:
        _fail("digest")
    # A matching PDF/digest is not extraction completeness, action safety,
    # Linux isolation or source permission. No controlled Ops port exists yet.
    _fail("dependency")
