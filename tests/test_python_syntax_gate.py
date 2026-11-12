from pathlib import Path

import pytest

from scripts.check_python_syntax import (
    RELEASE_PYTHON,
    _read_guarded_source,
    syntax_failures,
)


def test_syntax_gate_pins_the_release_interpreter() -> None:
    assert RELEASE_PYTHON == (3, 11)


def test_syntax_gate_reports_release_incompatible_source(tmp_path: Path) -> None:
    (tmp_path / "valid.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "invalid.py").write_text("value = (\n", encoding="utf-8")

    failures = syntax_failures(tmp_path, ["valid.py", "invalid.py"])

    assert len(failures) == 1
    assert failures[0].startswith("invalid.py:1:")


@pytest.mark.parametrize("relative_path", ["../outside.py", "/tmp/outside.py", "./file.py"])
def test_syntax_gate_rejects_noncanonical_paths(
    tmp_path: Path, relative_path: str
) -> None:
    with pytest.raises(ValueError, match="non-canonical tracked path"):
        _read_guarded_source(tmp_path, relative_path)


def test_syntax_gate_accepts_contained_tracked_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(target)

    assert _read_guarded_source(tmp_path, "link.py") == b"value = 1\n"
    assert syntax_failures(tmp_path, ["link.py"]) == []


def test_syntax_gate_rejects_escaping_tracked_symlink(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")
    (root / "link.py").symlink_to(outside)

    with pytest.raises(ValueError, match="escapes repository"):
        _read_guarded_source(root, "link.py")
