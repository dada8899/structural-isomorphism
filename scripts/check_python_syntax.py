#!/usr/bin/env python3
"""Compile every tracked Python source with the release interpreter."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RELEASE_PYTHON = (3, 11)


def tracked_python_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = [os.fsdecode(item) for item in completed.stdout.split(b"\0") if item]
    if not paths:
        raise RuntimeError("release syntax gate found no tracked Python files")
    return paths


def _read_guarded_source(root: Path, relative_path: str) -> bytes:
    pure_path = PurePosixPath(relative_path)
    if (
        pure_path.is_absolute()
        or pure_path.as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in pure_path.parts)
    ):
        raise ValueError(f"non-canonical tracked path: {relative_path!r}")

    root_resolved = root.resolve(strict=True)
    source = root.joinpath(*pure_path.parts)
    metadata = source.lstat()
    if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
        raise ValueError(f"tracked Python source is not a regular file: {relative_path}")
    try:
        resolved = source.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"tracked Python source escapes repository: {relative_path}") from exc
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError(f"tracked Python target is not a regular file: {relative_path}")
    return source.read_bytes()


def syntax_failures(root: Path, paths: Iterable[str]) -> list[str]:
    failures: list[str] = []
    for relative_path in paths:
        try:
            source = _read_guarded_source(root, relative_path)
            compile(source, relative_path, "exec", dont_inherit=True)
        except SyntaxError as exc:
            line = exc.lineno or 0
            column = exc.offset or 0
            failures.append(
                f"{relative_path}:{line}:{column}: {exc.msg}"
            )
    return failures


def main() -> int:
    if sys.version_info[:2] != RELEASE_PYTHON:
        actual = ".".join(str(part) for part in sys.version_info[:2])
        expected = ".".join(str(part) for part in RELEASE_PYTHON)
        print(
            f"python syntax gate error: expected Python {expected}, got {actual}",
            file=sys.stderr,
        )
        return 2
    try:
        paths = tracked_python_paths(ROOT)
        failures = syntax_failures(ROOT, paths)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"python syntax gate error: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("Python sources are not compatible with the release interpreter:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        f"Python syntax gate passed: {len(paths)} tracked files under "
        f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
