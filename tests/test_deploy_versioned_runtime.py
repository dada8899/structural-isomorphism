from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy-vps.sh"
HELPER = ROOT / "scripts" / "deploy-versioned-runtime.sh"
RETIRED_HELPER = ROOT / "scripts" / "deploy-retired-module.sh"
UNIT = ROOT / "web" / "scripts" / "structural-web.service"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-beta-backend.yml"
PHASE_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-phase-detector.yml"
EWS_WORKFLOW = ROOT / ".github" / "workflows" / "ews-pipeline-nightly.yml"
SITE_SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "site-smoke.yml"
DISPATCH_ENTRYPOINT = ROOT / "scripts" / "deploy-beta-backend.sh"
PHASE_DISPATCH_ENTRYPOINT = ROOT / "scripts" / "deploy-phase-detector-entrypoint.sh"
PHASE_DEPLOY_ENGINE = ROOT / "scripts" / "deploy-phase-detector-vps.sh"
PHASE_TEST_ISOLATION_MARKER = "structural-phase-test-isolation-v1"
FORCED_DISPATCHER = ROOT / "scripts" / "deploy-dispatcher.sh"
DISPATCH_INSTALLER = ROOT / "scripts" / "install-deploy-dispatcher.sh"
CANONICAL_PRIVACY_KEY = ("01234567" + "89abcdef") * 4


@pytest.fixture(autouse=True)
def _make_immutable_runtime_fixtures_removable(request):
    yield
    tmp_path = request.node.funcargs.get("tmp_path")
    if tmp_path is None:
        return
    for root, directories, files in os.walk(tmp_path, topdown=False):
        for name in directories + files:
            path = Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o700)
        Path(root).chmod(Path(root).stat().st_mode | 0o700)


def _bash(
    body: str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail; source {shlex.quote(str(HELPER))}; {body}"],
        env=merged,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _source_deploy(
    body: str, *, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [
            "bash",
            "-c",
            f"set -euo pipefail; source {shlex.quote(str(DEPLOY))}; {body}",
        ],
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _bind_phase_test_isolation(
    env: dict[str, str], repository: Path, test_root: Path
) -> None:
    physical_root = test_root.resolve(strict=True)
    physical_repo = repository.resolve(strict=True)
    assert physical_repo != physical_root
    assert physical_repo.is_relative_to(physical_root)
    assert not repository.is_symlink()
    git_dir = physical_repo / ".git"
    assert git_dir.is_dir() and not git_dir.is_symlink()
    marker = git_dir / PHASE_TEST_ISOLATION_MARKER
    marker.write_text(
        f"protocol={PHASE_TEST_ISOLATION_MARKER}\n"
        f"test_root={physical_root}\n"
        f"repo_root={physical_repo}\n",
        encoding="utf-8",
    )
    marker.chmod(0o600)
    env["PHASE_REPO"] = str(physical_repo)
    env["STRUCTURAL_PHASE_TEST_ROOT"] = str(physical_root)


def _make_fake_systemctl(
    tmp_path: Path, *, enabled: str = "disabled", active: str = "inactive"
) -> tuple[Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    state = tmp_path / "fake-systemctl-state"
    state.mkdir()
    (state / "enabled").write_text(enabled + "\n", encoding="utf-8")
    (state / "active").write_text(active + "\n", encoding="utf-8")
    script = fake_bin / "systemctl"
    script.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        ': "${FAKE_SYSTEMCTL_STATE:?}"\n'
        'printf "%s\\n" "$*" >> "$FAKE_SYSTEMCTL_STATE/calls"\n'
        'if test "${FAKE_SYSTEMCTL_ERROR_COMMAND:-}" = "$1"; then\n'
        "  echo 'Failed to connect to bus: injected failure' >&2\n"
        "  exit 1\n"
        "fi\n"
        'case "$1" in\n'
        "  is-enabled)\n"
        '    value=$(cat "$FAKE_SYSTEMCTL_STATE/enabled"); echo "$value"\n'
        '    test "$value" = enabled -o "$value" = enabled-runtime\n'
        "    ;;\n"
        "  is-active)\n"
        '    value=$(cat "$FAKE_SYSTEMCTL_STATE/active"); echo "$value"\n'
        '    test "$value" = active && exit 0\n'
        '    test "$value" = inactive -o "$value" = failed && exit 3\n'
        "    exit 4\n"
        "    ;;\n"
        '  enable) echo enabled > "$FAKE_SYSTEMCTL_STATE/enabled" ;;\n'
        '  disable) echo disabled > "$FAKE_SYSTEMCTL_STATE/enabled" ;;\n'
        '  restart) echo active > "$FAKE_SYSTEMCTL_STATE/active" ;;\n'
        '  stop) echo inactive > "$FAKE_SYSTEMCTL_STATE/active" ;;\n'
        "  reset-failed|daemon-reload|reload) ;;\n"
        "  *) echo \"unexpected systemctl command: $*\" >&2; exit 64 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return fake_bin, state


def _add_fake_nginx(fake_bin: Path, state: Path) -> None:
    script = fake_bin / "nginx"
    script.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        ': "${FAKE_NGINX_STATE:?}"\n'
        'printf "%s\\n" "$*" >> "$FAKE_NGINX_STATE/calls"\n'
        'failures=$(cat "$FAKE_NGINX_STATE/failures")\n'
        'if test "$failures" -gt 0; then\n'
        '  echo $((failures - 1)) > "$FAKE_NGINX_STATE/failures"\n'
        "  exit 1\n"
        "fi\n"
        'test "$1" = -t\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    (state / "failures").write_text("0\n", encoding="utf-8")


def _make_git_source(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "deploy-test@example.test")
    _git(source, "config", "user.name", "Deploy Test")
    (source / ".gitignore").write_text(".env\n", encoding="utf-8")
    (source / "app.py").write_text("print('release')\n", encoding="utf-8")
    _git(source, "add", ".gitignore", "app.py")
    _git(source, "commit", "-qm", "release")
    return source, _git(source, "rev-parse", "HEAD")


def _make_dispatch_repository(tmp_path: Path) -> tuple[Path, str, str, str]:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    repository = tmp_path / "dispatch-repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "dispatch-test@example.test")
    _git(repository, "config", "user.name", "Dispatch Test")
    _git(repository, "remote", "add", "origin", str(remote))
    _git(repository, "checkout", "-qb", "main")
    scripts = repository / "scripts"
    scripts.mkdir()
    (scripts / "deploy-vps.sh").write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        ': "${DISPATCH_RESULT:?}"\n'
        'printf "%s\\n" "$DEPLOY_COMMIT" > "$DISPATCH_RESULT"\n'
        'git -C "$SOURCE" rev-parse HEAD >> "$DISPATCH_RESULT"\n',
        encoding="utf-8",
    )
    (scripts / "deploy-phase-detector-vps.sh").write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        ': "${PHASE_DISPATCH_RESULT:?}"\n'
        'printf "%s\\n" "$PHASE_PREVIOUS_SHA" "$PHASE_DEPLOY_COMMIT" > "$PHASE_DISPATCH_RESULT"\n'
        'git -C "$STRUCTURAL_PHASE_REPO" rev-parse HEAD >> "$PHASE_DISPATCH_RESULT"\n',
        encoding="utf-8",
    )
    for name in ("deploy-versioned-runtime.sh", "deploy-retired-module.sh"):
        (scripts / name).write_text("#!/bin/bash\n# tracked bootstrap\n", encoding="utf-8")
    (scripts / "install-nginx-privacy-vhost.sh").write_text(
        "#!/bin/bash\n# tracked phase bootstrap\n", encoding="utf-8"
    )
    for script in scripts.iterdir():
        script.chmod(0o755)
    (repository / "app.txt").write_text("release one\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "release one")
    first = _git(repository, "rev-parse", "HEAD")
    _git(repository, "push", "-qu", "origin", "main")

    (repository / "app.txt").write_text("release two\n", encoding="utf-8")
    _git(repository, "commit", "-qam", "release two")
    second = _git(repository, "rev-parse", "HEAD")
    _git(repository, "push", "-q", "origin", "main")

    _git(repository, "checkout", "-qb", "side", first)
    (repository / "side.txt").write_text("never main\n", encoding="utf-8")
    _git(repository, "add", "side.txt")
    _git(repository, "commit", "-qm", "side only")
    side = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "-q", "main")
    return repository, first, second, side


def _dispatch_env(tmp_path: Path, repository: Path, result: Path) -> dict[str, str]:
    fake_bin = tmp_path / "dispatch-bin"
    fake_bin.mkdir(exist_ok=True)
    flock = fake_bin / "flock"
    flock.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    flock.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "STRUCTURAL_BETA_REPO": str(repository),
        "STRUCTURAL_BETA_DEPLOY_LOCK": str(tmp_path / "deploy.lock"),
        "DISPATCH_RESULT": str(result),
    }


def _make_forced_dispatch_fixture(tmp_path: Path) -> tuple[Path, Path]:
    install_dir = tmp_path / "forced-dispatch"
    install_dir.mkdir()
    dispatcher = install_dir / "deploy-dispatcher.sh"
    shutil.copy2(FORCED_DISPATCHER, dispatcher)
    dispatcher.chmod(0o755)
    record = tmp_path / "forced-dispatch-record"
    entrypoint = install_dir / "deploy-beta-backend.sh"
    entrypoint.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'printf "beta\\n%s\\n%s\\n%s\\n%s\\n" "$#" "$1" '
        f'"${{STRUCTURAL_BETA_REPO-unset}}" "${{GIT_DIR-unset}}" > {shlex.quote(str(record))}\n',
        encoding="utf-8",
    )
    entrypoint.chmod(0o755)
    phase_entrypoint = install_dir / "deploy-phase-detector-entrypoint.sh"
    phase_entrypoint.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'printf "phase\\n%s\\n%s\\n%s\\n%s\\n" "$#" "$1" '
        f'"${{STRUCTURAL_PHASE_REPO-unset}}" "${{GIT_WORK_TREE-unset}}" > {shlex.quote(str(record))}\n',
        encoding="utf-8",
    )
    phase_entrypoint.chmod(0o755)
    return dispatcher, record


def _dispatcher_install_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path, str]:
    install_dir = tmp_path / "installed-dispatch"
    install_dir.mkdir()
    ssh_dir = tmp_path / "ssh"
    ssh_dir.mkdir()
    authorized_keys = ssh_dir / "authorized_keys"
    authorized_keys.write_text("# operator key\nssh-ed25519 b3BlcmF0b3Ita2V5LW1hdGVyaWFs operator\n")
    authorized_keys.chmod(0o600)
    public_key = tmp_path / "deploy-key.pub"
    public_blob = "AAAAC3NzaC1lZDI1NTE5AAAAIAf5u9RhBKJrIF/oQvRZfYIDnhtce75WgHXoc+Iv5FNu"
    public_key.write_text(f"ssh-ed25519 {public_blob} deploy\n", encoding="utf-8")
    return (
        {
            **os.environ,
            "STRUCTURAL_DEPLOY_INSTALL_DIR": str(install_dir),
            "STRUCTURAL_DEPLOY_AUTHORIZED_KEYS": str(authorized_keys),
            "STRUCTURAL_DEPLOY_PUBLIC_KEY_FILE": str(public_key),
        },
        install_dir,
        authorized_keys,
        public_blob,
    )


_RUNTIME_TEMPLATE: Path | None = None
_RUNTIME_PACKAGE_VERSIONS = {
    "fastapi": "0.115.14",
    "pydantic": "2.6.1",
    "starlette": "0.46.2",
    "uvicorn": "0.27.1",
}


def _record_line(path: str, payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
    return f"{path},sha256={digest.decode('ascii')},{len(payload)}\n"


def _replace_record_line(record: Path, path: str, payload: bytes) -> None:
    lines = record.read_text(encoding="utf-8").splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.split(",", 1)[0] == path]
    assert len(matches) == 1
    lines[matches[0]] = _record_line(path, payload)
    record.write_text("".join(lines), encoding="utf-8")


