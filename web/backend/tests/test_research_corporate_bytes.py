"""The raw port stays closed; synthetic bytes are not an actual PDF proof."""
import ast
import hashlib
from pathlib import Path
import traceback
from unittest.mock import patch

import pytest
from research.source_adapters import corporate_bytes as raw


def test_matching_synthetic_bytes_still_dependency_without_ops():
    value=b"%PDF-1.5\nsynthetic-test-only\n%%EOF\n"
    with patch("socket.socket",side_effect=AssertionError("no network")),patch("subprocess.Popen",side_effect=AssertionError("no exec")),patch("builtins.open",side_effect=AssertionError("no file")):
        with pytest.raises(raw.CorporateParseError) as err:
            raw.parse_corporate_bytes(value,profile=raw.PROFILE,expected_raw_digest=hashlib.sha256(value).hexdigest())
    assert err.value.reason=="dependency"


@pytest.mark.parametrize("value,profile,digest,reason",[
    (bytearray(b"x"),raw.PROFILE,"a"*64,"unsupported"),
    (b"x","gfs-2025-20f-html","a"*64,"unsupported"),
    (b"x",raw.PROFILE,True,"digest"),
    (b"x",raw.PROFILE,"a"*64,"digest"),
    (b"x"*(raw.RAW_CAP+1),raw.PROFILE,"a"*64,"resource")])
def test_raw_rejections_are_bounded_and_fixed(value,profile,digest,reason):
    with pytest.raises(raw.CorporateParseError) as err:
        raw.parse_corporate_bytes(value,profile=profile,expected_raw_digest=digest)
    assert err.value.reason==reason


@pytest.mark.parametrize("action",["digest","dependency","profile"])
def test_raw_failure_drops_outer_private_exception(action):
    canary="PRIVATE-RAW-CORPORATE-CANARY"
    try:raise ValueError(canary)
    except ValueError:
        value=b"bounded"
        with pytest.raises(raw.CorporateParseError) as stopped:
            raw.parse_corporate_bytes(value,profile=canary if action=="profile" else raw.PROFILE,
                expected_raw_digest=canary if action=="digest" else hashlib.sha256(value).hexdigest())
        safe=stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None and safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


def test_no_user_callback_runtime_flag_or_dynamic_dependency():
    with pytest.raises(TypeError):raw.parse_corporate_bytes(b"",profile=raw.PROFILE,expected_raw_digest="a"*64,callback=lambda:True)
    tree=ast.parse(Path(raw.__file__).read_text())
    assert [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]==["corporate_locations"]
    assert [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]==["hashlib"]
