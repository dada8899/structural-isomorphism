from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "deploy-retired-module.sh"
RELATIVE = Path("web/backend/services/verified_isomorphisms.py")


def _run(target: Path, body: str) -> subprocess.CompletedProcess[str]:
    runtime_root = target / ".runtime-test"
    runtime_root.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["TARGET"] = str(target)
    env["RUNTIME_ROOT"] = str(runtime_root)
    return subprocess.run(
        [
            "bash",
            "-c",
            f"set -euo pipefail; source {shlex.quote(str(HELPER))}; {body}",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_backup_remove_and_restore_without_previous_sha(tmp_path: Path) -> None:
    retired = tmp_path / RELATIVE
    sibling = retired.with_name("keep.py")
    retired.parent.mkdir(parents=True)
    retired.write_text("old release\n", encoding="utf-8")
    sibling.write_text("keep\n", encoding="utf-8")

    result = _run(
        tmp_path,
        'retired_module_backup_and_remove "$TARGET"; '
        'test ! -e "$TARGET/$RETIRED_TRACKED_RELATIVE_PATH"; '
        'retired_module_restore "$TARGET"',
    )

    assert result.returncode == 0, result.stderr
    assert retired.read_text(encoding="utf-8") == "old release\n"
    assert sibling.read_text(encoding="utf-8") == "keep\n"


def test_success_cleanup_leaves_exact_retired_path_absent(tmp_path: Path) -> None:
    retired = tmp_path / RELATIVE
    retired.parent.mkdir(parents=True)
    retired.write_text("old release\n", encoding="utf-8")

    result = _run(
        tmp_path,
        'retired_module_backup_and_remove "$TARGET"; retired_module_cleanup',
    )

    assert result.returncode == 0, result.stderr
    assert not retired.exists()


def test_missing_retired_path_is_an_idempotent_noop(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        'retired_module_backup_and_remove "$TARGET"; '
        'retired_module_restore "$TARGET"; retired_module_cleanup',
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / RELATIVE).exists()


def test_backup_is_regular_and_contained_by_runtime_root(tmp_path: Path) -> None:
    retired = tmp_path / RELATIVE
    retired.parent.mkdir(parents=True)
    retired.write_text("old release\n", encoding="utf-8")

    result = _run(
        tmp_path,
        'retired_module_capture "$TARGET"; '
        'test "$RETIRED_TRACKED_CAPTURED" = 1; '
        'test -f "$RETIRED_TRACKED_BACKUP"; test ! -L "$RETIRED_TRACKED_BACKUP"; '
        'case "$RETIRED_TRACKED_BACKUP" in "$RUNTIME_ROOT"/.rollback-retired.*) ;; *) exit 91 ;; esac; '
        'retired_module_cleanup',
    )

    assert result.returncode == 0, result.stderr
    assert retired.read_text(encoding="utf-8") == "old release\n"
    assert not list((tmp_path / ".runtime-test").glob(".rollback-retired.*"))


def test_symlink_and_special_retired_paths_fail_closed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    retired = tmp_path / RELATIVE
    retired.parent.mkdir(parents=True)
    retired.symlink_to(outside)
    symlink_result = _run(
        tmp_path,
        'if retired_module_capture "$TARGET"; then exit 92; fi',
    )
    assert symlink_result.returncode == 0, symlink_result.stderr
    assert retired.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside\n"

    retired.unlink()
    os.mkfifo(retired)
    fifo_result = _run(
        tmp_path,
        'if retired_module_capture "$TARGET"; then exit 93; fi',
    )
    assert fifo_result.returncode == 0, fifo_result.stderr
    assert retired.is_fifo()


def test_cleanup_refuses_backup_outside_runtime_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside-backup"
    outside.write_text("preserve\n", encoding="utf-8")
    result = _run(
        tmp_path,
        f'RETIRED_TRACKED_BACKUP={shlex.quote(str(outside))}; '
        'if retired_module_cleanup; then exit 94; fi',
    )

    assert result.returncode == 0, result.stderr
    assert outside.read_text(encoding="utf-8") == "preserve\n"