def _composite_freeze_sha256(graph_sha256: str, content_sha256: str) -> str:
    payload = (
        f"resolved_graph_sha256={graph_sha256}\n"
        f"runtime_content_sha256={content_sha256}\n"
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _remove_runtime_test_bytecode(environment: Path) -> None:
    site_packages = _runtime_site_packages(environment)
    for pyc in site_packages.rglob("*.pyc"):
        pyc.unlink()
    for cache in sorted(site_packages.rglob("__pycache__"), reverse=True):
        if cache.exists():
            cache.rmdir()


def _runtime_template() -> Path:
    global _RUNTIME_TEMPLATE
    if _RUNTIME_TEMPLATE is not None:
        return _RUNTIME_TEMPLATE
    template = Path(tempfile.mkdtemp(prefix="structural-runtime-test-template-"))
    created = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"runtime_create_venv_without_pip {shlex.quote(str(template))}; "
        f"runtime_bootstrap_pip {shlex.quote(str(template))}"
    )
    assert created.returncode == 0, created.stderr
    site_packages_result = subprocess.run(
        [
            str(template / "bin" / "python"),
            "-c",
            "import sysconfig; print(sysconfig.get_paths()['purelib'])",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    site_packages = Path(site_packages_result.stdout.strip())
    for package, version in _RUNTIME_PACKAGE_VERSIONS.items():
        package_dir = site_packages / package
        package_dir.mkdir()
        init = package_dir / "__init__.py"
        init.write_text(f"__version__ = {version!r}\n", encoding="utf-8")
        metadata_name = f"{package}-{version}.dist-info"
        metadata_dir = site_packages / metadata_name
        metadata_dir.mkdir()
        metadata_file = metadata_dir / "METADATA"
        metadata_file.write_text(
            f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n",
            encoding="utf-8",
        )
        (metadata_dir / "RECORD").write_text(
            _record_line(f"{package}/__init__.py", init.read_bytes())
            + _record_line(f"{metadata_name}/METADATA", metadata_file.read_bytes())
            + f"{metadata_name}/RECORD,,\n",
            encoding="utf-8",
        )
    _remove_runtime_test_bytecode(template)
    _RUNTIME_TEMPLATE = template
    return template


def _runtime_site_packages(release: Path) -> Path:
    result = subprocess.run(
        [
            str(release / "bin" / "python"),
            "-I",
            "-B",
            "-c",
            "import sysconfig; print(sysconfig.get_paths()['purelib'])",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return Path(result.stdout.strip())


def _replace_runtime_distribution(
    release: Path, package: str, version: str | None
) -> None:
    site_packages = _runtime_site_packages(release)
    stem = package.replace("-", "_")
    for pattern in (f"{stem}-*.dist-info", f"{stem}.egg-info"):
        for metadata_dir in site_packages.glob(pattern):
            shutil.rmtree(metadata_dir)
    if package == "setuptools":
        for package_name in ("setuptools", "pkg_resources"):
            package_path = site_packages / package_name
            if package_path.exists() or package_path.is_symlink():
                if package_path.is_symlink():
                    package_path.unlink()
                else:
                    shutil.rmtree(package_path)
        precedence = site_packages / "distutils-precedence.pth"
        if precedence.exists() or precedence.is_symlink():
            precedence.unlink()
        local_hack = site_packages / "_distutils_hack"
        if local_hack.exists() or local_hack.is_symlink():
            if local_hack.is_symlink():
                local_hack.unlink()
            else:
                shutil.rmtree(local_hack)
    if version is None:
        return
    package_dir = site_packages / stem
    package_dir.mkdir(exist_ok=True)
    init = package_dir / "__init__.py"
    init.write_text(f"__version__ = {version!r}\n", encoding="utf-8")
    metadata_name = f"{stem}-{version}.dist-info"
    metadata_dir = site_packages / metadata_name
    metadata_dir.mkdir()
    metadata_file = metadata_dir / "METADATA"
    metadata_file.write_text(
        f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n",
        encoding="utf-8",
    )
    (metadata_dir / "RECORD").write_text(
        _record_line(f"{stem}/__init__.py", init.read_bytes())
        + _record_line(f"{metadata_name}/METADATA", metadata_file.read_bytes())
        + f"{metadata_name}/RECORD,,\n",
        encoding="utf-8",
    )


def _install_owned_setuptools_hook(release: Path) -> tuple[Path, Path]:
    site_packages = _runtime_site_packages(release)
    local_hack = site_packages / "_distutils_hack"
    local_hack.mkdir()
    hack_init = local_hack / "__init__.py"
    hack_init.write_text("def add_shim(): pass\n", encoding="utf-8")
    precedence = site_packages / "distutils-precedence.pth"
    precedence.write_text(
        "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; "
        "enabled = os.environ.get(var, 'local') == 'local'; "
        "enabled and __import__('_distutils_hack').add_shim();\n",
        encoding="utf-8",
    )
    record = site_packages / "setuptools-83.0.0.dist-info" / "RECORD"
    with record.open("a", encoding="utf-8") as stream:
        stream.write(_record_line("distutils-precedence.pth", precedence.read_bytes()))
        stream.write(
            _record_line("_distutils_hack/__init__.py", hack_init.read_bytes())
        )
    return site_packages, hack_init


def _make_runtime_release_writable(release: Path) -> None:
    for root, directories, files in os.walk(release):
        for name in [".", *directories, *files]:
            path = Path(root) if name == "." else Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o700)


def _rebind_runtime_release_identity(release: Path) -> Path:
    attestation_path = release / "attestation.json"
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    graph_sha = hashlib.sha256(
        (release / "resolved-packages.txt").read_bytes()
    ).hexdigest()
    proof = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        "runtime_validate_canonical_package_set "
        f"{shlex.quote(str(release))} "
        f"{shlex.quote(str(release / 'resolved-packages.txt'))} {graph_sha}"
    )
    assert proof.returncode == 0, proof.stderr
    count_raw, content_sha = proof.stdout.strip().split("\t")
    freeze_sha = _composite_freeze_sha256(graph_sha, content_sha)
    runtime_id = (
        f"{payload['python_abi']}-{payload['requirements_sha256']}-{freeze_sha}"
    )
    target = release.with_name(runtime_id)
    payload.update(
        {
            "schema_version": 2,
            "runtime_id": runtime_id,
            "resolved_graph_sha256": graph_sha,
            "runtime_content_sha256": content_sha,
            "installed_freeze_sha256": freeze_sha,
            "installed_package_count": int(count_raw),
        }
    )
    attestation_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release.rename(target)
    for root, directories, files in os.walk(target):
        for name in [".", *directories, *files]:
            path = Path(root) if name == "." else Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    return target


def _downgrade_runtime_release_to_schema1(release: Path) -> Path:
    _make_runtime_release_writable(release)
    attestation_path = release / "attestation.json"
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    graph_sha = payload.pop("resolved_graph_sha256")
    payload.pop("runtime_content_sha256")
    runtime_id = (
        f"{payload['python_abi']}-{payload['requirements_sha256']}-{graph_sha}"
    )
    payload.update(
        {
            "schema_version": 1,
            "runtime_id": runtime_id,
            "installed_freeze_sha256": graph_sha,
        }
    )
    attestation_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    target = release.with_name(runtime_id)
    release.rename(target)
    for root, directories, files in os.walk(target):
        for name in [".", *directories, *files]:
            path = Path(root) if name == "." else Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    return target


def _write_runtime_test_wheel(
    wheelhouse: Path, package: str, version: str
) -> None:
    normalized = package.replace("-", "_")
    metadata_dir = f"{normalized}-{version}.dist-info"
    files = {
        f"{normalized}/__init__.py": f"__version__ = {version!r}\n",
        f"{metadata_dir}/METADATA": (
            "Metadata-Version: 2.1\n"
            f"Name: {package}\n"
            f"Version: {version}\n"
            + ("Provides-Extra: standard\n" if package == "uvicorn" else "")
        ),
        f"{metadata_dir}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: structural-runtime-test\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ),
    }
    record = f"{metadata_dir}/RECORD"
    files[record] = "".join(
        _record_line(name, content.encode("utf-8")) for name, content in files.items()
    ) + f"{record},,\n"
    wheel = wheelhouse / f"{normalized}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _make_runtime_release(
    releases: Path,
    *,
    abi: str | None = None,
    requirements_sha: str,
    freeze_sha: str | None = None,
    resolved_package_versions: dict[str, str] | None = None,
) -> Path:
    template = _runtime_template()
    abi = abi or sys.implementation.cache_tag
    package_versions = {
        **_RUNTIME_PACKAGE_VERSIONS,
        **(resolved_package_versions or {}),
    }
    graph = "".join(
        f"{name}=={package_versions[name]}\n" for name in sorted(package_versions)
    )
    graph_sha = hashlib.sha256(graph.encode("utf-8")).hexdigest()
    release = releases / f".fixture-staging-{requirements_sha}"
    release.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, release, symlinks=True)
    for package, version in (resolved_package_versions or {}).items():
        _replace_runtime_distribution(release, package, version)
    (release / ".complete").touch()
    (release / "resolved-packages.txt").write_text(graph, encoding="utf-8")
    (release / "installed-packages.txt").write_text(graph, encoding="utf-8")
    _remove_runtime_test_bytecode(release)
    proof = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        "runtime_validate_canonical_package_set "
        f"{shlex.quote(str(release))} "
        f"{shlex.quote(str(release / 'resolved-packages.txt'))} {graph_sha}",
        env={"STRUCTURAL_EXPECTED_PYTHON_ABI": abi},
    )
    assert proof.returncode == 0, proof.stderr
    installed_count_raw, content_sha = proof.stdout.strip().split("\t")
    installed_count = int(installed_count_raw)
    actual_freeze_sha = _composite_freeze_sha256(graph_sha, content_sha)
    if freeze_sha is not None:
        assert freeze_sha == actual_freeze_sha
    freeze_sha = actual_freeze_sha
    final_release = releases / f"{abi}-{requirements_sha}-{freeze_sha}"
    release.rename(final_release)
    release = final_release
    python_version = subprocess.run(
        [
            str(release / "bin" / "python"),
            "-I",
            "-B",
            "-c",
            "import platform; print(platform.python_version())",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    ).stdout.strip()
    (release / "attestation.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id": release.name,
                "requirements_sha256": requirements_sha,
                "resolved_graph_sha256": graph_sha,
                "runtime_content_sha256": content_sha,
                "installed_freeze_sha256": freeze_sha,
                "installed_package_count": installed_count,
                "python_abi": abi,
                "python_version": python_version,
                **_RUNTIME_PACKAGE_VERSIONS,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for root, directories, files in os.walk(release):
        for name in [".", *directories, *files]:
            path = Path(root) if name == "." else Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    return release


def _make_forged_runtime_release(releases: Path, *, requirements_sha: str) -> Path:
    abi = sys.implementation.cache_tag
    freeze_sha = "f" * 64
    release = releases / f"{abi}-{requirements_sha}-{freeze_sha}"
    (release / "bin").mkdir(parents=True)
    for executable in ("python", "pip"):
        path = release / "bin" / executable
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    (release / ".complete").touch()
    (release / "attestation.json").write_text(
        json.dumps({
            "schema_version": 1,
            "runtime_id": release.name,
            "requirements_sha256": requirements_sha,
            "installed_freeze_sha256": freeze_sha,
            "installed_package_count": 4,
            "python_abi": abi,
            "python_version": "3.11.6",
            **_RUNTIME_PACKAGE_VERSIONS,
        }) + "\n",
        encoding="utf-8",
    )
    for root, directories, files in os.walk(release):
        for name in [".", *directories, *files]:
            path = Path(root) if name == "." else Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    return release


def _stage_recoverable_transaction(
    tmp_path: Path, *, wait_for_sigkill: bool,
) -> dict[str, Path]:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    old_release = _make_runtime_release(releases, requirements_sha="1" * 64)
    new_release = _make_runtime_release(releases, requirements_sha="2" * 64)
    current = runtime_root / "current"
    current.symlink_to(old_release)
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("old code\n", encoding="utf-8")
    protected = target / "operator" / "keep.txt"
    protected.parent.mkdir()
    protected.write_text("operator old\n", encoding="utf-8")
    fingerprint = target / "web" / "backend" / ".env.runtime"
    fingerprint.parent.mkdir(parents=True)
    fingerprint.write_text("OLD_FINGERPRINT=1\n", encoding="utf-8")
    retired = target / "web" / "backend" / "services" / "verified_isomorphisms.py"
    retired.parent.mkdir(parents=True, exist_ok=True)
    retired.write_text("old retired module\n", encoding="utf-8")
    unit = tmp_path / "structural-web.service"
    unit.write_text("old unit\n", encoding="utf-8")
    auth_env = tmp_path / "beta-auth.env"
    dropin = tmp_path / "structural-web.service.d" / "auth.conf"
    dropin.parent.mkdir()
    dropin.write_text(
        f"[Service]\nEnvironmentFile={auth_env}\n", encoding="utf-8"
    )
    dropin.chmod(0o600)
    nginx_vhost = tmp_path / "beta.conf"
    nginx_vhost.write_text("old vhost\n", encoding="utf-8")
    journal = runtime_root / "deploy-journal.json"
    ready = tmp_path / "transaction-ready"
    fake_bin, fake_state = _make_fake_systemctl(tmp_path)
    _add_fake_nginx(fake_bin, fake_state)
    wait = "while :; do sleep 1; done" if wait_for_sigkill else ":"
    body = (
        f'source {shlex.quote(str(HELPER))}; '
        f'source {shlex.quote(str(RETIRED_HELPER))}; '
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        f'TARGET={shlex.quote(str(target))}; SERVICE=structural-web; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(dropin))}; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(fingerprint))}; '
        f'NGINX_VHOST_TARGET={shlex.quote(str(nginx_vhost))}; '
        f'SOURCE_HEAD_SHA={"a" * 40}; RUNTIME_ID={shlex.quote(new_release.name)}; '
        'RUNTIME_BACKUP=""; RUNTIME_FINGERPRINT_BACKUP_READY=0; '
        'RUNTIME_FINGERPRINT_PREEXISTED=0; RUNTIME_FINGERPRINT_TMP=""; '
        'SYSTEMD_STATE_CAPTURED=0; SYSTEMD_SERVICE_WAS_ENABLED=0; '
        'SYSTEMD_SERVICE_WAS_ACTIVE=0; DEPLOY_TRANSACTION_ACTIVE=1; '
        'DEPLOY_ROLLBACK_DONE=0; DEPLOY_CLEANUP_DONE=0; '
        'EXCLUDES=(--exclude=.env --exclude=operator/); '
        'runtime_capture_current; deploy_code_snapshot; systemd_unit_capture; '
        f'systemd_dropin_capture {shlex.quote(str(auth_env))}; '
        'capture_systemd_service_state; runtime_fingerprint_capture; nginx_vhost_capture; '
        'deploy_journal_write snapshot; '
        'printf "new code\n" > "$TARGET/app.py"; '
        'printf "operator live\n" > "$TARGET/operator/keep.txt"; '
        'RUNTIME_SWITCHED=1; deploy_journal_write runtime_switching; '
        f'RUNTIME_RELEASE={shlex.quote(str(new_release))}; runtime_switch; '
        'printf "NEW_FINGERPRINT=1\n" > "$RUNTIME_FINGERPRINT_TARGET"; '
        'retired_module_capture "$TARGET"; deploy_journal_write retired_captured; '
        'RETIRED_TRACKED_REMOVED=1; deploy_journal_write retired_removing; '
        'retired_module_remove "$TARGET"; deploy_journal_write retired_removed; '
        'SYSTEMD_UNIT_INSTALLED=1; SYSTEMD_DROPIN_REMOVED=1; '
        'deploy_journal_write unit_installing; '
        'printf "new unit\n" > "$SYSTEMD_UNIT_TARGET"; systemd_dropin_migrate; '
        'NGINX_VHOST_INSTALLED=1; deploy_journal_write nginx_installing; '
        'printf "new vhost\n" > "$NGINX_VHOST_TARGET"; '
        'printf "enabled\n" > "$FAKE_SYSTEMCTL_STATE/enabled"; '
        'printf "active\n" > "$FAKE_SYSTEMCTL_STATE/active"; '
        'deploy_journal_write ready; '
        f'touch {shlex.quote(str(ready))}; {wait}'
    )
    process = subprocess.Popen(
        ["bash", "-c", f"set -euo pipefail; {body}"],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_SYSTEMCTL_STATE": str(fake_state),
            "FAKE_NGINX_STATE": str(fake_state),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if wait_for_sigkill:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.01)
        assert ready.exists(), process.communicate(timeout=2)[1]
        process.kill()
    stdout, stderr = process.communicate(timeout=15)
    expected = -signal.SIGKILL if wait_for_sigkill else 0
    assert process.returncode == expected, (stdout, stderr)
    return {
        "runtime_root": runtime_root,
        "old_release": old_release,
        "new_release": new_release,
        "current": current,
        "target": target,
        "protected": protected,
        "fingerprint": fingerprint,
        "retired": retired,
        "unit": unit,
        "dropin": dropin,
        "nginx_vhost": nginx_vhost,
        "journal": journal,
        "fake_bin": fake_bin,
        "fake_state": fake_state,
    }


def _recover_staged_transaction(
    paths: dict[str, Path], *, nginx_failures: int = 0,
) -> subprocess.CompletedProcess[str]:
    (paths["fake_state"] / "failures").write_text(
        f"{nginx_failures}\n", encoding="utf-8"
    )
    target = paths["target"]
    fingerprint = paths["fingerprint"]
    body = (
        f'source {shlex.quote(str(RETIRED_HELPER))}; '
        f'RUNTIME_ROOT={shlex.quote(str(paths["runtime_root"]))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(paths["journal"]))}; '
        f'TARGET={shlex.quote(str(target))}; SERVICE=structural-web; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(paths["unit"]))}; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(paths["dropin"]))}; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(fingerprint))}; '
        f'NGINX_VHOST_TARGET={shlex.quote(str(paths["nginx_vhost"]))}; '
        'RUNTIME_BACKUP=""; RUNTIME_FINGERPRINT_TMP=""; '
        'DEPLOY_TRANSACTION_ACTIVE=0; DEPLOY_ROLLBACK_DONE=0; DEPLOY_CLEANUP_DONE=0; '
        'EXCLUDES=(--exclude=.env); '
        'rollback_deep_readiness() { return 0; }; '
        'recover_previous_deploy_if_needed'
    )
    return _bash(
        body,
        env={
            "PATH": f"{paths['fake_bin']}:{os.environ['PATH']}",
            "FAKE_SYSTEMCTL_STATE": str(paths["fake_state"]),
            "FAKE_NGINX_STATE": str(paths["fake_state"]),
        },
    )


@pytest.mark.parametrize(
    ("fault", "privacy_key"),
    [
        ("missing", None),
        ("duplicate", CANONICAL_PRIVACY_KEY),
        ("short_hex", CANONICAL_PRIVACY_KEY[:-1]),
        ("low_distinct_bytes", "a" * 64),
        ("placeholder", "replace-with-private-64-hex-chars"),
        ("quoted", f'"{CANONICAL_PRIVACY_KEY}"'),
        ("escaped", rf"{CANONICAL_PRIVACY_KEY[:60]}\x41"),
        ("uppercase", CANONICAL_PRIVACY_KEY.upper()),
        ("quoted_31_bytes", f'"{CANONICAL_PRIVACY_KEY[:62]}"'),
        ("leading_whitespace", f" {CANONICAL_PRIVACY_KEY}"),
        ("trailing_whitespace", f"{CANONICAL_PRIVACY_KEY} "),
        ("crlf", f"{CANONICAL_PRIVACY_KEY}\r"),
    ],
)
def test_invalid_privacy_hmac_key_is_zero_mutation_before_beta_deploy(
    tmp_path: Path, fault: str, privacy_key: str | None,
) -> None:
    target = tmp_path / "live-code"
    target.mkdir()
    code = target / "app.py"
    code.write_bytes(b"live-code-sentinel\n")

    runtime_root = tmp_path / "runtime"
    release = runtime_root / "releases/old"
    release.mkdir(parents=True)
    current = runtime_root / "current"
    current.symlink_to(release)
    unit = tmp_path / "structural-web.service"
    unit.write_bytes(b"unit-sentinel\n")
    nginx_vhost = tmp_path / "beta-structural.conf"
    nginx_vhost.write_bytes(b"nginx-sentinel\n")
    journal = runtime_root / "deploy-journal.json"
    journal.write_bytes(b"journal-sentinel\n")
    auth_data = tmp_path / "auth-data"

    auth_env = tmp_path / "beta-auth.env"
    valid_key = CANONICAL_PRIVACY_KEY
    lines = [
        "AUTH_ENABLED=true",
        "AUTH_SITE_ROLE=beta",
        "JWT_SECRET=J7w!Q2m#L9x@R4c%N8k&T6p*W3z$H5jK",
        "AUTH_LINK_BASE_URL=https://beta.structural.bytedance.city",
        f"AUTH_DATA_DIR={auth_data}",
        "SMTP_HOST=smtp.private.test",
        "SMTP_PORT=587",
        "SMTP_FROM_EMAIL=mailer@private.test",
        "SMTP_USERNAME=mailer",
        "SMTP_PASSWORD=mail-password",
        "ADMIN_NOTIFICATION_EMAIL=admin@private.test",
        "AUTH_TRUSTED_PROXY_IPS=127.0.0.1",
    ]
    if privacy_key is not None:
        lines.insert(3, f"STRUCTURAL_PRIVACY_HMAC_KEY={privacy_key}")
    if fault == "duplicate":
        lines.insert(4, f"STRUCTURAL_PRIVACY_HMAC_KEY={valid_key}")
    auth_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    auth_env.chmod(0o600)

    immutable_files = {
        path: path.read_bytes() for path in (code, unit, nginx_vhost, journal)
    }
    current_link = os.readlink(current)
    result = _source_deploy(
        "validate_beta_auth_config",
        env={
            "SOURCE": str(ROOT),
            "TARGET": str(target),
            "STRUCTURAL_RUNTIME_ROOT": str(runtime_root),
            "STRUCTURAL_RUNTIME_PYTHON": sys.executable,
            "STRUCTURAL_DEPLOY_JOURNAL": str(journal),
            "STRUCTURAL_SYSTEMD_UNIT_TARGET": str(unit),
            "STRUCTURAL_NGINX_VHOST_TARGET": str(nginx_vhost),
            "STRUCTURAL_BETA_AUTH_ENV_FILE": str(auth_env),
        },
    )

    assert result.returncode != 0, (result.stdout, result.stderr)
    assert {path: path.read_bytes() for path in immutable_files} == immutable_files
    assert current.is_symlink() and os.readlink(current) == current_link
    assert not auth_data.exists()


def test_privacy_hmac_validator_rejects_noncanonical_utf8(
    tmp_path: Path,
) -> None:
    value = "结构同构隐私密钥-2026-AbCdEfG"
    assert len(value) < 32 <= len(value.encode("utf-8"))
    assert len(set(value.encode("utf-8"))) >= 12

    result = _source_deploy(
        'validate_privacy_hmac_key "$TEST_PRIVACY_KEY"',
        env={
            "SOURCE": str(ROOT),
            "TARGET": str(tmp_path / "target"),
            "STRUCTURAL_RUNTIME_PYTHON": sys.executable,
            "TEST_PRIVACY_KEY": value,
        },
    )

    assert result.returncode != 0


def test_privacy_key_validation_precedes_every_beta_deploy_mutation() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    function_start = deploy.index("validate_beta_auth_config()")
    function_end = deploy.index("\n}\n\nprepare_beta_auth_data_dir", function_start)
    function_body = deploy[function_start:function_end]
    assert "STRUCTURAL_PRIVACY_HMAC_KEY" in function_body
    assert 'validate_privacy_hmac_key "$privacy_hmac_key"' in function_body
    assert '"$RUNTIME_PYTHON" -I -c' in deploy
    assert 're.fullmatch(rb"[0-9a-f]{64}", raw)' in deploy
    assert "mkdir -p" not in function_body

    main_start = deploy.index("deploy_guard_install rollback_deploy deploy_cleanup_once")
    auth_validation = deploy.index("validate_beta_auth_config\n", main_start)
    lock_mutation = deploy.index("exec 9>/var/lock/structural-isomorphism-deploy.lock", main_start)
    auth_data_mutation = deploy.index("prepare_beta_auth_data_dir\n", main_start)
    source_validation = deploy.index("deploy_validate_source_checkout", main_start)
    assert auth_validation < lock_mutation < auth_data_mutation < source_validation


def test_deploy_builds_before_sync_and_rolls_back_all_mutable_state() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert deploy.index('runtime_prepare "$RUNTIME_REQUIREMENTS"') < deploy.index(
        '"${CMD[@]}" | tail -10'
    )
    switch_at = deploy.index("runtime_switch ||")
    assert switch_at < deploy.index('systemctl restart "$SERVICE"', switch_at)
    assert "restore-models.sh" not in deploy
    assert "STRUCTURAL_MODEL_PATH=$ARTIFACT_ROOT/structural-v2" in deploy
    assert '"$RUNTIME_CURRENT/bin/python"' in deploy
    assert 'deployment_restore_transaction_state' in helper
    assert 'runtime_publish_attestation "$PUBLIC_RUNTIME_ATTESTATION"' in deploy
    assert '$TARGET/venv/bin/pip' not in deploy
    assert 'runtime_pip "$RUNTIME_RESOLVER_DIR" install' in helper
    assert 'runtime_pip "$RUNTIME_BUILD_DIR" install' in helper
    assert 'runtime_pip "$RUNTIME_BUILD_DIR" freeze --all' in helper
    assert "/bin/pip" not in helper
    assert 'runtime_pip "$release" check' in helper
    assert 'Environment="PYTHONDONTWRITEBYTECODE=1"' in unit
    assert 'Environment="SETUPTOOLS_USE_DISTUTILS=stdlib"' in unit
    assert 'Environment="STRUCTURAL_PROJECT_ROOT=/root/Projects/structural-isomorphism"' in unit
    assert 'Environment="PYTHONPATH=' not in unit
    assert (
        "/usr/bin/env PYTHONDONTWRITEBYTECODE=1 SETUPTOOLS_USE_DISTUTILS=stdlib "
        "STRUCTURAL_PROJECT_ROOT=/root/Projects/structural-isomorphism" in unit
    )
    assert "/bin/python -I -B -m uvicorn" in unit
    assert "export SETUPTOOLS_USE_DISTUTILS=stdlib" in deploy
    assert "export PYTHONDONTWRITEBYTECODE=1" in deploy
    assert '"$RUNTIME_CURRENT/bin/python" - <<' not in deploy
    assert '"$RUNTIME_CURRENT/bin/python" -B -' in deploy
    assert "systemd_validate_tracked_unit_contract" in deploy
    assert "STRUCTURAL_PROJECT_ROOT=$project_root" in helper
    assert '"$release/bin/python" -I -B - \\' in helper
    assert '"$RUNTIME_CURRENT/bin/python" -I -B - \\' in helper
    assert 'RUNTIME_RELEASE="$RUNTIME_RELEASES/$RUNTIME_ID"' in helper
    assert '"$RUNTIME_RELEASES/.staging.' in helper
    assert 'mv "$RUNTIME_BUILD_DIR"' not in helper
    assert 'chmod -R a-w "$RUNTIME_BUILD_DIR"' in helper
    assert 'rsync -a --delete --checksum' in helper
    assert 'os.replace(sys.argv[1], sys.argv[2])' in helper
    assert "deploy_validate_source_checkout" in deploy
    assert "deploy_source_snapshot_prepare" in deploy
    assert "deploy_verify_code_identity" in deploy
    assert "GIT_LFS_SKIP_SMUDGE=1" in helper
    assert "member.islnk()" in helper
    assert "hardlinks/devices/special files are forbidden" in helper
    assert "--filter=':- .gitignore'" not in deploy
    assert "deploy_journal_write success" in deploy
    assert "runtime_gc_releases" in deploy
    assert "RUNTIME_FINGERPRINT_BACKUP_READY=1" in helper
    assert 'systemctl show "$SERVICE" --property=FragmentPath --value' in deploy
    assert 'systemctl show "$SERVICE" --property=DropInPaths --value' in deploy
    assert 'systemctl show "$SERVICE" --property=ExecStart --value' in deploy
    assert 'systemctl enable "$SERVICE"' in deploy
    assert (
        "SETUPTOOLS_USE_DISTUTILS=stdlib "
        "STRUCTURAL_PROJECT_ROOT=/root/Projects/structural-isomorphism "
        "/root/structural-runtime/current/bin/python -I -B" in unit
    )
    assert (
        "--app-dir /root/Projects/structural-isomorphism/web/backend" in unit
    )
    assert "/root/Projects/structural-isomorphism/venv/bin/python" not in unit
    assert "scripts/deploy-versioned-runtime.sh" in workflow
    assert "'structural_isomorphism/**'" in workflow
    assert "Verify immutable runtime attestation" in workflow
    assert "requirements_sha256" in workflow and "cpython-311" in workflow
    assert '"starlette": "0.46.2"' in workflow


def test_systemd_installer_and_tracked_unit_share_exact_runtime_contract(
    tmp_path: Path,
) -> None:
    current = "/root/structural-runtime/current"
    auth_env = "/root/.config/structural-isomorphism/beta-auth.env"
    app_dir = "/root/Projects/structural-isomorphism/web/backend"
    accepted = _bash(
        "systemd_validate_tracked_unit_contract "
        f"{shlex.quote(str(UNIT))} {current} {auth_env} {app_dir}"
    )
    assert accepted.returncode == 0, accepted.stderr

    weakened = tmp_path / "structural-web.service"
    weakened.write_text(
        UNIT.read_text(encoding="utf-8").replace(
            f"{current}/bin/python -I -B -m uvicorn",
            f"{current}/bin/python -I -m uvicorn",
        ),
        encoding="utf-8",
    )
    rejected = _bash(
        "if systemd_validate_tracked_unit_contract "
        f"{shlex.quote(str(weakened))} {current} {auth_env} {app_dir}; then exit 97; fi"
    )
    assert rejected.returncode == 0, rejected.stderr
    assert "does not use the attested current runtime" in rejected.stderr

    for conflict in (
        'Environment="PYTHONDONTWRITEBYTECODE=0"',
        'Environment="SETUPTOOLS_USE_DISTUTILS=local"',
        'Environment="STRUCTURAL_PROJECT_ROOT=/root/poison"',
        'Environment="PYTHONPATH=/root/poison"',
        (
            "UnsetEnvironment=PYTHONDONTWRITEBYTECODE "
            "SETUPTOOLS_USE_DISTUTILS STRUCTURAL_PROJECT_ROOT"
        ),
        "ExecStart=/bin/false",
    ):
        poisoned = tmp_path / f"poisoned-{len(conflict)}.service"
        poisoned.write_text(
            UNIT.read_text(encoding="utf-8") + conflict + "\n",
            encoding="utf-8",
        )
        rejected = _bash(
            "if systemd_validate_tracked_unit_contract "
            f"{shlex.quote(str(poisoned))} {current} {auth_env} {app_dir}; then exit 97; fi"
        )
        assert rejected.returncode == 0, rejected.stderr

    for old_fragment, replacement in (
        (" -I -B -m uvicorn", " -B -m uvicorn"),
        (f" --app-dir {app_dir}", ""),
        ("STRUCTURAL_PROJECT_ROOT=/root/Projects/structural-isomorphism ", ""),
        (
            "STRUCTURAL_PROJECT_ROOT=/root/Projects/structural-isomorphism",
            "STRUCTURAL_PROJECT_ROOT=/root/Projects/poison",
        ),
        (app_dir, "/root/Projects/structural-isomorphism-v4/web/backend"),
    ):
        legacy = tmp_path / f"legacy-{len(old_fragment)}.service"
        legacy.write_text(
            UNIT.read_text(encoding="utf-8").replace(old_fragment, replacement),
            encoding="utf-8",
        )
        rejected = _bash(
            "if systemd_validate_tracked_unit_contract "
            f"{shlex.quote(str(legacy))} {current} {auth_env} {app_dir}; then exit 97; fi"
        )
        assert rejected.returncode == 0, rejected.stderr


def test_beta_workflow_executes_schema2_composite_attestation_guard() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(
        candidate
        for candidate in workflow["jobs"]["deploy"]["steps"]
        if candidate.get("name", "").startswith("Verify immutable runtime attestation")
    )
    verifier = step["run"].rsplit("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]

    requirements_sha = "a" * 64
    graph_sha = "b" * 64
    content_sha = "c" * 64
    freeze_sha = _composite_freeze_sha256(graph_sha, content_sha)
    expected_sha = "d" * 40
    attestation = {
        "schema_version": 2,
        "python_abi": "cpython-311",
        "python_version": "3.11.14",
        "runtime_id": f"cpython-311-{requirements_sha}-{freeze_sha}",
        "requirements_sha256": requirements_sha,
        "resolved_graph_sha256": graph_sha,
        "runtime_content_sha256": content_sha,
        "installed_freeze_sha256": freeze_sha,
        "fastapi": "0.115.14",
        "pydantic": "2.6.1",
        "starlette": "0.46.2",
        "uvicorn": "0.27.1",
        "git_sha": expected_sha,
        "deployed_at": "2026-07-16T00:00:00Z",
    }

    def execute(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-I", "-c", verifier],
            env={
                **os.environ,
                "EXPECTED_SHA": expected_sha,
                "REQUIREMENTS_SHA": requirements_sha,
                "ATTESTATION": json.dumps(payload),
                "VERSION": json.dumps(attestation),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    accepted = execute(attestation)
    assert accepted.returncode == 0, accepted.stderr

    invalid_payloads = []
    for field, value in (
        ("schema_version", 1),
        ("resolved_graph_sha256", graph_sha.upper()),
        ("runtime_content_sha256", "g" * 64),
        ("runtime_content_sha256", None),
        ("installed_freeze_sha256", "e" * 64),
        ("runtime_id", f"cpython-311-{requirements_sha}-{graph_sha}"),
    ):
        payload = dict(attestation)
        payload[field] = value
        invalid_payloads.append(payload)
    for payload in invalid_payloads:
        rejected = execute(payload)
        assert rejected.returncode != 0, payload


def test_systemd_runtime_command_ignores_python_environment_file_injection(
    tmp_path: Path,
) -> None:
    poison_marker = tmp_path / "python-env-injection.marker"
    canonical_marker = tmp_path / "canonical-import.marker"
    poison = tmp_path / "poison"
    poison.mkdir()
    injected = (
        "from pathlib import Path\n"
        f"Path({str(poison_marker)!r}).write_text('executed')\n"
        "raise RuntimeError('python environment injection executed')\n"
    )
    for module in ("sitecustomize.py", "uvicorn.py", "main.py"):
        (poison / module).write_text(injected, encoding="utf-8")
    poisoned_package = poison / "structural_isomorphism"
    poisoned_package.mkdir()
    (poisoned_package / "__init__.py").write_text(injected, encoding="utf-8")

    environment_file = tmp_path / "hostile.env"
    environment_file.write_text(
        f"PYTHONPATH={poison}\n"
        f"PYTHONHOME={poison}\n"
        f"STRUCTURAL_PROJECT_ROOT={poison}\n",
        encoding="utf-8",
    )
    hostile_environment = os.environ.copy()
    for line in environment_file.read_text(encoding="utf-8").splitlines():
        name, value = line.split("=", 1)
        hostile_environment[name] = value

    project_root = tmp_path / "project"
    app_dir = project_root / "web" / "backend"
    app_dir.mkdir(parents=True)
    canonical_package = project_root / "structural_isomorphism"
    canonical_package.mkdir()
    (canonical_package / "__init__.py").write_text(
        "ORIGIN = 'canonical'\n", encoding="utf-8"
    )
    (app_dir / "main.py").write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from fastapi import FastAPI\n"
        "project_root = Path(os.environ['STRUCTURAL_PROJECT_ROOT']).resolve()\n"
        "sys.path.insert(0, str(project_root))\n"
        "import structural_isomorphism\n"
        "origin = Path(structural_isomorphism.__file__).resolve()\n"
        "if project_root not in origin.parents:\n"
        "    raise RuntimeError(f'noncanonical structural package: {origin}')\n"
        f"Path({str(canonical_marker)!r}).write_text(str(origin))\n"
        "app = FastAPI()\n",
        encoding="utf-8",
    )
    exec_line = next(
        line
        for line in UNIT.read_text(encoding="utf-8").splitlines()
        if line.startswith("ExecStart=")
    )
    command = shlex.split(exec_line.removeprefix("ExecStart="))
    command[command.index("/root/structural-runtime/current/bin/python")] = sys.executable
    command[
        command.index(
            "STRUCTURAL_PROJECT_ROOT=/root/Projects/structural-isomorphism"
        )
    ] = f"STRUCTURAL_PROJECT_ROOT={project_root}"
    command[command.index("/root/Projects/structural-isomorphism/web/backend")] = str(
        app_dir
    )
    command[command.index("5004")] = "0"
    assert command[:5] == [
        "/usr/bin/env",
        "PYTHONDONTWRITEBYTECODE=1",
        "SETUPTOOLS_USE_DISTUTILS=stdlib",
        f"STRUCTURAL_PROJECT_ROOT={project_root}",
        sys.executable,
    ]
    assert command[5:10] == ["-I", "-B", "-m", "uvicorn", "main:app"]

    process = subprocess.Popen(
        command,
        cwd=tmp_path,
        env=hostile_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and process.poll() is None:
            assert not poison_marker.exists()
            if canonical_marker.exists():
                break
            time.sleep(0.05)
        was_running = process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    if process.returncode != 0:
        assert "Application startup complete." in stderr, stdout + stderr
        assert "error while attempting to bind" in stderr, stdout + stderr
    else:
        assert was_running, stdout + stderr
    assert canonical_marker.exists(), stdout + stderr
    canonical_origin = Path(canonical_marker.read_text(encoding="utf-8"))
    assert project_root in canonical_origin.parents
    assert canonical_origin == canonical_package / "__init__.py"
    assert not poison_marker.exists()


def test_beta_dispatch_pins_one_full_main_reachable_commit() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    entrypoint = DISPATCH_ENTRYPOINT.read_text(encoding="utf-8")
    dispatcher = FORCED_DISPATCHER.read_text(encoding="utf-8")

    assert '"beta-backend $DEPLOY_SHA"' in workflow
    assert "DEPLOY_SHA: ${{ github.sha }}" in workflow
    assert "^[0-9a-f]{40}$" in entrypoint
    assert 'reset --hard "$DEPLOY_SHA"' in entrypoint
    assert 'DEPLOY_COMMIT="$DEPLOY_SHA"' in entrypoint
    assert 'STRUCTURAL_DEPLOY_LOCK_HELD=1' in entrypoint
    assert 'FETCHED_MAIN_SHA=' in entrypoint
    assert 'merge-base --is-ancestor "$DEPLOY_SHA" "$FETCHED_MAIN_SHA"' in entrypoint
    assert "git rev-parse --short" not in workflow
    assert ".startswith(expected_sha)" not in workflow
    assert "got_sha != expected_sha" in workflow
    assert "SSH_ORIGINAL_COMMAND" in dispatcher
    assert "^beta-backend\\ ([0-9a-f]{40})$" in dispatcher
    assert 'PATH=/usr/sbin:/usr/bin:/sbin:/bin' in dispatcher


@pytest.mark.parametrize(
    "original_command",
    [
        "",
        "beta-backend",
        "beta-backend " + "a" * 39,
        "beta-backend " + "A" * 40,
        "beta-backend  " + "a" * 40,
        " beta-backend " + "a" * 40,
        "beta-backend " + "a" * 40 + " ",
        "beta-backend " + "a" * 40 + "; id",
        "beta-backend\t" + "a" * 40,
        "beta-backend " + "a" * 40 + "\nwhoami",
        "deploy",
        "phase-deploy",
        "ews US,HK",
    ],
)
def test_forced_dispatcher_rejects_every_noncanonical_original_command(
    tmp_path: Path, original_command: str,
) -> None:
    dispatcher, record = _make_forced_dispatch_fixture(tmp_path)
    result = subprocess.run(
        [str(dispatcher)],
        env={
            **os.environ,
            "PATH": str(tmp_path / "attacker-bin"),
            "SSH_ORIGINAL_COMMAND": original_command,
            "DISPATCH_RECORD": str(record),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stderr
    assert not record.exists()


def test_forced_dispatcher_passes_only_the_exact_full_sha_and_rejects_arguments(
    tmp_path: Path,
) -> None:
    dispatcher, record = _make_forced_dispatch_fixture(tmp_path)
    deploy_sha = "b" * 40
    env = {
        **os.environ,
        "PATH": str(tmp_path / "attacker-bin"),
        "SSH_ORIGINAL_COMMAND": f"beta-backend {deploy_sha}",
        "STRUCTURAL_BETA_REPO": "/attacker/repository",
        "GIT_DIR": "/attacker/git-dir",
    }

    accepted = subprocess.run(
        [str(dispatcher)], env=env, capture_output=True, text=True, check=False
    )
    assert accepted.returncode == 0, accepted.stderr
    assert record.read_text(encoding="utf-8").splitlines() == [
        "beta", "1", deploy_sha, "unset", "unset",
    ]

    record.unlink()
    rejected = subprocess.run(
        [str(dispatcher), "unexpected"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 2, rejected.stderr
    assert not record.exists()

    env["SSH_ORIGINAL_COMMAND"] = f"phase-deploy {deploy_sha}"
    env["STRUCTURAL_PHASE_REPO"] = "/attacker/phase"
    env["GIT_WORK_TREE"] = "/attacker/work-tree"
    phase = subprocess.run(
        [str(dispatcher)], env=env, capture_output=True, text=True, check=False
    )
    assert phase.returncode == 0, phase.stderr
    assert record.read_text(encoding="utf-8").splitlines() == [
        "phase", "1", deploy_sha, "unset", "unset",
    ]


def test_dispatcher_installer_is_idempotent_atomic_and_checkable(tmp_path: Path) -> None:
    env, install_dir, authorized_keys, key_blob = _dispatcher_install_env(tmp_path)
    unrelated = authorized_keys.read_text(encoding="utf-8")

    installed = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert installed.returncode == 0, installed.stderr
    checked = subprocess.run(
        [str(DISPATCH_INSTALLER), "--check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    expected_line = (
        f'restrict,command="{install_dir}/deploy-dispatcher.sh" '
        f"ssh-ed25519 {key_blob} structural-deploy"
    )
    content = authorized_keys.read_text(encoding="utf-8")
    assert content.startswith(unrelated)
    assert content.splitlines().count(expected_line) == 1
    assert stat.S_IMODE(authorized_keys.stat().st_mode) == 0o600
    for name, source in (
        ("install-nginx-privacy-vhost.sh", ROOT / "scripts" / "install-nginx-privacy-vhost.sh"),
        ("deploy-phase-detector-vps.sh", PHASE_DEPLOY_ENGINE),
        ("deploy-phase-detector-entrypoint.sh", ROOT / "scripts" / "deploy-phase-detector-entrypoint.sh"),
        ("deploy-dispatcher.sh", FORCED_DISPATCHER),
        ("deploy-beta-backend.sh", DISPATCH_ENTRYPOINT),
    ):
        installed_script = install_dir / name
        assert installed_script.read_bytes() == source.read_bytes()
        assert stat.S_IMODE(installed_script.stat().st_mode) == 0o755

    repeated = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert repeated.returncode == 0, repeated.stderr
    assert authorized_keys.read_text(encoding="utf-8").splitlines().count(expected_line) == 1


def test_dispatcher_installer_ignores_pythonpath_and_shell_startup_injection(
    tmp_path: Path,
) -> None:
    env, _install_dir, _authorized_keys, _key_blob = _dispatcher_install_env(tmp_path)
    poison = tmp_path / "poison"
    poison.mkdir()
    marker = tmp_path / "pythonpath-imported"
    (poison / "shlex.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
        "raise RuntimeError('PYTHONPATH shadow executed')\n",
        encoding="utf-8",
    )
    shell_marker = tmp_path / "shell-startup-executed"
    bash_env = tmp_path / "bash-env"
    bash_env.write_text(f"printf injected > {shlex.quote(str(shell_marker))}\n")
    env.update({"PYTHONPATH": str(poison), "BASH_ENV": str(bash_env)})

    result = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert not shell_marker.exists()


def test_dispatcher_installer_rejects_non_ssh_wire_key_before_mutation(
    tmp_path: Path,
) -> None:
    env, install_dir, authorized_keys, _key_blob = _dispatcher_install_env(tmp_path)
    public_key = Path(env["STRUCTURAL_DEPLOY_PUBLIC_KEY_FILE"])
    public_key.write_text(
        "ssh-ed25519 c3RydWN0dXJhbC1kZXBsb3kta2V5LW1hdGVyaWFs invalid\n",
        encoding="utf-8",
    )
    authorized_before = authorized_keys.read_bytes()

    result = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "not accepted by ssh-keygen" in result.stderr
    assert not list(install_dir.iterdir())
    assert authorized_keys.read_bytes() == authorized_before


def test_dispatcher_installer_check_fails_closed_on_tamper(tmp_path: Path) -> None:
    env, install_dir, authorized_keys, _key_blob = _dispatcher_install_env(tmp_path)
    installed = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert installed.returncode == 0, installed.stderr

    (install_dir / "deploy-beta-backend.sh").write_text("#!/bin/sh\nexit 0\n")
    rejected_script = subprocess.run(
        [str(DISPATCH_INSTALLER), "--check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected_script.returncode != 0
    assert "differs from tracked source" in rejected_script.stderr

    healed = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert healed.returncode == 0, healed.stderr
    authorized_keys.write_text(authorized_keys.read_text().replace("restrict,", "no-pty,"))
    rejected_key = subprocess.run(
        [str(DISPATCH_INSTALLER), "--check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected_key.returncode != 0
    assert "missing or non-canonical" in rejected_key.stderr


def test_dispatcher_installer_rejects_duplicate_key_and_symlink_target(
    tmp_path: Path,
) -> None:
    env, install_dir, authorized_keys, key_blob = _dispatcher_install_env(tmp_path)
    duplicate = f"ssh-ed25519 {key_blob} duplicate\n"
    authorized_keys.write_text(duplicate + duplicate, encoding="utf-8")
    duplicate_result = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert duplicate_result.returncode != 0
    assert "appears more than once" in duplicate_result.stderr
    assert not list(install_dir.iterdir())

    authorized_keys.write_text("# no deployment key\n", encoding="utf-8")
    victim = tmp_path / "operator-script"
    victim.write_text("operator bytes\n", encoding="utf-8")
    (install_dir / "deploy-dispatcher.sh").symlink_to(victim)
    symlink_result = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert symlink_result.returncode != 0
    assert "unsafe installed script" in symlink_result.stderr
    assert victim.read_text(encoding="utf-8") == "operator bytes\n"


def test_dispatcher_installer_preflights_every_target_before_mutation(
    tmp_path: Path,
) -> None:
    env, install_dir, authorized_keys, _key_blob = _dispatcher_install_env(tmp_path)
    dispatcher = install_dir / "deploy-dispatcher.sh"
    phase = install_dir / "deploy-phase-detector-entrypoint.sh"
    dispatcher.write_text("old dispatcher\n", encoding="utf-8")
    phase.write_text("old phase entrypoint\n", encoding="utf-8")
    dispatcher.chmod(0o700)
    phase.chmod(0o700)
    (install_dir / "deploy-beta-backend.sh").mkdir()
    authorized_before = authorized_keys.read_bytes()

    result = subprocess.run(
        [str(DISPATCH_INSTALLER)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "unsafe installed script" in result.stderr
    assert dispatcher.read_text(encoding="utf-8") == "old dispatcher\n"
    assert phase.read_text(encoding="utf-8") == "old phase entrypoint\n"
    assert stat.S_IMODE(dispatcher.stat().st_mode) == 0o700
    assert stat.S_IMODE(phase.stat().st_mode) == 0o700
    assert authorized_keys.read_bytes() == authorized_before
    assert not list(install_dir.glob(".*.*"))


def test_dispatcher_installer_records_replace_before_directory_fsync() -> None:
    installer = DISPATCH_INSTALLER.read_text(encoding="utf-8")
    commit_loop = installer.index("for temporary, target in staged:")
    replace = installer.index("commit_stage(temporary, target)", commit_loop)
    record = installer.index("committed.append(target)", replace)
    fsync = installer.index("fsync_parent(target)", record)

    assert replace < record < fsync


@pytest.mark.parametrize(
    "invalid_sha",
    ["", "a" * 12, "A" * 40, "g" * 40, "a" * 41, "../main"],
)
def test_dispatcher_rejects_invalid_sha_before_git_mutation(
    tmp_path: Path, invalid_sha: str,
) -> None:
    repository, _first, second, _side = _make_dispatch_repository(tmp_path)
    result_path = tmp_path / "dispatch-result"
    arguments = [str(DISPATCH_ENTRYPOINT)]
    if invalid_sha:
        arguments.append(invalid_sha)
    result = subprocess.run(
        arguments,
        env=_dispatch_env(tmp_path, repository, result_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stderr
    assert not result_path.exists()
    assert _git(repository, "rev-parse", "HEAD") == second


def test_dispatcher_rejects_known_commit_that_never_reached_main(tmp_path: Path) -> None:
    repository, _first, second, side = _make_dispatch_repository(tmp_path)
    result_path = tmp_path / "dispatch-result"
    result = subprocess.run(
        [str(DISPATCH_ENTRYPOINT), side],
        env=_dispatch_env(tmp_path, repository, result_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "not reachable from origin/main" in result.stderr
    assert not result_path.exists()
    assert _git(repository, "rev-parse", "HEAD") == second


def test_dispatcher_pins_event_sha_when_main_advances_before_dispatch(
    tmp_path: Path,
) -> None:
    repository, first, second, _side = _make_dispatch_repository(tmp_path)
    result_path = tmp_path / "dispatch-result"
    result = subprocess.run(
        [str(DISPATCH_ENTRYPOINT), first],
        env=_dispatch_env(tmp_path, repository, result_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result_path.read_text(encoding="utf-8").splitlines() == [first, first]
    assert _git(repository, "rev-parse", "refs/remotes/origin/main") == second
    assert _git(repository, "rev-parse", "HEAD") == first


def test_phase_installed_engine_pins_requested_sha_when_main_advances_before_dispatch(
    tmp_path: Path,
) -> None:
    repository, first, second, _side = _make_dispatch_repository(tmp_path)
    env = _dispatch_env(tmp_path, repository, tmp_path / "unused-beta-result")
    env.update({
        "STRUCTURAL_DEPLOY_LOCK_HELD": "1",
        "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
        "PHASE_DEPLOY_ENGINE": str(PHASE_DEPLOY_ENGINE),
        "REQUESTED_SHA": first,
    })
    _bind_phase_test_isolation(env, repository, tmp_path)

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$PHASE_DEPLOY_ENGINE"; phase_sync_exact_commit "$REQUESTED_SHA"',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert _git(repository, "rev-parse", "refs/remotes/origin/main") == second
    assert _git(repository, "rev-parse", "HEAD") == first


def test_beta_workflow_tracks_privacy_installation_inputs() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "- 'scripts/install-nginx-privacy-vhost.sh'" in workflow
    assert "- 'web/scripts/beta-structural.nginx.conf'" in workflow
    assert "- 'scripts/deploy-dispatcher.sh'" in workflow
    assert "- 'scripts/install-deploy-dispatcher.sh'" in workflow
    assert "needs: release-contracts" in workflow
    assert 'python-version: "3.11"' in workflow
    assert "tests/test_deploy_versioned_runtime.py" in workflow
    assert "tests/test_nginx_privacy_contract.py" in workflow
    assert "tests/test_production_smoke.py" in workflow
    assert "web/backend/tests/test_version.py" in workflow


def test_product_deploy_queues_are_isolated_while_the_host_lock_serializes() -> None:
    beta_workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    phase_workflow = yaml.safe_load(PHASE_WORKFLOW.read_text(encoding="utf-8"))
    beta_concurrency = beta_workflow["concurrency"]
    phase_concurrency = phase_workflow["concurrency"]

    assert beta_concurrency == {
        "group": "deploy-beta-backend",
        "cancel-in-progress": False,
        "queue": "single",
    }
    assert phase_concurrency == {
        "group": "deploy-phase-detector",
        "cancel-in-progress": False,
        "queue": "single",
    }
    assert beta_concurrency["group"] != phase_concurrency["group"]
    assert beta_workflow["jobs"]["release-contracts"]["timeout-minutes"] == 20
    assert beta_workflow["jobs"]["deploy"]["timeout-minutes"] == 90
    assert phase_workflow["jobs"]["deploy"]["timeout-minutes"] == 90

    beta_entrypoint = DISPATCH_ENTRYPOINT.read_text(encoding="utf-8")
    beta_deploy = DEPLOY.read_text(encoding="utf-8")
    phase_deploy = PHASE_DEPLOY_ENGINE.read_text(encoding="utf-8")
    assert beta_entrypoint.count("flock -w 2700 9") == 1
    assert beta_deploy.count("flock -w 2700 9") == 1
    assert phase_deploy.count("flock -w 2700 9") == 2
    assert "flock -w 900 9" not in beta_entrypoint
    assert "flock -w 900 9" not in beta_deploy
    assert "flock -w 900 9" not in phase_deploy


def test_phase_workflow_uses_python_311_for_the_complete_syntax_gate() -> None:
    workflow = PHASE_WORKFLOW.read_text(encoding="utf-8")
    setup_at = workflow.index("- name: Set up Phase API Python")
    syntax_at = workflow.index("- name: Verify repository Python 3.11 syntax")
    validation_at = workflow.index(
        "- name: Validate Phase API and privacy release contracts"
    )

    assert setup_at < syntax_at < validation_at
    assert "python-version: '3.11'" in workflow[setup_at:syntax_at]
    assert "python-version: '3.12'" not in workflow
    assert "run: python -I scripts/check_python_syntax.py" in workflow[
        syntax_at:validation_at
    ]
    assert "python -m venv /tmp/phase-api-import" in workflow[validation_at:]


def test_phase_workflow_installs_exact_test_dependency_closure() -> None:
    workflow = yaml.safe_load(PHASE_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    matches = [
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("name") == "Validate Phase API and privacy release contracts"
    ]
    assert len(matches) == 1
    validation = matches[0]
    run = validation["run"]

    assert steps.index(validation) < next(
        index
        for index, step in enumerate(steps)
        if isinstance(step, dict) and step.get("name") == "SSH deploy"
    )
    assert "if" not in validation and "continue-on-error" not in validation
    assert run.count("/tmp/phase-api-import/bin/pip install") == 1
    assert "-r v4/product/d1_phase_detector/api/requirements.txt" in run
    assert "pytest==9.0.3 httpx==0.27.2" in run
    assert run.index("/tmp/phase-api-import/bin/pip check") < run.index(
        "from v4.product.d1_phase_detector.api.main import app"
    )
    assert (
        "tests/test_deploy_versioned_runtime.py::"
        "test_phase_workflow_installs_exact_test_dependency_closure"
    ) in run
    for target in (
        "tests/test_phase_privacy_gate.py",
        "tests/test_nginx_privacy_contract.py",
        "v4/product/d1_phase_detector/api/tests/test_privacy_middleware.py",
        "v4/product/d1_phase_detector/api/tests/test_waitlist.py",
    ):
        assert target in run


def test_phase_workflow_uses_the_same_strict_exact_sha_dispatcher() -> None:
    workflow = PHASE_WORKFLOW.read_text(encoding="utf-8")
    entrypoint = PHASE_DISPATCH_ENTRYPOINT.read_text(encoding="utf-8")
    deploy = PHASE_DEPLOY_ENGINE.read_text(encoding="utf-8")

    assert '"phase-deploy $DEPLOY_SHA"' in workflow
    assert "DEPLOY_SHA: ${{ github.sha }}" in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "$DEPLOY_SHA"' in workflow
    assert "^[0-9a-f]{40}$" in entrypoint
    assert 'PHASE_DEPLOY_COMMIT="$DEPLOY_SHA"' in entrypoint
    assert 'ENGINE="$SCRIPT_DIR/deploy-phase-detector-vps.sh"' in entrypoint
    assert 'NGINX_PRIVACY_INSTALLER="$PHASE_ENGINE_DIR/install-nginx-privacy-vhost.sh"' in deploy
    assert '$REPO/scripts/install-nginx-privacy-vhost.sh' not in deploy
    assert 'merge-base --is-ancestor "$deploy_sha" "$fetched_main_sha"' in deploy
    assert 'reset --hard "$deploy_sha"' in deploy
    assert "git reset --hard origin/main" not in deploy

    recover_at = deploy.index("recover_phase_outer_transaction || {", deploy.index("if [[ \"${STRUCTURAL_PHASE_RECOVERY_ONLY"))
    previous_at = deploy.index('PREVIOUS_SHA="$(git -C "$REPO" rev-parse --verify HEAD)"', recover_at)
    journal_at = deploy.index("begin_phase_outer_transaction || {", previous_at)
    reset_at = deploy.index('phase_sync_exact_commit "$DEPLOY_SHA"', journal_at)
    assert recover_at < previous_at < journal_at < reset_at


def test_ews_workflow_is_a_read_only_frozen_snapshot_monitor() -> None:
    workflow = EWS_WORKFLOW.read_text(encoding="utf-8")

    assert "EWS Frozen Snapshot Monitor" in workflow
    assert "VPS_DEPLOY_KEY" not in workflow
    assert "ssh " not in workflow
    assert 'payload.get("n_tickers") == 597' in workflow
    assert 'payload.get("price_provenance") == "demo"' in workflow


def test_smoke_binds_each_trigger_to_an_explicit_deployed_beta_release() -> None:
    workflow = SITE_SMOKE_WORKFLOW.read_text(encoding="utf-8")

    assert 'workflows: ["Deploy Beta Backend"]' in workflow
    assert "expected_git_sha:" in workflow
    assert "required: true" in workflow
    assert 'EXPECTED_SHA="$MANUAL_SHA"' in workflow
    assert 'EXPECTED_SHA="$DEPLOY_SHA"' in workflow
    assert "actions/workflows/deploy-beta-backend.yml/runs" in workflow
    assert "status=success" in workflow
    assert ".workflow_runs[0].head_sha" in workflow
    assert "ref: ${{ steps.release.outputs.sha }}" in workflow
    assert 'python-version: "3.11"' in workflow
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_BETA_SHA"' in workflow
    assert '--expected-git-sha "$EXPECTED_BETA_SHA"' in workflow
    assert '--expected-git-sha "$(git rev-parse HEAD)"' not in workflow


def test_failed_runtime_build_leaves_current_and_code_untouched(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    old_release = runtime_root / "releases" / "old"
    old_release.mkdir(parents=True)
    current = runtime_root / "current"
    current.symlink_to(old_release)
    target = tmp_path / "target"
    target.mkdir()
    code = target / "app.py"
    code.write_text("old\n", encoding="utf-8")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.14\n"
        "starlette==0.46.2\n"
        "uvicorn[standard]==0.27.1\n"
        "pydantic==2.6.1\n",
        encoding="utf-8",
    )
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == -c ]]; then echo cpython-311; exit 0; fi\n"
        "if [[ ${1:-} == -m && ${2:-} == venv ]]; then exit 47; fi\n"
        "exit 48\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(str(fake_python))}; '
        f'if runtime_prepare {shlex.quote(str(requirements))}; then exit 91; fi; '
        'test "$(readlink "$RUNTIME_CURRENT")" = '
        f'{shlex.quote(str(old_release))}; '
        f'test "$(cat {shlex.quote(str(code))})" = old; '
        'test ! -e "$RUNTIME_RELEASE"; '
        'test -z "$(find "$RUNTIME_RELEASES" -maxdepth 1 -name ".build-*" -print -quit)"',
    )

    assert result.returncode == 0, result.stderr
    assert current.resolve() == old_release.resolve()
    assert code.read_text(encoding="utf-8") == "old\n"


def test_runtime_validate_and_prepare_reuse_succeed_under_nounset(
    tmp_path: Path,
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.14\n"
        "starlette==0.46.2\n"
        "uvicorn[standard]==0.27.1\n"
        "pydantic==2.6.1\n",
        encoding="utf-8",
    )
    requirements_sha = hashlib.sha256(requirements.read_bytes()).hexdigest()
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha=requirements_sha
    )
    freeze_sha = release.name.rsplit("-", 1)[1]
    result = _bash(
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"RUNTIME_RELEASE={shlex.quote(str(release))}; "
        f"RUNTIME_ID={shlex.quote(release.name)}; "
        f"RUNTIME_REQUIREMENTS_SHA256={requirements_sha}; "
        f"RUNTIME_FREEZE_SHA256={freeze_sha}; "
        f"runtime_validate_release {shlex.quote(str(release))}; "
        f"runtime_prepare {shlex.quote(str(requirements))}; "
        f'test "$RUNTIME_RELEASE" = {shlex.quote(str(release))}',
        env={"STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag},
    )

    assert result.returncode == 0, result.stderr
    assert f"Reusing attested release: {release.name}" in result.stdout


def test_runtime_prepare_cold_build_and_reuse_succeed_with_local_wheels(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    for package, version in _RUNTIME_PACKAGE_VERSIONS.items():
        _write_runtime_test_wheel(wheelhouse, package, version)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.14\n"
        "starlette==0.46.2\n"
        "uvicorn[standard]==0.27.1\n"
        "pydantic==2.6.1\n",
        encoding="utf-8",
    )
    runtime_root = tmp_path / "runtime-one"
    second_runtime_root = tmp_path / "runtime-two"
    result = _bash(
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"runtime_prepare {shlex.quote(str(requirements))}; "
        'cold_release="$RUNTIME_RELEASE"; '
        'test -f "$cold_release/.complete"; '
        'test -f "$cold_release/resolved-packages.txt"; '
        'runtime_validate_release "$cold_release"; '
        f"runtime_prepare {shlex.quote(str(requirements))}; "
        'test "$RUNTIME_RELEASE" = "$cold_release"; '
        'cold_runtime_id="${cold_release##*/}"; '
        f"RUNTIME_ROOT={shlex.quote(str(second_runtime_root))}; "
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"runtime_prepare {shlex.quote(str(requirements))}; "
        'test "${RUNTIME_RELEASE##*/}" = "$cold_runtime_id"',
        env={
            "PIP_FIND_LINKS": str(wheelhouse),
            "PIP_NO_INDEX": "1",
            "STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag,
            "STRUCTURAL_RUNTIME_MIN_FREE_KB": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Building immutable runtime staging directory" in result.stdout
    assert "Reusing attested release:" in result.stdout
    releases = list((runtime_root / "releases").iterdir())
    assert len(releases) == 1
    assert not releases[0].name.startswith(".staging.")
    payload = json.loads((releases[0] / "attestation.json").read_text())
    assert payload["schema_version"] == 2
    assert releases[0].name.endswith(payload["installed_freeze_sha256"])
    assert payload["installed_freeze_sha256"] == _composite_freeze_sha256(
        payload["resolved_graph_sha256"], payload["runtime_content_sha256"]
    )
    second_releases = list((second_runtime_root / "releases").iterdir())
    assert [path.name for path in second_releases] == [releases[0].name]


def test_schema1_release_is_rollback_only_and_never_reused_by_prepare(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    for package, version in _RUNTIME_PACKAGE_VERSIONS.items():
        _write_runtime_test_wheel(wheelhouse, package, version)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.14\n"
        "starlette==0.46.2\n"
        "uvicorn[standard]==0.27.1\n"
        "pydantic==2.6.1\n",
        encoding="utf-8",
    )
    requirements_sha = hashlib.sha256(requirements.read_bytes()).hexdigest()
    runtime_root = tmp_path / "runtime"
    legacy = _downgrade_runtime_release_to_schema1(
        _make_runtime_release(
            runtime_root / "releases", requirements_sha=requirements_sha
        )
    )
    _make_runtime_release_writable(legacy)
    with (legacy / "pyvenv.cfg").open("a", encoding="utf-8") as stream:
        stream.write(f"command = {sys.executable} -m venv {legacy}\n")
    legacy_cache = _runtime_site_packages(legacy) / "fastapi" / "__pycache__"
    legacy_cache.mkdir()
    (legacy_cache / f"__init__.{sys.implementation.cache_tag}.pyc").write_bytes(
        b"legacy-runtime-bytecode"
    )
    for root, directories, files in os.walk(legacy):
        for name in [".", *directories, *files]:
            path = Path(root) if name == "." else Path(root, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    (runtime_root / "current").symlink_to(legacy)

    result = _bash(
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        "runtime_capture_current; "
        f"runtime_prepare {shlex.quote(str(requirements))}; "
        'test "$RUNTIME_RELEASE" != "$RUNTIME_PREVIOUS_TARGET"',
        env={
            "PIP_FIND_LINKS": str(wheelhouse),
            "PIP_NO_INDEX": "1",
            "STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag,
            "STRUCTURAL_RUNTIME_MIN_FREE_KB": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert legacy.is_dir()
    releases = [path for path in (runtime_root / "releases").iterdir() if path.is_dir()]
    schemas = {
        json.loads((path / "attestation.json").read_text())["schema_version"]
        for path in releases
    }
    assert schemas == {1, 2}


def test_source_checkout_accepts_exact_clean_commit_and_ignored_secret(tmp_path: Path) -> None:
    source, commit = _make_git_source(tmp_path)
    (source / ".env").write_text("SECRET=never-log-this\n", encoding="utf-8")

    result = _bash(
        f'deploy_validate_source_checkout {shlex.quote(str(source))} {commit}'
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == commit
    assert "SECRET" not in result.stdout + result.stderr


@pytest.mark.parametrize("deploy_commit", ["HEAD", "main", "a" * 12, "A" * 40])
def test_source_checkout_rejects_ref_prefix_and_nonlowercase_commit_identity(
    tmp_path: Path, deploy_commit: str,
) -> None:
    source, _commit = _make_git_source(tmp_path)
    result = _bash(
        f'if deploy_validate_source_checkout {shlex.quote(str(source))} '
        f'{shlex.quote(deploy_commit)}; then exit 112; fi'
    )

    assert result.returncode == 0, result.stderr
    assert "one full lowercase Git SHA" in result.stderr


@pytest.mark.parametrize("unsafe_state", ["dirty", "untracked", "mismatch", "missing_git"])
def test_source_checkout_rejects_ambiguous_publish_state(
    tmp_path: Path, unsafe_state: str,
) -> None:
    source, commit = _make_git_source(tmp_path)
    expected = commit
    if unsafe_state == "dirty":
        (source / "app.py").write_text("print('dirty')\n", encoding="utf-8")
    elif unsafe_state == "untracked":
        (source / "publish-me.py").write_text("unsafe\n", encoding="utf-8")
    elif unsafe_state == "mismatch":
        (source / "second.py").write_text("second\n", encoding="utf-8")
        _git(source, "add", "second.py")
        _git(source, "commit", "-qm", "second")
    else:
        source = tmp_path / "not-a-repository"
        source.mkdir()

    result = _bash(
        f'if deploy_validate_source_checkout {shlex.quote(str(source))} {expected}; '
        "then exit 93; fi"
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("link_target", ["/tmp/archive-escape", "../../../../../../archive-escape"])
def test_commit_snapshot_rejects_absolute_or_escaping_allowlisted_symlink(
    tmp_path: Path, link_target: str,
) -> None:
    source = tmp_path / "source"
    link = source / "dataset" / "v1" / "null_controls" / "_VERDICT.md"
    link.parent.mkdir(parents=True)
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "deploy-test@example.test")
    _git(source, "config", "user.name", "Deploy Test")
    link.symlink_to(link_target)
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "unsafe link")
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'if deploy_source_snapshot_prepare {shlex.quote(str(source))} '
        f'{_git(source, "rev-parse", "HEAD")}; then exit 101; fi; '
        'test -z "$(find "$RUNTIME_ROOT" -mindepth 1 -print -quit)"'
    )

    assert result.returncode == 0, result.stderr
    assert "unsafe target" in result.stderr or "escapes the commit snapshot" in result.stderr


def test_real_commit_snapshot_excludes_lfs_material_and_absolute_legacy_link(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    commit = _git(ROOT, "rev-parse", "HEAD")
    body = (
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'deploy_source_snapshot_prepare {shlex.quote(str(ROOT))} {commit}; '
        'grep -Fx "web/data/kb_embeddings.npy" "$DEPLOY_LFS_PATHS_FILE"; '
        'grep -Fx "web/data/kb_embeddings.npy" "$DEPLOY_PROTECTED_PATHS_FILE"; '
        'grep -Fx "v4/validation/markov-memory-fidelity/data/noaa_storm_2024.csv" '
        '"$DEPLOY_PROTECTED_PATHS_FILE"; '
        'test -f "$DEPLOY_SOURCE_SNAPSHOT/structural_isomorphism/model.py"; '
        'test ! -e "$DEPLOY_SOURCE_SNAPSHOT/web/data/kb_embeddings.npy"; '
        'test ! -e "$DEPLOY_SOURCE_SNAPSHOT/v4/validation/markov-memory-fidelity/data/noaa_storm_2024.csv"; '
        'test -L "$DEPLOY_SOURCE_SNAPSHOT/dataset/v1/null_controls/_VERDICT.md"; '
        'resolved=$(realpath "$DEPLOY_SOURCE_SNAPSHOT/dataset/v1/null_controls/_VERDICT.md"); '
        'case "$resolved" in "$DEPLOY_SOURCE_SNAPSHOT"/*) ;; *) exit 102 ;; esac; '
        'deploy_source_snapshot_cleanup; '
        'test -z "$(find "$RUNTIME_ROOT" -mindepth 1 -print -quit)"'
    )
    result = _bash(body)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("escape_at", ["root", "parent"])
def test_target_preflight_rejects_symlink_escape_boundaries(
    tmp_path: Path, escape_at: str,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    if escape_at == "root":
        target = tmp_path / "target"
        target.symlink_to(real_target)
    else:
        target = real_target
        (target / "web").symlink_to(outside)
    proof = tmp_path / "tree-proof.json"
    proof.write_text(
        json.dumps({
            "entries": {
                "web/app.py": {"mode": "100644", "oid": "0" * 40},
            },
        }) + "\n",
        encoding="utf-8",
    )
    protected = tmp_path / "protected.txt"
    protected.write_text("", encoding="utf-8")
    symlinks = tmp_path / "symlinks.json"
    symlinks.write_text("{}\n", encoding="utf-8")

    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'TARGET={shlex.quote(str(target))}; '
        f'DEPLOY_ARCHIVE_TREE_PROOF={shlex.quote(str(proof))}; '
        f'DEPLOY_PROTECTED_PATHS_FILE={shlex.quote(str(protected))}; '
        f'DEPLOY_SYMLINK_PROOF_FILE={shlex.quote(str(symlinks))}; '
        "if deploy_validate_target_tree; then exit 103; fi"
    )

    assert result.returncode == 0, result.stderr
    assert not (outside / "app.py").exists()


def test_target_preflight_rejects_protected_model_root_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "models").symlink_to(outside)
    proof = tmp_path / "tree-proof.json"
    proof.write_text(
        json.dumps({
            "entries": {
                "models/fixture.bin": {"mode": "100644", "oid": "0" * 40},
            },
        }) + "\n",
        encoding="utf-8",
    )
    protected = tmp_path / "protected.txt"
    protected.write_text("models/fixture.bin\n", encoding="utf-8")
    symlinks = tmp_path / "symlinks.json"
    symlinks.write_text("{}\n", encoding="utf-8")

    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'TARGET={shlex.quote(str(target))}; '
        f'DEPLOY_ARCHIVE_TREE_PROOF={shlex.quote(str(proof))}; '
        f'DEPLOY_PROTECTED_PATHS_FILE={shlex.quote(str(protected))}; '
        f'DEPLOY_SYMLINK_PROOF_FILE={shlex.quote(str(symlinks))}; '
        "if deploy_validate_target_tree; then exit 103; fi"
    )

    assert result.returncode == 0, result.stderr
    assert "symlink boundary" in result.stderr
    assert not any(outside.iterdir())


def test_model_restore_revalidates_destination_before_write(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "models").symlink_to(outside)
    restore = ROOT / "scripts" / "restore-models.sh"

    result = subprocess.run(
        ["bash", str(restore)],
        env={
            **os.environ,
            "REPO_ROOT": str(target),
            "MODEL_DIR": str(target / "models" / "structural-v2"),
            "VENV_PYTHON": sys.executable,
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "unsafe model destination" in result.stderr
    assert not any(outside.iterdir())


def test_forward_sync_is_authoritative_and_manifest_proves_commit_bytes(
    tmp_path: Path,
) -> None:
    if not shutil.which("rsync"):
        pytest.skip("rsync is required for the deploy transaction")
    source, commit = _make_git_source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    deployed = target / "app.py"
    deployed.write_text("print('stale!!')\n", encoding="utf-8")
    future = time.time() + 3600
    os.utime(deployed, (future, future))
    (target / "obsolete.py").write_text("delete me\n", encoding="utf-8")
    (target / ".env.runtime").write_text("KEEP=1\n", encoding="utf-8")
    (target / ".env.local").write_text("LOCAL_SECRET=keep\n", encoding="utf-8")
    (target / "models").mkdir()
    (target / "models" / "artifact.bin").write_text("keep model\n", encoding="utf-8")

    rsync_help = subprocess.run(
        ["rsync", "--help"], capture_output=True, text=True, check=False
    ).stdout
    delete_flag = "--delete-delay" if "--delete-delay" in rsync_help else "--delete"
    sync = subprocess.run(
        [
            "rsync", "-av", delete_flag,
            "--exclude=.git/", "--exclude=.env.runtime", "--exclude=.env.local",
            "--exclude=models/",
            f"{source}/", f"{target}/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sync.returncode == 0, sync.stderr
    manifest = target / ".structural-deploy-manifest.json"
    protected_paths = tmp_path / "protected-paths.txt"
    protected_paths.write_text("", encoding="utf-8")
    symlink_proof = tmp_path / "symlink-proof.json"
    symlink_proof.write_text("{}\n", encoding="utf-8")
    result = _bash(
        f'SOURCE={shlex.quote(str(source))}; TARGET={shlex.quote(str(target))}; '
        f'SOURCE_HEAD_SHA={commit}; RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_MANIFEST_TARGET={shlex.quote(str(manifest))}; '
        f'DEPLOY_PROTECTED_PATHS_FILE={shlex.quote(str(protected_paths))}; '
        f'DEPLOY_SYMLINK_PROOF_FILE={shlex.quote(str(symlink_proof))}; '
        "deploy_verify_code_identity"
    )

    assert result.returncode == 0, result.stderr
    assert deployed.read_bytes() == (source / "app.py").read_bytes()
    assert not (target / "obsolete.py").exists()
    assert (target / ".env.runtime").read_text(encoding="utf-8") == "KEEP=1\n"
    assert (target / ".env.local").read_text(encoding="utf-8") == "LOCAL_SECRET=keep\n"
    assert (target / "models" / "artifact.bin").is_file()
    proof = json.loads(manifest.read_text(encoding="utf-8"))
    assert proof["commit"] == commit
    assert any(entry["path"] == "app.py" for entry in proof["entries"])

    deployed.write_text("print('tampered')\n", encoding="utf-8")
    tampered = _bash(
        f'SOURCE={shlex.quote(str(source))}; TARGET={shlex.quote(str(target))}; '
        f'SOURCE_HEAD_SHA={commit}; RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_MANIFEST_TARGET={shlex.quote(str(manifest))}; '
        f'DEPLOY_PROTECTED_PATHS_FILE={shlex.quote(str(protected_paths))}; '
        f'DEPLOY_SYMLINK_PROOF_FILE={shlex.quote(str(symlink_proof))}; '
        "if deploy_verify_code_identity; then exit 94; fi"
    )
    assert tampered.returncode == 0, tampered.stderr


def test_empty_previous_unit_is_removed_on_rollback(tmp_path: Path) -> None:
    unit = tmp_path / "structural-web.service"
    result = _bash(
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; '
        'systemd_unit_capture; '
        'test "$SYSTEMD_UNIT_PREEXISTED" = 0; '
        'printf "new unit\\n" > "$SYSTEMD_UNIT_TARGET"; '
        'SYSTEMD_UNIT_INSTALLED=1; systemd_unit_restore; '
        'test ! -e "$SYSTEMD_UNIT_TARGET"',
    )

    assert result.returncode == 0, result.stderr
    assert not unit.exists()


def test_systemd_state_capture_and_rollback_preserve_disabled_inactive(
    tmp_path: Path,
) -> None:
    fake_bin, state = _make_fake_systemctl(tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    unit = tmp_path / "structural-web.service"
    unit.write_text("old unit\n", encoding="utf-8")
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; SERVICE=structural-web; '
        'systemd_unit_capture; capture_systemd_service_state; '
        'test "$SYSTEMD_STATE_CAPTURED" = 1; '
        'test "$SYSTEMD_SERVICE_WAS_ENABLED" = 0; '
        'test "$SYSTEMD_SERVICE_WAS_ACTIVE" = 0; '
        'printf "enabled\n" > "$FAKE_SYSTEMCTL_STATE/enabled"; '
        'printf "active\n" > "$FAKE_SYSTEMCTL_STATE/active"; '
        'restore_systemd_service_state; '
        'test "$(cat "$FAKE_SYSTEMCTL_STATE/enabled")" = disabled; '
        'test "$(cat "$FAKE_SYSTEMCTL_STATE/active")" = inactive',
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_SYSTEMCTL_STATE": str(state),
        },
    )

    assert result.returncode == 0, result.stderr
    calls = (state / "calls").read_text(encoding="utf-8")
    assert "disable structural-web" in calls
    assert "stop structural-web" in calls
    assert "reset-failed structural-web" in calls


@pytest.mark.parametrize("error_command", ["is-enabled", "is-active"])
def test_systemd_state_capture_rejects_dbus_and_command_errors(
    tmp_path: Path, error_command: str,
) -> None:
    fake_bin, state = _make_fake_systemctl(tmp_path)
    unit = tmp_path / "structural-web.service"
    unit.write_text("old unit\n", encoding="utf-8")
    result = _bash(
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; SERVICE=structural-web; '
        'SYSTEMD_UNIT_PREEXISTED=1; '
        'if capture_systemd_service_state; then exit 109; fi; '
        'test "$SYSTEMD_STATE_CAPTURED" = 0',
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_SYSTEMCTL_STATE": str(state),
            "FAKE_SYSTEMCTL_ERROR_COMMAND": error_command,
        },
    )

    assert result.returncode == 0, result.stderr
    assert "failed unexpectedly" in result.stderr


def test_known_auth_dropin_migrates_transactionally_and_rolls_back(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    unit = tmp_path / "structural-web.service"
    unit.write_text("old unit\n", encoding="utf-8")
    auth_env = tmp_path / "beta-auth.env"
    dropin = tmp_path / "structural-web.service.d" / "auth.conf"
    dropin.parent.mkdir()
    dropin.write_text(
        f"[Service]\nEnvironmentFile={auth_env}\n", encoding="utf-8"
    )
    dropin.chmod(0o600)
    expected_dropin = f"[Service]\nEnvironmentFile={auth_env}"

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(dropin))}; '
        'systemd_unit_capture; '
        f'systemd_dropin_capture {shlex.quote(str(auth_env))}; '
        'test "$SYSTEMD_UNIT_CAPTURED" = 1; '
        'test "$SYSTEMD_DROPIN_CAPTURED" = 1; '
        'test "$SYSTEMD_DROPIN_PREEXISTED" = 1; '
        'printf "new unit\n" > "$SYSTEMD_UNIT_TARGET"; SYSTEMD_UNIT_INSTALLED=1; '
        'systemd_dropin_migrate; test ! -e "$SYSTEMD_DROPIN_TARGET"; '
        'systemd_unit_restore; '
        'test "$(cat "$SYSTEMD_UNIT_TARGET")" = "old unit"; '
        f'test "$(cat "$SYSTEMD_DROPIN_TARGET")" = '
        f'{shlex.quote(expected_dropin)}',
    )

    assert result.returncode == 0, result.stderr
    assert unit.read_text(encoding="utf-8") == "old unit\n"
    assert dropin.read_text(encoding="utf-8") == (
        f"[Service]\nEnvironmentFile={auth_env}\n"
    )


def test_partial_systemd_install_is_journaled_before_write_and_restores_preimage(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    code_backup = runtime_root / ".rollback-code.test"
    code_backup.mkdir()
    code_excludes = runtime_root / ".rollback-excludes.test"
    code_excludes.write_text(".env\n", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    unit = tmp_path / "structural-web.service"
    unit.write_bytes(b"old unit exact\n")
    source = tmp_path / "candidate.service"
    source.write_bytes(b"new unit\n")
    fake_bin = tmp_path / "partial-install-bin"
    fake_bin.mkdir()
    install = fake_bin / "install"
    install.write_text(
        "#!/bin/sh\n"
        'printf "partial write" > "$4"\n'
        "exit 55\n",
        encoding="utf-8",
    )
    install.chmod(0o755)
    journal = runtime_root / "deploy-journal.json"
    runtime_id = f"cpython-311-{'a' * 64}-{'b' * 64}"
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        f'SOURCE_HEAD_SHA={"a" * 40}; RUNTIME_ID={shlex.quote(runtime_id)}; '
        f'TARGET={shlex.quote(str(target))}; SERVICE=structural-web; '
        f'DEPLOY_CODE_BACKUP={shlex.quote(str(code_backup))}; DEPLOY_CODE_SNAPSHOT_READY=1; '
        f'DEPLOY_CODE_EXCLUDES_BACKUP={shlex.quote(str(code_excludes))}; '
        'DEPLOY_CODE_EXCLUDES_READY=1; RUNTIME_PREVIOUS_CAPTURED=1; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; systemd_unit_capture; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(tmp_path / "auth.conf"))}; '
        'systemd_dropin_capture /auth.env; SYSTEMD_STATE_CAPTURED=1; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(target / ".env.runtime"))}; '
        'RUNTIME_FINGERPRINT_BACKUP_READY=1; '
        f'NGINX_VHOST_TARGET={shlex.quote(str(tmp_path / "beta.conf"))}; '
        'NGINX_VHOST_CAPTURED=1; deploy_journal_write snapshot; '
        'RETIRED_TRACKED_CAPTURED=1; '
        f'if systemd_unit_install_transaction {shlex.quote(str(source))} '
        f'{shlex.quote(str(unit))}; then exit 113; fi; '
        'test "$SYSTEMD_UNIT_INSTALLED" = 1; '
        'status=0; deploy_journal_check_start || status=$?; test "$status" = 10; '
        'systemd_unit_restore; cmp -s "$SYSTEMD_UNIT_TARGET" "$SYSTEMD_UNIT_BACKUP"',
        env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    assert unit.read_bytes() == b"old unit exact\n"
    payload = json.loads(journal.read_text(encoding="utf-8"))
    assert payload["stage"] == "unit_installing"
    assert payload["systemd_unit_installed"] is True


@pytest.mark.parametrize(
    "contents",
    [
        "[Service]\nEnvironmentFile=/unexpected\n",
        "[Service]\nEnvironmentFile=/expected\nExecStart=/bin/false\n",
    ],
)
def test_unknown_systemd_dropin_is_rejected_without_mutation(
    tmp_path: Path, contents: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    dropin = tmp_path / "auth.conf"
    dropin.write_text(contents, encoding="utf-8")
    dropin.chmod(0o600)
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(dropin))}; '
        'if systemd_dropin_capture /expected; then exit 110; fi; '
        'test "$SYSTEMD_DROPIN_CAPTURED" = 0; '
        'test -z "$SYSTEMD_DROPIN_BACKUP"',
    )

    assert result.returncode == 0, result.stderr
    assert dropin.read_text(encoding="utf-8") == contents


def test_runtime_fingerprint_preimage_restores_exact_bytes_and_absence(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    fingerprint = tmp_path / ".env.runtime"
    fingerprint.write_bytes(b"OLD=exact\n")
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(fingerprint))}; '
        'runtime_fingerprint_capture; '
        'test "$RUNTIME_FINGERPRINT_BACKUP_READY" = 1; '
        'test "$RUNTIME_FINGERPRINT_PREEXISTED" = 1; '
        'printf "NEW=bad\n" > "$RUNTIME_FINGERPRINT_TARGET"; '
        'runtime_fingerprint_restore; '
        'test "$(cat "$RUNTIME_FINGERPRINT_TARGET")" = "OLD=exact"',
    )
    assert result.returncode == 0, result.stderr
    assert fingerprint.read_bytes() == b"OLD=exact\n"

    fingerprint.unlink()
    absent = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(fingerprint))}; '
        'runtime_fingerprint_capture; '
        'test "$RUNTIME_FINGERPRINT_PREEXISTED" = 0; '
        'printf "NEW=remove\n" > "$RUNTIME_FINGERPRINT_TARGET"; '
        'runtime_fingerprint_restore; test ! -e "$RUNTIME_FINGERPRINT_TARGET"',
    )
    assert absent.returncode == 0, absent.stderr
    assert not fingerprint.exists()


def test_nginx_preimage_retry_preserves_evidence_then_succeeds(
    tmp_path: Path,
) -> None:
    fake_bin, state = _make_fake_systemctl(tmp_path)
    _add_fake_nginx(fake_bin, state)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    vhost = tmp_path / "beta.conf"
    vhost.write_text("old vhost\n", encoding="utf-8")
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'NGINX_VHOST_TARGET={shlex.quote(str(vhost))}; '
        'nginx_vhost_capture; test "$NGINX_VHOST_CAPTURED" = 1; '
        'printf "new vhost\n" > "$NGINX_VHOST_TARGET"; NGINX_VHOST_INSTALLED=1; '
        'printf "1\n" > "$FAKE_NGINX_STATE/failures"; '
        'if nginx_vhost_restore; then exit 111; fi; '
        'test "$NGINX_VHOST_INSTALLED" = 1; '
        'test -f "$NGINX_VHOST_BACKUP"; '
        'nginx_vhost_restore; test "$NGINX_VHOST_INSTALLED" = 0; '
        'test "$(cat "$NGINX_VHOST_TARGET")" = "old vhost"',
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_SYSTEMCTL_STATE": str(state),
            "FAKE_NGINX_STATE": str(state),
        },
    )

    assert result.returncode == 0, result.stderr
    assert vhost.read_text(encoding="utf-8") == "old vhost\n"
    assert (state / "failures").read_text(encoding="utf-8").strip() == "0"
    assert "reload nginx" in (state / "calls").read_text(encoding="utf-8")


def test_post_switch_readiness_rollback_restores_runtime_unit_and_code(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    old_release = _make_runtime_release(releases, requirements_sha="a" * 64)
    new_release = _make_runtime_release(releases, requirements_sha="b" * 64)
    current = runtime_root / "current"
    current.symlink_to(old_release)

    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("old code\n", encoding="utf-8")
    (target / ".structural-deploy-manifest.json").write_text(
        "old manifest\n", encoding="utf-8"
    )
    (target / "venv").mkdir()
    (target / "venv" / "legacy-python").write_text("kept\n", encoding="utf-8")
    systemd_unit = tmp_path / "structural-web.service"
    systemd_unit.write_text("old unit\n", encoding="utf-8")

    body = (
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'TARGET={shlex.quote(str(target))}; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(systemd_unit))}; '
        'EXCLUDES=(--exclude=venv/ --exclude=.env '
        '--exclude=.structural-deploy-manifest.json); '
        'runtime_capture_current; deploy_code_snapshot; systemd_unit_capture; '
        f'RUNTIME_RELEASE={shlex.quote(str(new_release))}; runtime_switch; '
        'printf "new code\\n" > "$TARGET/app.py"; '
        'printf "new file\\n" > "$TARGET/new.py"; '
        'printf "new manifest\\n" > "$TARGET/.structural-deploy-manifest.json"; '
        'printf "new unit\\n" > "$SYSTEMD_UNIT_TARGET"; SYSTEMD_UNIT_INSTALLED=1; '
        '# Simulate the caller detecting failed post-switch readiness.\n'
        'deployment_restore_transaction_state; '
        'test "$(readlink "$RUNTIME_CURRENT")" = '
        f'{shlex.quote(str(old_release))}; '
        'test "$(cat "$TARGET/app.py")" = "old code"; '
        'test ! -e "$TARGET/new.py"; '
        'test "$(cat "$TARGET/.structural-deploy-manifest.json")" = "old manifest"; '
        'test "$(cat "$TARGET/venv/legacy-python")" = kept; '
        'test "$(cat "$SYSTEMD_UNIT_TARGET")" = "old unit"; '
        'deployment_transaction_cleanup'
    )
    result = _bash(body)

    assert result.returncode == 0, result.stderr
    assert current.resolve() == old_release.resolve()
    assert (target / "app.py").read_text(encoding="utf-8") == "old code\n"
    assert not (target / "new.py").exists()
    assert systemd_unit.read_text(encoding="utf-8") == "old unit\n"


def test_first_runtime_migration_rolls_back_to_legacy_target_venv(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    new_release = _make_runtime_release(
        runtime_root / "releases", requirements_sha="c" * 64
    )

    target = tmp_path / "target"
    legacy_python = target / "venv" / "bin" / "python"
    legacy_python.parent.mkdir(parents=True)
    legacy_python.write_text("legacy runtime\n", encoding="utf-8")
    (target / "app.py").write_text("legacy code\n", encoding="utf-8")
    unit = tmp_path / "structural-web.service"
    unit.write_text(f"ExecStart={legacy_python}\n", encoding="utf-8")

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'TARGET={shlex.quote(str(target))}; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; '
        'EXCLUDES=(--exclude=venv/); '
        'runtime_capture_current; test "$RUNTIME_PREVIOUS_PRESENT" = 0; '
        'deploy_code_snapshot; systemd_unit_capture; '
        f'RUNTIME_RELEASE={shlex.quote(str(new_release))}; runtime_switch; '
        'printf "candidate code\\n" > "$TARGET/app.py"; '
        'printf "candidate unit\\n" > "$SYSTEMD_UNIT_TARGET"; SYSTEMD_UNIT_INSTALLED=1; '
        'deployment_restore_transaction_state; '
        'test ! -e "$RUNTIME_CURRENT"; '
        'test "$(cat "$TARGET/app.py")" = "legacy code"; '
        'test "$(cat "$TARGET/venv/bin/python")" = "legacy runtime"; '
        f'test "$(cat "$SYSTEMD_UNIT_TARGET")" = '
        f'{shlex.quote(f"ExecStart={legacy_python}")}; '
        'deployment_transaction_cleanup'
    )

    assert result.returncode == 0, result.stderr
    assert not (runtime_root / "current").exists()
    assert legacy_python.read_text(encoding="utf-8") == "legacy runtime\n"
    assert (target / "app.py").read_text(encoding="utf-8") == "legacy code\n"


def test_incomplete_release_that_current_resolves_to_is_never_deleted(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.14\n"
        "starlette==0.46.2\n"
        "uvicorn[standard]==0.27.1\n"
        "pydantic==2.6.1\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    abi = sys.implementation.cache_tag
    runtime_root = tmp_path / "runtime"
    incomplete = runtime_root / "releases" / f"{abi}-{digest}-{'f' * 64}"
    incomplete.mkdir(parents=True)
    (incomplete / ".building").touch()
    (runtime_root / "current").symlink_to(incomplete)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'if runtime_prepare {shlex.quote(str(requirements))}; then exit 92; fi; '
        f'test -f {shlex.quote(str(incomplete / ".building"))}',
        env={"STRUCTURAL_EXPECTED_PYTHON_ABI": abi},
    )

    assert result.returncode == 0, result.stderr
    assert (incomplete / ".building").is_file()


@pytest.mark.parametrize("unsafe_target", ["relative", "broken", "outside", "release_symlink"])
def test_current_runtime_rejects_unsafe_rollback_targets(
    tmp_path: Path, unsafe_target: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    valid = _make_runtime_release(releases, requirements_sha="1" * 64)
    current = runtime_root / "current"
    if unsafe_target == "relative":
        current.symlink_to(f"releases/{valid.name}")
    elif unsafe_target == "broken":
        current.symlink_to(releases / f"cpython-311-{'2' * 64}-{'3' * 64}")
    elif unsafe_target == "outside":
        current.symlink_to(tmp_path)
    else:
        alias = releases / f"cpython-311-{'4' * 64}-{'5' * 64}"
        alias.symlink_to(valid)
        current.symlink_to(alias)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        "if runtime_capture_current; then exit 95; fi"
    )

    assert result.returncode == 0, result.stderr
    assert current.is_symlink()


def test_current_runtime_regular_file_is_rejected(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "current").write_text("not a symlink\n", encoding="utf-8")
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        "if runtime_capture_current; then exit 96; fi"
    )
    assert result.returncode == 0, result.stderr


def test_current_runtime_mutable_release_is_rejected(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha="5" * 64
    )
    release.chmod(release.stat().st_mode | 0o200)
    (runtime_root / "current").symlink_to(release)
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        "if runtime_capture_current; then exit 104; fi"
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("launcher_state", "accepted"),
    [("missing", False), ("nonexecutable", True)],
)
def test_current_runtime_pip_launcher_obeys_record_without_being_executed(
    tmp_path: Path, launcher_state: str, accepted: bool,
) -> None:
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha="8" * 64
    )
    launchers = sorted((release / "bin").glob("pip*"))
    assert launchers
    launcher = launchers[0]
    if launcher_state == "missing":
        launcher.parent.chmod(launcher.parent.stat().st_mode | 0o200)
        launcher.unlink()
        launcher.parent.chmod(launcher.parent.stat().st_mode & ~0o222)
    else:
        launcher.chmod(0o444)
    current = runtime_root / "current"
    current.symlink_to(release)

    validation = (
        'runtime_capture_current; test "$RUNTIME_PREVIOUS_PRESENT" = 1; '
        f'test "$RUNTIME_PREVIOUS_TARGET" = {shlex.quote(str(release))}'
        if accepted
        else "if runtime_capture_current; then exit 105; fi"
    )
    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        + validation
    )

    assert result.returncode == 0, result.stderr


def test_current_runtime_rejects_forged_shell_executables(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    release = _make_forged_runtime_release(
        runtime_root / "releases", requirements_sha="f" * 64
    )
    current = runtime_root / "current"
    current.symlink_to(release)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        "if runtime_capture_current; then exit 105; fi"
    )

    assert result.returncode == 0, result.stderr
    assert current.resolve() == release.resolve()


@pytest.mark.parametrize("tamper", ["python", "package_metadata"])
def test_current_runtime_rejects_live_binary_or_package_tamper(
    tmp_path: Path, tamper: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha="e" * 64
    )
    if tamper == "python":
        binary = release / "bin" / "python"
        binary.parent.chmod(binary.parent.stat().st_mode | 0o200)
        binary.unlink()
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o555)
        binary.parent.chmod(binary.parent.stat().st_mode & ~0o222)
    else:
        metadata_file = next(release.rglob("pydantic-*.dist-info/METADATA"))
        metadata_file.chmod(metadata_file.stat().st_mode | 0o200)
        metadata_file.write_text(
            "Metadata-Version: 2.1\nName: pydantic\nVersion: 9.9.9\n",
            encoding="utf-8",
        )
        metadata_file.chmod(metadata_file.stat().st_mode & ~0o222)
    current = runtime_root / "current"
    current.symlink_to(release)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        "if runtime_capture_current; then exit 106; fi"
    )

    assert result.returncode == 0, result.stderr
    assert current.resolve() == release.resolve()


def test_production_model_is_only_the_validated_artifact_bundle() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")

    assert "restore-models.sh" not in deploy
    assert "restore-models.sh" not in unit
    assert "STRUCTURAL_MODEL_PATH=$ARTIFACT_ROOT/structural-v2" in deploy
    assert 'model_path=f"{artifact_root}/structural-v2"' in deploy
    assert deploy.index("Validating production artifact bundle") < deploy.index(
        "STRUCTURAL_MODEL_PATH=$ARTIFACT_ROOT/structural-v2"
    )


def test_rollback_revalidates_previous_target_against_symlink_swap(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    previous = _make_runtime_release(releases, requirements_sha="6" * 64)
    candidate = _make_runtime_release(releases, requirements_sha="7" * 64)
    current = runtime_root / "current"
    current.symlink_to(previous)
    displaced = releases / "displaced"

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; runtime_capture_current; '
        f'RUNTIME_RELEASE={shlex.quote(str(candidate))}; runtime_switch; '
        f'chmod -R u+w {shlex.quote(str(previous))}; '
        f'mv {shlex.quote(str(previous))} {shlex.quote(str(displaced))}; '
        f'ln -s {shlex.quote(str(tmp_path))} {shlex.quote(str(previous))}; '
        'if runtime_restore_previous; then exit 97; fi; '
        f'test "$(readlink "$RUNTIME_CURRENT")" = {shlex.quote(str(candidate))}'
    )

    assert result.returncode == 0, result.stderr
    assert current.resolve() == candidate.resolve()


def test_deployment_journal_blocks_nonterminal_restart_and_allows_terminal_state(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    journal = runtime_root / "deploy-journal.json"
    code_backup = runtime_root / ".rollback-code.test"
    code_backup.mkdir(parents=True)
    code_excludes = runtime_root / ".rollback-excludes.test"
    code_excludes.write_text(".env\n", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    runtime_id = f"cpython-311-{'a' * 64}-{'b' * 64}"
    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'SOURCE_HEAD_SHA="{"a" * 40}"; RUNTIME_ID={shlex.quote(runtime_id)}; '
        f'TARGET={shlex.quote(str(target))}; SERVICE=structural-web; '
        f'DEPLOY_CODE_BACKUP={shlex.quote(str(code_backup))}; DEPLOY_CODE_SNAPSHOT_READY=1; '
        f'DEPLOY_CODE_EXCLUDES_BACKUP={shlex.quote(str(code_excludes))}; '
        'DEPLOY_CODE_EXCLUDES_READY=1; '
        'RUNTIME_PREVIOUS_CAPTURED=1; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(tmp_path / "structural.service"))}; '
        'SYSTEMD_UNIT_CAPTURED=1; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(tmp_path / "auth.conf"))}; '
        'SYSTEMD_DROPIN_CAPTURED=1; SYSTEMD_STATE_CAPTURED=1; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(target / ".env.runtime"))}; '
        'RUNTIME_FINGERPRINT_BACKUP_READY=1; '
        f'NGINX_VHOST_TARGET={shlex.quote(str(tmp_path / "beta.conf"))}; '
        'NGINX_VHOST_CAPTURED=1; '
        'deploy_journal_check_start; deploy_journal_write snapshot; '
        'status=0; deploy_journal_check_start || status=$?; test "$status" = 10; '
        'deploy_journal_load_state; test "$JOURNAL_LOAD_COMPLETE" = 1; '
        'deploy_journal_write rolled_back; deploy_journal_check_start'
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(journal.read_text(encoding="utf-8"))
    assert payload["stage"] == "rolled_back"
    assert payload["code_backup"] == str(code_backup)
    assert payload["previous_runtime_captured"] is True
    assert payload["systemd_unit_captured"] is True
    assert payload["systemd_dropin_captured"] is True
    assert payload["systemd_state_captured"] is True
    assert payload["fingerprint_backup_ready"] is True
    assert payload["nginx_captured"] is True
    assert not list(journal.parent.glob("deploy-journal.json.tmp.*"))


def _write_valid_schema2_journal(tmp_path: Path, *, stage: str = "snapshot") -> Path:
    runtime_root = tmp_path / "runtime"
    journal = runtime_root / "deploy-journal.json"
    code_backup = runtime_root / ".rollback-code.test"
    code_backup.mkdir(parents=True)
    code_excludes = runtime_root / ".rollback-excludes.test"
    code_excludes.write_text(".env\n", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    runtime_id = f"cpython-311-{'a' * 64}-{'b' * 64}"
    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'SOURCE_HEAD_SHA="{"a" * 40}"; RUNTIME_ID={shlex.quote(runtime_id)}; '
        f'TARGET={shlex.quote(str(target))}; SERVICE=structural-web; '
        f'DEPLOY_CODE_BACKUP={shlex.quote(str(code_backup))}; DEPLOY_CODE_SNAPSHOT_READY=1; '
        f'DEPLOY_CODE_EXCLUDES_BACKUP={shlex.quote(str(code_excludes))}; '
        'DEPLOY_CODE_EXCLUDES_READY=1; '
        'RUNTIME_PREVIOUS_CAPTURED=1; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(tmp_path / "structural.service"))}; '
        'SYSTEMD_UNIT_CAPTURED=1; '
        f'SYSTEMD_DROPIN_TARGET={shlex.quote(str(tmp_path / "auth.conf"))}; '
        'SYSTEMD_DROPIN_CAPTURED=1; SYSTEMD_STATE_CAPTURED=1; '
        f'RUNTIME_FINGERPRINT_TARGET={shlex.quote(str(target / ".env.runtime"))}; '
        'RUNTIME_FINGERPRINT_BACKUP_READY=1; '
        f'NGINX_VHOST_TARGET={shlex.quote(str(tmp_path / "beta.conf"))}; '
        'NGINX_VHOST_CAPTURED=1; '
        f'deploy_journal_write {shlex.quote(stage)}'
    )
    assert result.returncode == 0, result.stderr
    return journal


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda payload, _root: payload.update(unexpected="field"), "schema/fields"),
        (lambda payload, _root: payload.update(code_backup="/tmp/outside"), "escaped runtime root"),
        (lambda payload, _root: payload.update(code_snapshot_ready=False), "incomplete preimages"),
        (lambda payload, _root: payload.update(systemd_unit_captured=False), "incomplete preimages"),
        (lambda payload, _root: payload.update(nginx_captured=False), "incomplete preimages"),
        (lambda payload, _root: payload.update(retired_relative_path="../escape"), "retired path"),
        (
            lambda payload, _root: payload.update(
                retired_captured=True,
                retired_was_present=False,
                retired_removed=True,
            ),
            "retired removal flags",
        ),
    ],
)
def test_schema2_journal_rejects_unknown_incomplete_and_unsafe_state(
    tmp_path: Path, mutation, expected: str,
) -> None:
    journal = _write_valid_schema2_journal(tmp_path)
    payload = json.loads(journal.read_text(encoding="utf-8"))
    mutation(payload, journal.parent)
    journal.write_text(json.dumps(payload), encoding="utf-8")

    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        'status=0; deploy_journal_check_start || status=$?; '
        'test "$status" != 0; test "$status" != 10'
    )

    assert result.returncode == 0, result.stderr
    assert expected in result.stderr


def test_journal_loader_propagates_partial_producer_failure(tmp_path: Path) -> None:
    journal = _write_valid_schema2_journal(tmp_path)
    counter = tmp_path / "python-count"
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/bin/sh\n"
        f"counter={shlex.quote(str(counter))}\n"
        "count=0\n"
        'test ! -f "$counter" || count=$(cat "$counter")\n'
        "count=$((count + 1))\n"
        'printf "%s\\n" "$count" > "$counter"\n'
        "if test \"$count\" = 1; then\n"
        f"  exec {shlex.quote(sys.executable)} \"$@\"\n"
        "fi\n"
        "printf 'JOURNAL_STAGE\\0snapshot\\0'\n"
        "exit 23\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(str(fake_python))}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        'if deploy_journal_load_state; then exit 108; fi; '
        'test "$JOURNAL_LOAD_COMPLETE" = 0; '
        'test -z "$(find "$(dirname "$DEPLOY_JOURNAL")" -maxdepth 1 '
        '-name "$(basename "$DEPLOY_JOURNAL").load.*" -print -quit)"'
    )

    assert result.returncode == 0, result.stderr
    assert counter.read_text(encoding="utf-8").strip() == "2"


def test_sigkill_is_recovered_by_new_process_and_second_recovery_is_idempotent(
    tmp_path: Path,
) -> None:
    paths = _stage_recoverable_transaction(tmp_path, wait_for_sigkill=True)
    assert paths["current"].resolve() == paths["new_release"].resolve()
    assert (paths["target"] / "app.py").read_text(encoding="utf-8") == "new code\n"
    assert not paths["retired"].exists()

    recovered = _recover_staged_transaction(paths)
    assert recovered.returncode == 0, recovered.stderr
    assert paths["current"].resolve() == paths["old_release"].resolve()
    assert (paths["target"] / "app.py").read_text(encoding="utf-8") == "old code\n"
    assert paths["protected"].read_text(encoding="utf-8") == "operator live\n"
    assert paths["fingerprint"].read_text(encoding="utf-8") == "OLD_FINGERPRINT=1\n"
    assert paths["retired"].read_text(encoding="utf-8") == "old retired module\n"
    assert paths["unit"].read_text(encoding="utf-8") == "old unit\n"
    assert "EnvironmentFile=" in paths["dropin"].read_text(encoding="utf-8")
    assert paths["nginx_vhost"].read_text(encoding="utf-8") == "old vhost\n"
    payload = json.loads(paths["journal"].read_text(encoding="utf-8"))
    assert payload["stage"] == "rolled_back"
    assert not list(paths["runtime_root"].glob(".rollback-*"))

    calls_before = (paths["fake_state"] / "calls").read_text(encoding="utf-8")
    second = _recover_staged_transaction(paths)
    assert second.returncode == 0, second.stderr
    calls_after = (paths["fake_state"] / "calls").read_text(encoding="utf-8")
    assert calls_after == calls_before


def test_rollback_failed_preserves_all_remaining_evidence_for_retry(
    tmp_path: Path,
) -> None:
    paths = _stage_recoverable_transaction(tmp_path, wait_for_sigkill=False)
    first = _recover_staged_transaction(paths, nginx_failures=1)
    assert first.returncode != 0
    payload = json.loads(paths["journal"].read_text(encoding="utf-8"))
    assert payload["stage"] == "rollback_failed"
    for key in (
        "code_backup",
        "code_excludes_backup",
        "systemd_unit_backup",
        "systemd_dropin_backup",
        "fingerprint_backup",
        "nginx_backup",
    ):
        assert payload[key], key
        assert Path(payload[key]).exists(), key
    assert list(paths["runtime_root"].glob(".rollback-*"))

    second = _recover_staged_transaction(paths)
    assert second.returncode == 0, second.stderr
    payload = json.loads(paths["journal"].read_text(encoding="utf-8"))
    assert payload["stage"] == "rolled_back"
    assert not list(paths["runtime_root"].glob(".rollback-*"))
    assert paths["current"].resolve() == paths["old_release"].resolve()
    assert paths["protected"].read_text(encoding="utf-8") == "operator live\n"


@pytest.mark.parametrize("stage", ["success", "rolled_back"])
def test_legacy_terminal_journal_is_accepted_without_unsafe_migration(
    tmp_path: Path, stage: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime_id = f"cpython-311-{'a' * 64}-{'b' * 64}"
    journal = runtime_root / "deploy-journal.json"
    legacy = {
        "schema_version": 1,
        "stage": stage,
        "pid": 123,
        "updated_at": "2026-07-14T00:00:00+00:00",
        "commit": "c" * 40,
        "runtime_id": runtime_id,
        "code_backup": str(runtime_root / ".rollback-code.legacy"),
        "previous_runtime": str(runtime_root / "releases" / runtime_id),
    }
    journal.write_text(json.dumps(legacy), encoding="utf-8")

    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; deploy_journal_check_start'
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(journal.read_text(encoding="utf-8")) == legacy


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"stage": "snapshot"}, "legacy nonterminal"),
        ({"unexpected": "field"}, "fields are unknown or incomplete"),
        ({"code_backup": "/tmp/outside"}, "code backup is unsafe"),
        ({"previous_runtime": "/tmp/outside"}, "previous runtime is unsafe"),
    ],
)
def test_legacy_journal_rejects_nonterminal_unknown_and_unsafe_paths(
    tmp_path: Path, mutation: dict[str, str], expected: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime_id = f"cpython-311-{'a' * 64}-{'b' * 64}"
    journal = runtime_root / "deploy-journal.json"
    legacy = {
        "schema_version": 1,
        "stage": "success",
        "pid": 123,
        "updated_at": "2026-07-14T00:00:00+00:00",
        "commit": "c" * 40,
        "runtime_id": runtime_id,
        "code_backup": "",
        "previous_runtime": "",
        **mutation,
    }
    journal.write_text(json.dumps(legacy), encoding="utf-8")

    result = _bash(
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        'if deploy_journal_check_start; then exit 107; fi'
    )

    assert result.returncode == 0, result.stderr
    assert expected in result.stderr


def test_runtime_orphan_recovery_removes_only_safe_incomplete_directories(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    previous = _make_runtime_release(releases, requirements_sha="8" * 64)
    orphan = releases / f"cpython-311-{'9' * 64}-{'a' * 64}"
    orphan.mkdir()
    (orphan / ".building").touch()
    staging_orphan = releases / ".staging.cpython-311.deadbeef.ABC123"
    staging_orphan.mkdir()
    (staging_orphan / ".building").touch()
    staging_orphan.chmod(0o500)
    resolver = runtime_root / ".resolver.abcd"
    resolver.mkdir()
    old_code_backup = runtime_root / ".rollback-code.abcd"
    old_code_backup.mkdir()
    old_unit_backup = runtime_root / ".rollback-unit.abcd"
    old_unit_backup.write_text("old\n", encoding="utf-8")
    extra_backup_names = (
        ".rollback-dropin.abcd",
        ".rollback-fingerprint.abcd",
        ".rollback-nginx.abcd",
        ".rollback-retired.abcd",
        ".rollback-excludes.abcd",
    )
    extra_backups = [runtime_root / name for name in extra_backup_names]
    for backup in extra_backups:
        backup.write_text("old\n", encoding="utf-8")
    old_source_snapshot = runtime_root / ".deploy-source.abcd"
    old_source_snapshot.mkdir()
    old_link_tmp = runtime_root / ".current.123.456"
    old_link_tmp.symlink_to(previous)
    outside = tmp_path / "outside"
    outside.mkdir()
    resolver_link = runtime_root / ".resolver.escape"
    resolver_link.symlink_to(outside)
    (runtime_root / "current").symlink_to(previous)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; runtime_capture_current; '
        "runtime_recover_orphan_builds"
    )

    assert result.returncode == 0, result.stderr
    assert previous.is_dir()
    assert not orphan.exists()
    assert not staging_orphan.exists()
    assert not resolver.exists()
    assert not old_code_backup.exists()
    assert not old_unit_backup.exists()
    assert all(not backup.exists() for backup in extra_backups)
    assert not old_source_snapshot.exists()
    assert not old_link_tmp.exists()
    assert resolver_link.is_symlink()
    assert outside.is_dir()


def test_runtime_gc_protects_current_previous_and_configured_recent_releases(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    created = [
        _make_runtime_release(releases, requirements_sha=f"{index:x}" * 64)
        for index in range(1, 7)
    ]
    for index, release in enumerate(created):
        os.utime(release, ns=(index + 1, index + 1))
    previous = created[0]
    current_release = created[-1]
    recent_extra = created[-2]
    current = runtime_root / "current"
    current.symlink_to(current_release)
    journal = runtime_root / "deploy-journal.json"
    journal.write_text('{"stage":"success"}\n', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    escape = releases / f"cpython-311-{'a' * 64}-{'b' * 64}"
    escape.symlink_to(outside)

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'RUNTIME_PREVIOUS_TARGET={shlex.quote(str(previous))}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; runtime_gc_releases',
        env={"STRUCTURAL_RUNTIME_KEEP_RELEASES": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert previous.is_dir()
    assert current_release.is_dir()
    assert recent_extra.is_dir()
    assert all(not release.exists() for release in created[1:-2])
    assert escape.is_symlink() and outside.is_dir()


def test_runtime_gc_refuses_active_journal_without_deleting_releases(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    release = _make_runtime_release(releases, requirements_sha="c" * 64)
    (runtime_root / "current").symlink_to(release)
    journal = runtime_root / "deploy-journal.json"
    journal.write_text('{"stage":"runtime_switched"}\n', encoding="utf-8")

    result = _bash(
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'DEPLOY_JOURNAL={shlex.quote(str(journal))}; '
        "if runtime_gc_releases; then exit 99; fi"
    )

    assert result.returncode == 0, result.stderr
    assert release.is_dir()


def test_disk_space_gate_fails_before_runtime_build(tmp_path: Path) -> None:
    result = _bash(
        f'if runtime_require_disk_space {shlex.quote(str(tmp_path))}; then exit 100; fi',
        env={"STRUCTURAL_RUNTIME_MIN_FREE_KB": str(10**18)},
    )
    assert result.returncode == 0, result.stderr


def test_resolver_report_canonicalizes_explicit_setuptools_into_identity(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "install": [
                    {"metadata": {"name": "Setuptools", "version": "83.0.0"}},
                    {"metadata": {"name": "Demo_Pkg", "version": "1.2.3+cpu"}},
                ]
            }
        ),
        encoding="utf-8",
    )
    canonical = tmp_path / "constraints.txt"
    expected = b"demo-pkg==1.2.3+cpu\nsetuptools==83.0.0\n"

    result = _bash(
        f"runtime_canonicalize_resolver_report {shlex.quote(sys.executable)} "
        f"{shlex.quote(str(report))} {shlex.quote(str(canonical))}"
    )

    assert result.returncode == 0, result.stderr
    assert canonical.read_bytes() == expected
    assert result.stdout.strip() == hashlib.sha256(expected).hexdigest()


def test_resolver_report_rejects_duplicate_canonical_package(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "install": [
                    {"metadata": {"name": "Setuptools", "version": "83.0.0"}},
                    {"metadata": {"name": "setuptools", "version": "83.0.0"}},
                ]
            }
        ),
        encoding="utf-8",
    )
    canonical = tmp_path / "constraints.txt"

    result = _bash(
        "if runtime_canonicalize_resolver_report "
        f"{shlex.quote(sys.executable)} {shlex.quote(str(report))} "
        f"{shlex.quote(str(canonical))}; then exit 93; fi"
    )

    assert result.returncode == 0, result.stderr
    assert "resolver returned a duplicate package" in result.stderr
    assert not canonical.exists()


def test_runtime_proofs_ignore_cwd_and_pythonpath_distribution_injection(
    tmp_path: Path,
) -> None:
    requirements_sha = "9" * 64
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha=requirements_sha
    )
    current = runtime_root / "current"
    current.symlink_to(release)

    ambient_cwd = tmp_path / "ambient-cwd"
    ambient_cwd.mkdir()
    cwd_metadata = ambient_cwd / "structural_isomorphism.egg-info"
    cwd_metadata.mkdir()
    (cwd_metadata / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: structural-isomorphism\nVersion: 9.9.9\n",
        encoding="utf-8",
    )
    (ambient_cwd / "json.py").write_text(
        "raise RuntimeError('cwd import injection executed')\n", encoding="utf-8"
    )

    pythonpath_poison = tmp_path / "pythonpath-poison"
    pythonpath_poison.mkdir()
    path_metadata = pythonpath_poison / "ambient_dependency-8.8.8.dist-info"
    path_metadata.mkdir()
    (path_metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: ambient-dependency\nVersion: 8.8.8\n",
        encoding="utf-8",
    )
    (pythonpath_poison / "pathlib.py").write_text(
        "raise RuntimeError('PYTHONPATH import injection executed')\n",
        encoding="utf-8",
    )

    generated = tmp_path / "generated-attestation.json"
    public = tmp_path / "public" / "runtime-attestation.json"
    freeze_sha = release.name.rsplit("-", 1)[1]
    result = _bash(
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_RELEASE={shlex.quote(str(release))}; "
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"RUNTIME_ID={shlex.quote(release.name)}; "
        f"RUNTIME_REQUIREMENTS_SHA256={requirements_sha}; "
        f"RUNTIME_FREEZE_SHA256={freeze_sha}; "
        f"runtime_attest_release {shlex.quote(str(release))} {shlex.quote(str(generated))}; "
        f"runtime_live_validate_release {shlex.quote(str(release))}; "
        f"runtime_publish_attestation {shlex.quote(str(public))} "
        f"{'a' * 40} 2026-07-15T00:00:00Z",
        env={"PYTHONPATH": str(pythonpath_poison)},
        cwd=ambient_cwd,
    )

    assert result.returncode == 0, result.stderr
    generated_payload = json.loads(generated.read_text(encoding="utf-8"))
    assert generated_payload["installed_package_count"] == len(
        _RUNTIME_PACKAGE_VERSIONS
    )
    assert generated_payload["installed_freeze_sha256"] == freeze_sha
    payload = json.loads(public.read_text(encoding="utf-8"))
    assert payload["installed_package_count"] == len(_RUNTIME_PACKAGE_VERSIONS)
    assert payload["installed_freeze_sha256"] == freeze_sha
    assert "ambient-dependency" not in public.read_text(encoding="utf-8")
    assert "structural-isomorphism" not in public.read_text(encoding="utf-8")


def test_explicit_setuptools_is_bound_across_attestation_and_live_validation(
    tmp_path: Path,
) -> None:
    requirements_sha = "7" * 64
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases",
        requirements_sha=requirements_sha,
        resolved_package_versions={"setuptools": "83.0.0"},
    )
    _make_runtime_release_writable(release)
    _install_owned_setuptools_hook(release)
    release = _rebind_runtime_release_identity(release)
    generated = tmp_path / "generated-attestation.json"
    freeze_sha = release.name.rsplit("-", 1)[1]

    result = _bash(
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_RELEASE={shlex.quote(str(release))}; "
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"RUNTIME_ID={shlex.quote(release.name)}; "
        f"RUNTIME_REQUIREMENTS_SHA256={requirements_sha}; "
        f"RUNTIME_FREEZE_SHA256={freeze_sha}; "
        f"runtime_attest_release {shlex.quote(str(release))} "
        f"{shlex.quote(str(generated))}; "
        f"runtime_live_validate_release {shlex.quote(str(release))}",
        env={"STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(generated.read_text(encoding="utf-8"))
    assert payload["installed_package_count"] == len(_RUNTIME_PACKAGE_VERSIONS) + 1
    assert payload["installed_freeze_sha256"] == freeze_sha
    assert "setuptools==83.0.0\n" in (release / "resolved-packages.txt").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("tamper", "expected_error"),
    [
        ("missing", "installed package-set is missing: setuptools"),
        ("unexpected", "installed package-set has unexpected packages: wheel"),
        ("version_drift", "installed package-set has version drift: setuptools"),
        ("manifest_tamper", "canonical package-set manifest bytes are not canonical"),
        ("pth_escape", "site path entries are forbidden"),
        ("sitecustomize", "site customization hooks are forbidden"),
        ("package_symlink", "site-packages entry escapes its environment"),
        ("dist_info_symlink", "site-packages entry escapes its environment"),
        ("record_escape", "accepted distribution RECORD path escapes its environment"),
        ("interpreter_escape", "runtime interpreter does not resolve to the trusted base"),
        ("unowned_safe_pth", "runtime file lacks exactly one RECORD owner"),
        ("nested_unowned_symlink", "runtime file lacks exactly one RECORD owner"),
        ("unowned_code", "runtime file lacks exactly one RECORD owner"),
        ("missing_record", "RECORD is unavailable or is a symlink"),
        ("missing_record_path", "RECORD path is missing"),
        ("hash_tamper", "RECORD sha256 mismatch"),
        ("size_tamper", "RECORD size mismatch"),
        ("safe_hook_marker", "RECORD size mismatch"),
        (
            "safe_hook_record_rewrite",
            "runtime content",
        ),
        ("internal_wrapper", "runtime interpreter does not resolve to the trusted base"),
        ("pyc_injection", "runtime bytecode cache files are forbidden"),
        ("pyvenv_system_site", "runtime pyvenv enables system site-packages"),
        (
            "pyvenv_home",
            "runtime pyvenv home does not resolve to trusted base",
        ),
        (
            "pyvenv_executable",
            "runtime pyvenv executable does not resolve to trusted base",
        ),
        (
            "pyvenv_version",
            "runtime pyvenv Python version does not match trusted base",
        ),
        (
            "pyvenv_missing",
            "runtime pyvenv configuration is missing or is a symlink",
        ),
        (
            "pyvenv_duplicate",
            "runtime pyvenv configuration has unknown or duplicate keys",
        ),
        (
            "pyvenv_unknown",
            "runtime pyvenv configuration has unknown or duplicate keys",
        ),
        (
            "pyvenv_symlink",
            "runtime pyvenv configuration is missing or is a symlink",
        ),
    ],
)
def test_attestation_and_live_reject_package_set_or_provenance_drift(
    tmp_path: Path, tamper: str, expected_error: str
) -> None:
    requirements_sha = "6" * 64
    runtime_root = tmp_path / "runtime"
    provenance_tamper = tamper in {
        "pth_escape",
        "sitecustomize",
        "package_symlink",
        "dist_info_symlink",
        "record_escape",
        "interpreter_escape",
        "unowned_safe_pth",
        "nested_unowned_symlink",
        "unowned_code",
        "missing_record",
        "missing_record_path",
        "hash_tamper",
        "size_tamper",
        "safe_hook_marker",
        "safe_hook_record_rewrite",
        "internal_wrapper",
        "pyc_injection",
        "pyvenv_system_site",
        "pyvenv_home",
        "pyvenv_executable",
        "pyvenv_version",
        "pyvenv_missing",
        "pyvenv_duplicate",
        "pyvenv_unknown",
        "pyvenv_symlink",
    }
    if tamper in {"safe_hook_marker", "safe_hook_record_rewrite"}:
        resolved_versions = {"setuptools": "83.0.0"}
    elif provenance_tamper:
        resolved_versions = {"plugin-pkg": "1.0.0"}
    else:
        resolved_versions = (
            {"setuptools": "83.0.0"} if tamper != "unexpected" else None
        )
    release = _make_runtime_release(
        runtime_root / "releases",
        requirements_sha=requirements_sha,
        resolved_package_versions=resolved_versions,
    )
    _make_runtime_release_writable(release)
    site_packages = _runtime_site_packages(release)
    external = tmp_path / "external"
    external.mkdir()
    marker = tmp_path / "executed.marker"
    (external / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    if tamper == "missing":
        _replace_runtime_distribution(release, "setuptools", None)
    elif tamper == "unexpected":
        _replace_runtime_distribution(release, "wheel", "0.45.1")
    elif tamper == "version_drift":
        _replace_runtime_distribution(release, "setuptools", "84.0.0")
    elif tamper == "manifest_tamper":
        manifest = release / "resolved-packages.txt"
        lines = manifest.read_text(encoding="utf-8").splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper == "pth_escape":
        shutil.move(str(site_packages / "plugin_pkg"), external / "plugin_pkg")
        shutil.move(
            str(site_packages / "plugin_pkg-1.0.0.dist-info"),
            external / "plugin_pkg-1.0.0.dist-info",
        )
        (site_packages / "escape.pth").write_text(str(external) + "\n", encoding="utf-8")
    elif tamper == "sitecustomize":
        (site_packages / "sitecustomize.py").write_text(
            "raise RuntimeError('must never execute')\n", encoding="utf-8"
        )
    elif tamper == "package_symlink":
        package = site_packages / "plugin_pkg"
        shutil.move(str(package), external / package.name)
        package.symlink_to(external / package.name, target_is_directory=True)
    elif tamper == "dist_info_symlink":
        metadata_dir = site_packages / "plugin_pkg-1.0.0.dist-info"
        shutil.move(str(metadata_dir), external / metadata_dir.name)
        metadata_dir.symlink_to(external / metadata_dir.name, target_is_directory=True)
    elif tamper == "record_escape":
        escaped = external / "payload.py"
        escaped.write_text("raise RuntimeError('outside release')\n", encoding="utf-8")
        record = site_packages / "plugin_pkg-1.0.0.dist-info" / "RECORD"
        with record.open("a", encoding="utf-8") as stream:
            stream.write(f"{os.path.relpath(escaped, site_packages)},,\n")
    elif tamper == "interpreter_escape":
        escaped_python = external / "python"
        escaped_python.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        escaped_python.chmod(0o755)
        python = release / "bin" / "python"
        python.unlink()
        python.symlink_to(escaped_python)
    elif tamper == "nested_unowned_symlink":
        (site_packages / "plugin_pkg" / "shadow.py").symlink_to("__init__.py")
    elif tamper == "unowned_code":
        (site_packages / "plugin_pkg" / "shadow.py").write_text(
            "raise RuntimeError('unowned')\n", encoding="utf-8"
        )
    elif tamper == "missing_record":
        (site_packages / "plugin_pkg-1.0.0.dist-info" / "RECORD").unlink()
    elif tamper == "missing_record_path":
        (site_packages / "plugin_pkg" / "__init__.py").unlink()
    elif tamper == "hash_tamper":
        (site_packages / "plugin_pkg" / "__init__.py").write_text(
            "__version__ = '9.9.9'\n", encoding="utf-8"
        )
    elif tamper == "size_tamper":
        record = site_packages / "plugin_pkg-1.0.0.dist-info" / "RECORD"
        lines = record.read_text(encoding="utf-8").splitlines()
        fields = lines[0].split(",")
        fields[2] = str(int(fields[2]) + 1)
        lines[0] = ",".join(fields)
        record.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper == "safe_hook_marker":
        _site_packages, hack_init = _install_owned_setuptools_hook(release)
        hack_init.write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
            "def add_shim(): pass\n",
            encoding="utf-8",
        )
    elif tamper == "safe_hook_record_rewrite":
        _site_packages, hack_init = _install_owned_setuptools_hook(release)
        malicious = (
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
            "def add_shim(): pass\n"
        ).encode("utf-8")
        hack_init.write_bytes(malicious)
        _replace_record_line(
            site_packages / "setuptools-83.0.0.dist-info" / "RECORD",
            "_distutils_hack/__init__.py",
            malicious,
        )
    elif tamper == "internal_wrapper":
        python = release / "bin" / "python"
        python.unlink()
        python.write_text(
            "#!/bin/sh\n"
            f"printf ran > {shlex.quote(str(marker))}\n"
            f"exec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        python.chmod(0o755)
    elif tamper == "pyc_injection":
        cache = site_packages / "plugin_pkg" / "__pycache__"
        cache.mkdir()
        (cache / f"shadow.{sys.implementation.cache_tag}.pyc").write_bytes(b"malicious")
    elif tamper == "pyvenv_system_site":
        configuration = release / "pyvenv.cfg"
        configuration.write_text(
            configuration.read_text(encoding="utf-8").replace(
                "include-system-site-packages = false\n",
                "include-system-site-packages = true\n",
            ),
            encoding="utf-8",
        )
    elif tamper == "pyvenv_home":
        configuration = release / "pyvenv.cfg"
        lines = configuration.read_text(encoding="utf-8").splitlines()
        lines[0] = f"home = {external}"
        configuration.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper == "pyvenv_executable":
        escaped_python = external / "python"
        escaped_python.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        escaped_python.chmod(0o755)
        configuration = release / "pyvenv.cfg"
        lines = configuration.read_text(encoding="utf-8").splitlines()
        lines[3] = f"executable = {escaped_python}"
        configuration.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper == "pyvenv_version":
        configuration = release / "pyvenv.cfg"
        configuration.write_text(
            configuration.read_text(encoding="utf-8").replace(
                f"version = {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n",
                "version = 0.0.0\n",
            ),
            encoding="utf-8",
        )
    elif tamper == "pyvenv_missing":
        (release / "pyvenv.cfg").unlink()
    elif tamper == "pyvenv_duplicate":
        with (release / "pyvenv.cfg").open("a", encoding="utf-8") as stream:
            stream.write("include-system-site-packages = false\n")
    elif tamper == "pyvenv_unknown":
        with (release / "pyvenv.cfg").open("a", encoding="utf-8") as stream:
            stream.write("prompt = poisoned\n")
    elif tamper == "pyvenv_symlink":
        configuration = release / "pyvenv.cfg"
        moved = external / "pyvenv.cfg"
        configuration.rename(moved)
        configuration.symlink_to(moved)
    else:
        _replace_runtime_distribution(release, "setuptools", None)
        precedence = site_packages / "distutils-precedence.pth"
        if precedence.exists() or precedence.is_symlink():
            precedence.unlink()
        local_hack = site_packages / "_distutils_hack"
        if local_hack.exists():
            shutil.rmtree(local_hack)
        local_hack.mkdir()
        (local_hack / "__init__.py").write_text(
            "def add_shim(): pass\n", encoding="utf-8"
        )
        precedence.write_text(
            "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; "
            "enabled = os.environ.get(var, 'local') == 'local'; "
            "enabled and __import__('_distutils_hack').add_shim()\n",
            encoding="utf-8",
        )
    freeze_sha = release.name.rsplit("-", 1)[1]
    common = (
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_RELEASE={shlex.quote(str(release))}; "
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"RUNTIME_ID={shlex.quote(release.name)}; "
        f"RUNTIME_REQUIREMENTS_SHA256={requirements_sha}; "
        f"RUNTIME_FREEZE_SHA256={freeze_sha}; "
    )
    generated = tmp_path / "generated-attestation.json"

    attestation = _bash(
        common
        + f"if runtime_attest_release {shlex.quote(str(release))} "
        + f"{shlex.quote(str(generated))}; then exit 94; fi",
        env={
            "STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag,
            "PYTHONHOME": str(external),
            "PYTHONPATH": str(external),
        },
    )
    live = _bash(
        common
        + f"if runtime_live_validate_release {shlex.quote(str(release))}; "
        + "then exit 95; fi",
        env={
            "STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag,
            "PYTHONHOME": str(external),
            "PYTHONPATH": str(external),
        },
    )

    assert attestation.returncode == 0, attestation.stderr
    assert live.returncode == 0, live.stderr
    assert expected_error in attestation.stderr
    assert expected_error in live.stderr
    assert not generated.exists()
    assert not marker.exists()


def test_pyvenv_semantic_tamper_cannot_be_reattested_with_synchronized_identity(
    tmp_path: Path,
) -> None:
    requirements_sha = "d" * 64
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha=requirements_sha
    )
    _make_runtime_release_writable(release)
    configuration = release / "pyvenv.cfg"
    configuration.write_text(
        configuration.read_text(encoding="utf-8").replace(
            "include-system-site-packages = false\n",
            "include-system-site-packages = true\n",
        ),
        encoding="utf-8",
    )
    attestation = release / "attestation.json"
    payload = json.loads(attestation.read_text(encoding="utf-8"))
    forged_content = hashlib.sha256(configuration.read_bytes()).hexdigest()
    forged_freeze = _composite_freeze_sha256(
        payload["resolved_graph_sha256"], forged_content
    )
    forged_id = (
        f"{payload['python_abi']}-{payload['requirements_sha256']}-{forged_freeze}"
    )
    payload.update(
        {
            "runtime_id": forged_id,
            "runtime_content_sha256": forged_content,
            "installed_freeze_sha256": forged_freeze,
        }
    )
    attestation.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    forged_release = release.with_name(forged_id)
    release.rename(forged_release)

    external = tmp_path / "external"
    external.mkdir()
    marker = tmp_path / "executed.marker"
    (external / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    generated = tmp_path / "reattested.json"
    common = (
        f"RUNTIME_ROOT={shlex.quote(str(runtime_root))}; "
        f'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"RUNTIME_ID={forged_id}; "
        f"RUNTIME_REQUIREMENTS_SHA256={requirements_sha}; "
        f"RUNTIME_RESOLVED_GRAPH_SHA256={payload['resolved_graph_sha256']}; "
        f"RUNTIME_CONTENT_SHA256={forged_content}; "
        f"RUNTIME_FREEZE_SHA256={forged_freeze}; "
    )
    hostile_environment = {
        "STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag,
        "PYTHONHOME": str(external),
        "PYTHONPATH": str(external),
    }
    reattest = _bash(
        common
        + f"if runtime_attest_release {shlex.quote(str(forged_release))} "
        + f"{shlex.quote(str(generated))}; then exit 96; fi",
        env=hostile_environment,
    )
    live = _bash(
        common
        + f"if runtime_live_validate_release {shlex.quote(str(forged_release))}; "
        + "then exit 97; fi",
        env=hostile_environment,
    )

    assert reattest.returncode == 0, reattest.stderr
    assert live.returncode == 0, live.stderr
    assert "runtime pyvenv enables system site-packages" in reattest.stderr
    assert "runtime pyvenv enables system site-packages" in live.stderr
    assert not generated.exists()
    assert not marker.exists()


def test_runtime_content_identity_binds_python_link_text_and_resolved_target(
    tmp_path: Path,
) -> None:
    requirements_sha = "e" * 64
    release = _make_runtime_release(
        tmp_path / "runtime" / "releases", requirements_sha=requirements_sha
    )
    payload = json.loads((release / "attestation.json").read_text(encoding="utf-8"))
    _make_runtime_release_writable(release)
    python = release / "bin" / "python"
    old_link = os.readlink(python)
    trusted_python = Path(sys.executable).resolve(strict=True)
    alternate_link = str(trusted_python)
    if alternate_link == old_link:
        alternate_link = os.path.relpath(trusted_python, python.parent)
    python.unlink()
    python.symlink_to(alternate_link)
    assert python.resolve(strict=True) == trusted_python

    proof = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        "runtime_validate_canonical_package_set "
        f"{shlex.quote(str(release))} "
        f"{shlex.quote(str(release / 'resolved-packages.txt'))} "
        f"{payload['resolved_graph_sha256']}"
    )
    assert proof.returncode == 0, proof.stderr
    _count, changed_content = proof.stdout.strip().split("\t")
    assert changed_content != payload["runtime_content_sha256"]

    validation = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"if runtime_validate_release {shlex.quote(str(release))}; then exit 98; fi",
        env={"STRUCTURAL_EXPECTED_PYTHON_ABI": sys.implementation.cache_tag},
    )
    assert validation.returncode == 0, validation.stderr
    assert "runtime content digest differs from attestation" in validation.stderr


def _make_long_pip_environment(tmp_path: Path) -> Path:
    runtime_id = f"{sys.implementation.cache_tag}-{'a' * 64}-{'b' * 64}"
    environment = tmp_path / "releases" / runtime_id
    environment.parent.mkdir()
    created = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"runtime_create_venv_without_pip {shlex.quote(str(environment))}; "
        f"runtime_bootstrap_pip {shlex.quote(str(environment))}"
    )
    assert created.returncode == 0, created.stderr
    return environment


def test_runtime_pip_ignores_long_path_console_launcher(tmp_path: Path) -> None:
    environment = _make_long_pip_environment(tmp_path)
    expected_shebang_bytes = len(
        f"#!{environment}/bin/python{sys.version_info.major}\n".encode()
    )
    assert expected_shebang_bytes > 127
    launchers = list((environment / "bin").glob("pip*"))
    assert launchers
    assert all(
        launcher.read_text(encoding="utf-8").splitlines()[0] == "#!/bin/sh"
        for launcher in launchers
    )

    for launcher in launchers:
        launcher.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        launcher.chmod(0o755)

    result = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"runtime_validate_pip_module {shlex.quote(str(environment))}; "
        f"runtime_pip {shlex.quote(str(environment))} --version"
    )

    assert result.returncode == 0, result.stderr
    assert str(environment) in result.stdout


def test_runtime_pip_rejects_package_symlink_outside_environment(
    tmp_path: Path,
) -> None:
    environment = _make_long_pip_environment(tmp_path)
    observed = subprocess.run(
        [
            str(environment / "bin" / "python"),
            "-I",
            "-c",
            "import pip; print(pip.__file__)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    pip_package = Path(observed.stdout.strip()).parent
    external_package = tmp_path / "external-pip"
    shutil.copytree(pip_package, external_package)
    shutil.rmtree(pip_package)
    pip_package.symlink_to(external_package, target_is_directory=True)

    result = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"if runtime_validate_pip_module {shlex.quote(str(environment))}; "
        "then exit 97; fi"
    )

    assert result.returncode == 0
    assert "site-packages entry escapes its environment" in result.stderr


def test_venv_bootstrap_preflights_before_first_target_execution(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "runtime"
    created = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"runtime_create_venv_without_pip {shlex.quote(str(environment))}"
    )
    assert created.returncode == 0, created.stderr
    site_packages = (
        environment
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    assert site_packages.is_dir()
    assert not (site_packages / "pip").exists()

    marker = tmp_path / "executed.marker"
    (site_packages / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    rejected = _bash(
        f"RUNTIME_PYTHON={shlex.quote(sys.executable)}; "
        f"if runtime_bootstrap_pip {shlex.quote(str(environment))}; then exit 98; fi"
    )
    assert rejected.returncode == 0, rejected.stderr
    assert "site customization hooks are forbidden" in rejected.stderr
    assert not marker.exists()
    assert not (site_packages / "pip").exists()

    helper = HELPER.read_text(encoding="utf-8")
    create = helper[helper.index("runtime_create_venv_without_pip()") :]
    create = create[: create.index("\n}")]
    assert create.index("--without-pip") < create.index(
        'runtime_trusted_structural_preflight "$environment"'
    )
    bootstrap = helper[helper.index("runtime_bootstrap_pip()") :]
    bootstrap = bootstrap[: bootstrap.index("\n}")]
    assert bootstrap.index('runtime_trusted_structural_preflight "$environment"') < bootstrap.index(
        "-m ensurepip --upgrade"
    )


@pytest.mark.parametrize("invalid_sha", ["a" * 12, "A" * 40, "g" * 40])
def test_public_attestation_is_atomic_and_rejects_noncanonical_sha_without_clobber(
    tmp_path: Path, invalid_sha: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    release = _make_runtime_release(
        runtime_root / "releases", requirements_sha="f" * 64
    )
    current = runtime_root / "current"
    current.symlink_to(release)
    public = tmp_path / "public" / "runtime-attestation.json"
    public.parent.mkdir()
    victim = tmp_path / "operator-owned.txt"
    victim.write_text("operator bytes\n", encoding="utf-8")
    public.symlink_to(victim)
    stale_regular = public.with_name(f"{public.name}.tmp.111")
    stale_regular.write_text("stale\n", encoding="utf-8")
    stale_symlink = public.with_name(f"{public.name}.tmp.link")
    stale_symlink.symlink_to(victim)

    common = (
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        f'RUNTIME_RELEASE={shlex.quote(str(release))}; '
        f'RUNTIME_CURRENT={shlex.quote(str(current))}; '
    )
    published = _bash(
        common
        + f'runtime_publish_attestation {shlex.quote(str(public))} '
        + f'{"b" * 40} 2026-07-14T00:00:00Z'
    )
    assert published.returncode == 0, published.stderr
    payload = json.loads(public.read_text(encoding="utf-8"))
    assert payload["git_sha"] == "b" * 40
    assert payload["runtime_id"] == release.name
    assert not public.is_symlink()
    assert victim.read_text(encoding="utf-8") == "operator bytes\n"
    assert not stale_regular.exists()
    assert stale_symlink.is_symlink()
    published_bytes = public.read_bytes()

    rejected = _bash(
        common
        + f'if runtime_publish_attestation {shlex.quote(str(public))} '
        + f'{shlex.quote(invalid_sha)} 2026-07-14T00:01:00Z; then exit 99; fi'
    )
    assert rejected.returncode == 0, rejected.stderr
    assert public.read_bytes() == published_bytes


def _signal_transaction(
    tmp_path: Path,
    *,
    stage: str,
    signal_name: str,
    wait_for_external_signal: bool = False,
) -> tuple[subprocess.CompletedProcess[str] | subprocess.Popen[str], dict[str, Path]]:
    runtime_root = tmp_path / "runtime"
    releases = runtime_root / "releases"
    old_release = _make_runtime_release(releases, requirements_sha="d" * 64)
    new_release = _make_runtime_release(releases, requirements_sha="e" * 64)
    (runtime_root / "current").symlink_to(old_release)
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("old code\n", encoding="utf-8")
    unit = tmp_path / "structural-web.service"
    unit.write_text("old unit\n", encoding="utf-8")
    rollback_log = tmp_path / "rollback.log"
    cleanup_log = tmp_path / "cleanup.log"
    ready = tmp_path / "ready"

    mutations = {
        "code": 'printf "new code\\n" > "$TARGET/app.py";',
        "current": (
            'printf "new code\\n" > "$TARGET/app.py"; '
            f'RUNTIME_RELEASE={shlex.quote(str(new_release))}; runtime_switch;'
        ),
        "unit": (
            'printf "new code\\n" > "$TARGET/app.py"; '
            f'RUNTIME_RELEASE={shlex.quote(str(new_release))}; runtime_switch; '
            'printf "new unit\\n" > "$SYSTEMD_UNIT_TARGET"; SYSTEMD_UNIT_INSTALLED=1;'
        ),
    }
    wait = (
        f'printf ready > {shlex.quote(str(ready))}; while :; do sleep 1; done'
        if wait_for_external_signal
        else f'kill -s {signal_name} "$$"'
    )
    body = (
        f'source {shlex.quote(str(HELPER))}; '
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'TARGET={shlex.quote(str(target))}; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(unit))}; '
        'EXCLUDES=(--exclude=.env); runtime_capture_current; deploy_code_snapshot; systemd_unit_capture; '
        'DEPLOY_TRANSACTION_ACTIVE=1; '
        f'rollback_callback() {{ printf "rollback\\n" >> {shlex.quote(str(rollback_log))}; '
        'deployment_restore_transaction_state; }; '
        f'cleanup_callback() {{ printf "cleanup\\n" >> {shlex.quote(str(cleanup_log))}; '
        'deployment_transaction_cleanup; }; '
        'deploy_guard_install rollback_callback cleanup_callback; '
        f'{mutations[stage]} {wait}'
    )
    command = ["bash", "-c", f"set -euo pipefail; {body}"]
    paths = {
        "runtime_root": runtime_root,
        "old_release": old_release,
        "target": target,
        "unit": unit,
        "rollback_log": rollback_log,
        "cleanup_log": cleanup_log,
        "ready": ready,
    }
    if wait_for_external_signal:
        return subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE), paths
    return subprocess.run(command, text=True, capture_output=True, check=False), paths


@pytest.mark.parametrize("stage", ["code", "current", "unit"])
@pytest.mark.parametrize("signal_name", ["TERM", "HUP", "INT"])
def test_direct_signals_rollback_and_cleanup_exactly_once(
    tmp_path: Path, stage: str, signal_name: str,
) -> None:
    result, paths = _signal_transaction(
        tmp_path, stage=stage, signal_name=signal_name
    )
    assert isinstance(result, subprocess.CompletedProcess)
    expected_signal = getattr(signal, f"SIG{signal_name}")
    assert result.returncode == -expected_signal, result.stderr
    assert paths["rollback_log"].read_text(encoding="utf-8") == "rollback\n"
    assert paths["cleanup_log"].read_text(encoding="utf-8") == "cleanup\n"
    assert (paths["target"] / "app.py").read_text(encoding="utf-8") == "old code\n"
    assert paths["unit"].read_text(encoding="utf-8") == "old unit\n"
    assert (paths["runtime_root"] / "current").resolve() == paths["old_release"].resolve()


def test_external_ci_timeout_term_uses_the_same_single_finalizer(tmp_path: Path) -> None:
    process, paths = _signal_transaction(
        tmp_path,
        stage="unit",
        signal_name="TERM",
        wait_for_external_signal=True,
    )
    assert isinstance(process, subprocess.Popen)
    deadline = time.monotonic() + 5
    while not paths["ready"].exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert paths["ready"].exists(), "fault-injection harness did not reach the unit stage"
    process.send_signal(signal.SIGTERM)
    _stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == -signal.SIGTERM, stderr
    assert paths["rollback_log"].read_text(encoding="utf-8") == "rollback\n"
    assert paths["cleanup_log"].read_text(encoding="utf-8") == "cleanup\n"
    assert (paths["target"] / "app.py").read_text(encoding="utf-8") == "old code\n"
    assert paths["unit"].read_text(encoding="utf-8") == "old unit\n"
    assert (paths["runtime_root"] / "current").resolve() == paths["old_release"].resolve()


def _beta_candidate_gate_fixture(
    tmp_path: Path, *, failure: str = ""
) -> tuple[dict[str, str], Path]:
    snapshot = tmp_path / "snapshot"
    backend = snapshot / "web" / "backend"
    backend.mkdir(parents=True)
    (backend / ".env.example").write_text(
        "ASK_LLM_MODEL=openai/gpt-5.6-luna-pro\n", encoding="utf-8"
    )
    fake_bin = tmp_path / "candidate-fake-bin"
    fake_bin.mkdir()
    fake_state = tmp_path / "candidate-fake-state"
    fake_state.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        f"#!{sys.executable}\n"
        + r'''import hashlib
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
state = Path(os.environ["FAKE_CURL_STATE"])
failure = os.environ.get("FAKE_CURL_FAILURE", "")
if not args or args[0] != "-q":
    raise SystemExit(90)
if args.count("--noproxy") != 1:
    raise SystemExit(91)
no_proxy_index = args.index("--noproxy")
if args[no_proxy_index + 1] != "*":
    raise SystemExit(92)
if args.count("--resolve") != 1:
    raise SystemExit(93)
resolve_index = args.index("--resolve")
if args[resolve_index + 1] != "beta.structural.bytedance.city:443:127.0.0.1":
    raise SystemExit(94)
url = next((arg for arg in reversed(args) if arg.startswith("https://")), "")
if not url.startswith("https://beta.structural.bytedance.city/"):
    raise SystemExit(95)
data = ""
if "--data-binary" in args:
    data = args[args.index("--data-binary") + 1]
with (state / "calls.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"url": url, "data": data}, ensure_ascii=False) + "\n")

sha = os.environ["FAKE_EXPECTED_SHA"]
requirements_sha = os.environ["FAKE_REQUIREMENTS_SHA"]
graph_sha = "b" * 64
content_sha = "c" * 64
freeze_sha = hashlib.sha256(
    (
        f"resolved_graph_sha256={graph_sha}\n"
        f"runtime_content_sha256={content_sha}\n"
    ).encode("ascii")
).hexdigest()
runtime_id = f"cpython-311-{requirements_sha}-{freeze_sha}"
deployed_at = os.environ["FAKE_DEPLOYED_AT"]
packages = {
    "fastapi": "0.115.14",
    "pydantic": "2.6.1",
    "starlette": "0.46.2",
    "uvicorn": "0.27.1",
}
attestation = {
    "schema_version": 2,
    "python_abi": "cpython-311",
    "python_version": "3.11.14",
    "runtime_id": runtime_id,
    "requirements_sha256": requirements_sha,
    "resolved_graph_sha256": graph_sha,
    "runtime_content_sha256": content_sha,
    "installed_freeze_sha256": freeze_sha,
    "git_sha": sha,
    "deployed_at": deployed_at,
    **packages,
}
version = {
    "semver": "0.2.0",
    "git_sha": sha,
    "python_version": "3.11.14",
    "python_abi": "cpython-311",
    "runtime_id": runtime_id,
    "requirements_sha256": requirements_sha,
    "installed_freeze_sha256": freeze_sha,
    "env": "prod",
    "model": "openai/gpt-5.6-luna-pro",
    "deployed_at": deployed_at,
    **packages,
}

if failure == "malformed" and "/api/version" in url:
    print("{")
elif "/assets/runtime-attestation.json" in url:
    if failure == "schema1":
        attestation["schema_version"] = 1
    elif failure == "graph":
        attestation["resolved_graph_sha256"] = "g" * 64
    elif failure == "content":
        attestation["runtime_content_sha256"] = None
    elif failure == "composite":
        attestation["installed_freeze_sha256"] = "d" * 64
    elif failure == "runtime_id":
        attestation["runtime_id"] = "cpython-311-" + "0" * 129
    elif failure == "sha":
        attestation["git_sha"] = "e" * 40
    elif failure == "deployed_at":
        attestation["deployed_at"] = "2026-07-15T00:00:00Z"
    print(json.dumps(attestation))
elif "/api/version" in url:
    if failure == "sha":
        version["git_sha"] = "e" * 40
    elif failure == "model":
        version["model"] = "wrong-model"
    elif failure == "package":
        version["fastapi"] = "9.9.9"
    elif failure == "semver":
        version["semver"] = "9.9.9"
    elif failure == "deployed_at":
        version["deployed_at"] = "2026-07-15T00:00:00Z"
    print(json.dumps(version))
elif "/api/health?deep=1" in url:
    health = {
        "status": "ok",
        "kb_size": 4443,
        "artifact_id": "structural-v2-kb4443-20260711",
        "embedding_shape": [4443, 768],
        "checks": {
            "search_service": "ok",
            "knowledge_base": "ok",
            "artifact_manifest": "ok",
            "history_db": "ok",
            "llm_env": "missing",
        },
    }
    if failure == "health":
        health["checks"]["search_service"] = "failed"
    print(json.dumps(health))
elif "/api/auth/me" in url:
    print(json.dumps({"error": "no session"}))
    print("200" if failure == "auth" else "401")
elif url.endswith("/"):
    print("HTTP/2 200")
    print("Referrer-Policy: no-referrer")
    print("X-Request-ID: candidate-request-1234")
    if failure == "headers":
        print("X-Request-ID: duplicate-request-5678")
elif "/api/search" in url:
    request = json.loads(data)
    counter_path = state / "search-count"
    count = int(counter_path.read_text() if counter_path.exists() else "0") + 1
    counter_path.write_text(str(count))
    expected_queries = (
        "月活用户每月固定流失百分之七，应该如何干预？",
        "为什么有些谣言会突然爆发并形成级联传播？",
        "团队氛围崩溃后为什么很难恢复？",
        "银行挤兑为什么会出现自我强化？",
        "一个平台如何避免正反馈导致系统失控？",
    )
    if (
        count > len(expected_queries)
        or request.get("query") != expected_queries[count - 1]
        or request.get("rewrite") is not False
        or request.get("top_k") != 5
        or request.get("lang") != "zh"
    ):
        raise SystemExit(96)
    body = {
        "out_of_scope": False,
        "count": 1,
        "results": [{
            "id": "test",
            "name": "Test",
            "domain": "systems",
            "type_id": "feedback",
            "cross_domain": failure != "no_cross" and count == 1,
        }],
    }
    if failure == f"search{count}":
        body.update(out_of_scope=True, count=0, results=[])
    print(json.dumps(body))
else:
    raise SystemExit(97)
''',
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    source_sha = "a" * 40
    requirements_sha = "f" * 64
    graph_sha = "b" * 64
    content_sha = "c" * 64
    freeze_sha = _composite_freeze_sha256(graph_sha, content_sha)
    deployed_at = "2026-07-16T00:00:00Z"
    env = {
        "SOURCE": str(ROOT),
        "TARGET": str(tmp_path / "target"),
        "STRUCTURAL_RUNTIME_PYTHON": sys.executable,
        "TEST_DEPLOY_SYNC_SOURCE": str(snapshot),
        "TEST_SOURCE_HEAD_SHA": source_sha,
        "TEST_RUNTIME_REQUIREMENTS_SHA256": requirements_sha,
        "TEST_RUNTIME_FREEZE_SHA256": freeze_sha,
        "TEST_RUNTIME_ID": f"cpython-311-{requirements_sha}-{freeze_sha}",
        "TEST_DEPLOYED_AT": deployed_at,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_CURL_STATE": str(fake_state),
        "FAKE_CURL_FAILURE": failure,
        "FAKE_EXPECTED_SHA": source_sha,
        "FAKE_REQUIREMENTS_SHA": requirements_sha,
        "FAKE_DEPLOYED_AT": deployed_at,
    }
    return env, fake_state / "calls.jsonl"


def _run_beta_candidate_gate(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _source_deploy(
        'DEPLOY_SYNC_SOURCE="$TEST_DEPLOY_SYNC_SOURCE"; '
        'SOURCE_HEAD_SHA="$TEST_SOURCE_HEAD_SHA"; '
        'RUNTIME_REQUIREMENTS_SHA256="$TEST_RUNTIME_REQUIREMENTS_SHA256"; '
        'RUNTIME_FREEZE_SHA256="$TEST_RUNTIME_FREEZE_SHA256"; '
        'RUNTIME_ID="$TEST_RUNTIME_ID"; DEPLOYED_AT="$TEST_DEPLOYED_AT"; '
        "beta_candidate_tls_gate",
        env=env,
    )


def test_beta_candidate_tls_gate_accepts_canonical_local_candidate(
    tmp_path: Path,
) -> None:
    env, calls_path = _beta_candidate_gate_fixture(tmp_path)

    result = _run_beta_candidate_gate(env)

    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    assert len(calls) == 10
    searches = [call for call in calls if call["url"].endswith("/api/search")]
    assert len(searches) == 5
    assert all(json.loads(call["data"])["rewrite"] is False for call in searches)


def test_beta_candidate_tls_gate_rejects_schema1_runtime(tmp_path: Path) -> None:
    env, _calls_path = _beta_candidate_gate_fixture(tmp_path, failure="schema1")

    result = _run_beta_candidate_gate(env)

    assert result.returncode != 0
    assert "candidate runtime/version identity is invalid" in result.stderr


@pytest.mark.parametrize(
    "failure",
    [
        "graph",
        "content",
        "composite",
        "runtime_id",
        "sha",
        "model",
        "package",
        "semver",
        "deployed_at",
        "health",
        "auth",
        "headers",
        "malformed",
        "search1",
        "search2",
        "search3",
        "search4",
        "search5",
        "no_cross",
    ],
)
def test_beta_candidate_tls_gate_rejects_invalid_candidate_contracts(
    tmp_path: Path, failure: str,
) -> None:
    env, _calls_path = _beta_candidate_gate_fixture(tmp_path, failure=failure)

    result = _run_beta_candidate_gate(env)

    assert result.returncode != 0, failure


def test_beta_candidate_gate_precedes_transaction_commit_and_cleanup() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    nginx_installed = deploy.index("deploy_journal_write nginx_installed")
    gate = deploy.index("  beta_candidate_tls_gate", nginx_installed)
    ready = deploy.index("deploy_journal_write ready", gate)
    success = deploy.index("deploy_journal_write success", ready)
    garbage_collection = deploy.index("runtime_gc_releases", success)
    deactivate = deploy.index("DEPLOY_TRANSACTION_ACTIVE=0", garbage_collection)
    cleanup = deploy.index("deploy_cleanup_once", deactivate)

    assert nginx_installed < gate < ready < success < garbage_collection < deactivate < cleanup
    gate_function = deploy[
        deploy.index("beta_candidate_tls_gate()") : deploy.index(
            "\n}\n\n# The validation boundary", deploy.index("beta_candidate_tls_gate()")
        )
    ]
    assert "--resolve \"$resolve\"" in gate_function
    assert "beta.structural.bytedance.city:443:127.0.0.1" in gate_function
    assert "--noproxy '*'" in gate_function
    assert '"$RUNTIME_PYTHON" -I -S -B -' in gate_function
    assert '"$RUNTIME_CURRENT/bin/python"' not in gate_function


def test_beta_workflow_keeps_public_checks_post_commit_without_remote_rollback() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["deploy"]["steps"]
    deploy_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name", "").startswith("Pull + deploy via deploy-dispatcher")
    )
    verification_steps = steps[deploy_index + 1 :]

    assert verification_steps
    assert all(
        "post-commit public verification" in step.get("name", "")
        for step in verification_steps
    )
    sha_steps = [
        step
        for step in verification_steps
        if "EXPECTED_SHA" in step.get("env", {})
    ]
    assert len(sha_steps) == 2
    assert all(
        step["env"]["EXPECTED_SHA"] == "${{ github.sha }}" for step in sha_steps
    )
    assert "EXPECTED_SHA=$(git rev-parse HEAD)" not in workflow_text
    for step in steps:
        run = step.get("run", "").lower()
        if "ssh " in run:
            assert "rollback" not in run


def test_first_runtime_migration_candidate_gate_failure_restores_legacy_state(
    tmp_path: Path,
) -> None:
    env, _calls_path = _beta_candidate_gate_fixture(tmp_path, failure="schema1")
    runtime_root = tmp_path / "runtime"
    new_release = _make_runtime_release(
        runtime_root / "releases", requirements_sha="8" * 64
    )
    target = tmp_path / "target"
    legacy_python = target / "venv" / "bin" / "python"
    legacy_python.parent.mkdir(parents=True)
    legacy_python.write_text("legacy runtime\n", encoding="utf-8")
    (target / "app.py").write_text("legacy code\n", encoding="utf-8")
    systemd_unit = tmp_path / "legacy-structural.service"
    systemd_unit.write_text(f"ExecStart={legacy_python}\n", encoding="utf-8")

    body = (
        f'RUNTIME_ROOT={shlex.quote(str(runtime_root))}; '
        'RUNTIME_RELEASES="$RUNTIME_ROOT/releases"; '
        'RUNTIME_CURRENT="$RUNTIME_ROOT/current"; '
        f'RUNTIME_PYTHON={shlex.quote(sys.executable)}; '
        f'TARGET={shlex.quote(str(target))}; '
        f'SYSTEMD_UNIT_TARGET={shlex.quote(str(systemd_unit))}; '
        'EXCLUDES=(--exclude=venv/); '
        'runtime_capture_current; test "$RUNTIME_PREVIOUS_PRESENT" = 0; '
        'deploy_code_snapshot; systemd_unit_capture; '
        f'RUNTIME_RELEASE={shlex.quote(str(new_release))}; runtime_switch; '
        'printf "candidate code\\n" > "$TARGET/app.py"; '
        'printf "candidate-only\\n" > "$TARGET/new.py"; '
        'printf "candidate unit\\n" > "$SYSTEMD_UNIT_TARGET"; '
        'SYSTEMD_UNIT_INSTALLED=1; DEPLOY_TRANSACTION_ACTIVE=1; '
        'DEPLOY_SYNC_SOURCE="$TEST_DEPLOY_SYNC_SOURCE"; '
        'SOURCE_HEAD_SHA="$TEST_SOURCE_HEAD_SHA"; '
        'RUNTIME_REQUIREMENTS_SHA256="$TEST_RUNTIME_REQUIREMENTS_SHA256"; '
        'RUNTIME_FREEZE_SHA256="$TEST_RUNTIME_FREEZE_SHA256"; '
        'RUNTIME_ID="$TEST_RUNTIME_ID"; DEPLOYED_AT="$TEST_DEPLOYED_AT"; '
        'if beta_candidate_tls_gate; then exit 97; fi; '
        'if abort_deploy "candidate failed canonical TLS pre-commit gate"; then exit 98; fi; '
        'test "$DEPLOY_TRANSACTION_ACTIVE" = 1; '
        'deployment_restore_transaction_state; '
        'test ! -e "$RUNTIME_CURRENT"; '
        'test "$(cat "$TARGET/app.py")" = "legacy code"; '
        'test ! -e "$TARGET/new.py"; '
        'test "$(cat "$TARGET/venv/bin/python")" = "legacy runtime"; '
        f'test "$(cat "$SYSTEMD_UNIT_TARGET")" = '
        f'{shlex.quote(f"ExecStart={legacy_python}")}; '
        'DEPLOY_TRANSACTION_ACTIVE=0; deployment_transaction_cleanup'
    )

    result = _source_deploy(body, env=env)

    assert result.returncode == 0, result.stderr
    assert "candidate failed canonical TLS pre-commit gate" in result.stderr
    assert not (runtime_root / "current").exists()
    assert legacy_python.read_text(encoding="utf-8") == "legacy runtime\n"
    assert (target / "app.py").read_text(encoding="utf-8") == "legacy code\n"
