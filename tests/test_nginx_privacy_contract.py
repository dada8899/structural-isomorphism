"""Fail-closed privacy and transaction contracts for public Nginx vhosts."""

from __future__ import annotations

from pathlib import Path
import os
import re
import signal
import stat
import subprocess
import time

import pytest


ROOT = Path(__file__).parents[1]
BETA_CONFIG = ROOT / "web/scripts/beta-structural.nginx.conf"
PHASE_CONFIG = ROOT / "web/phase-detector/phase.bytedance.city.nginx.conf"
INSTALLER = ROOT / "scripts/install-nginx-privacy-vhost.sh"
PHASE_DEPLOY = ROOT / "scripts/deploy-phase-detector-vps.sh"
PHASE_TEST_ISOLATION_MARKER = "structural-phase-test-isolation-v1"
CANONICAL_PRIVACY_KEY = ("01234567" + "89abcdef") * 4
ALLOWED_LOG_VARIABLES = {
    "$request_id",
    "$request_method",
    "$status",
    "$body_bytes_sent",
    "$request_time",
    "$upstream_response_time",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _log_format(config: str, name: str) -> str:
    match = re.search(rf"\blog_format\s+{re.escape(name)}\s+(.*?);", config, re.DOTALL)
    assert match, f"missing log format {name}"
    return match.group(1)


def _server_blocks(config: str) -> list[str]:
    blocks: list[str] = []
    start = 0
    while True:
        match = re.search(r"(?m)^\s*server\s*\{", config[start:])
        if not match:
            return blocks
        begin = start + match.start()
        cursor = start + match.end()
        depth = 1
        while cursor < len(config) and depth:
            if config[cursor] == "{":
                depth += 1
            elif config[cursor] == "}":
                depth -= 1
            cursor += 1
        assert depth == 0, "unterminated server block"
        blocks.append(config[begin:cursor])
        start = cursor


def _assert_privacy_vhost(config: str, name: str, domain: str) -> None:
    rendered = _log_format(config, name)
    variables = set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", rendered))
    assert variables == ALLOWED_LOG_VARIABLES
    assert not re.search(r"\$(?:uri|request_uri|args|arg_|cookie_|http_|remote_)", rendered)

    blocks = [
        block for block in _server_blocks(config)
        if re.search(rf"\bserver_name\s+{re.escape(domain)}\s*;", block)
    ]
    assert len(blocks) == 2
    for block in blocks:
        assert block.count(f"access_log /var/log/nginx/access.log {name};") == 1
        assert block.count("error_log /dev/null crit;") == 1
        assert block.count("proxy_hide_header Referrer-Policy;") == 1
        assert block.count('add_header Referrer-Policy "no-referrer" always;') == 1
        assert block.count("proxy_pass ") == block.count(
            "proxy_set_header X-Request-ID $request_id;"
        )
        assert block.count("proxy_pass ") == block.count(
            'proxy_set_header X-Forwarded-Host "";'
        )


def test_beta_vhost_uses_content_free_request_telemetry() -> None:
    _assert_privacy_vhost(
        _read(BETA_CONFIG),
        "structural_beta_privacy",
        "beta.structural.bytedance.city",
    )


def test_phase_vhost_uses_content_free_request_telemetry() -> None:
    _assert_privacy_vhost(
        _read(PHASE_CONFIG),
        "structural_phase_privacy",
        "phase.bytedance.city",
    )


@pytest.mark.parametrize(
    ("path", "host"),
    [
        (BETA_CONFIG, "beta.structural.bytedance.city"),
        (PHASE_CONFIG, "phase.bytedance.city"),
    ],
)
def test_http_redirects_drop_query_and_pin_the_host(path: Path, host: str) -> None:
    config = _read(path)
    redirects = re.findall(r"\breturn\s+30[178]\s+([^;]+);", config)
    assert redirects == [f"https://{host}$uri"]
    assert not set(re.findall(r"\$[A-Za-z0-9_]+", redirects[0])).intersection(
        {"$request", "$request_uri", "$args", "$query_string", "$host"}
    )


def test_phase_http_vhost_preserves_acme_challenge() -> None:
    phase = _read(PHASE_CONFIG)
    http_block = next(block for block in _server_blocks(phase) if "listen 80;" in block)
    assert "location /.well-known/acme-challenge/" in http_block
    assert "root /var/www/html;" in http_block
    assert "location / {" in http_block


def _canonical_candidate() -> str:
    return """log_format test_privacy
    'request_id=$request_id method=$request_method '
    'status=$status bytes=$body_bytes_sent request_time=$request_time '
    'upstream_time=$upstream_response_time';
server {
    listen 443 ssl;
    server_name private.example.test;
    access_log /var/log/nginx/access.log test_privacy;
    error_log /dev/null crit;
    proxy_hide_header Referrer-Policy;
    add_header Referrer-Policy "no-referrer" always;
    location / {
        proxy_pass http://127.0.0.1:5004;
        proxy_set_header X-Request-ID $request_id;
    }
}
server {
    listen 80;
    server_name private.example.test;
    access_log /var/log/nginx/access.log test_privacy;
    error_log /dev/null crit;
    proxy_hide_header Referrer-Policy;
    add_header Referrer-Policy "no-referrer" always;
    location / { return 301 https://private.example.test$uri; }
}
"""


def _installer_fixture(tmp_path: Path, *, existing: bool = True):
    source = tmp_path / "candidate.conf"
    source.write_text(_canonical_candidate(), encoding="utf-8")
    target = tmp_path / "etc/nginx/conf.d/private.conf"
    target.parent.mkdir(parents=True)
    prior = b"prior-vhost-bytes\n"
    if existing:
        target.write_bytes(prior)
        target.chmod(0o640)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    nginx = fake_bin / "nginx"
    nginx.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
increment() {
  name="$1"
  count=0
  [[ ! -f "$FAKE_STATE/$name-count" ]] || count="$(cat "$FAKE_STATE/$name-count")"
  count=$((count + 1))
  printf '%s' "$count" > "$FAKE_STATE/$name-count"
  printf '%s' "$count"
}
if [[ "$1" == "-t" ]]; then
  count="$(increment syntax)"
  if [[ -n "${SIGNAL_ON_NGINX_T:-}" && "$count" == "1" ]]; then
    kill -s "$SIGNAL_ON_NGINX_T" "$PPID"
    sleep 1
  fi
  [[ "${FAIL_NGINX_T_ON:-0}" != "$count" ]]
elif [[ "$1" == "-T" ]]; then
  count="$(increment effective)"
  mode="$(stat -c '%a' "$NGINX_PRIVACY_EFFECTIVE_FILE" 2>/dev/null || stat -f '%Lp' "$NGINX_PRIVACY_EFFECTIVE_FILE")"
  printf '%s' "$mode" > "$FAKE_STATE/effective-output-mode"
  if [[ "${FAIL_EFFECTIVE:-0}" == "1" ]]; then
    printf '%s\n' '# effective candidate deliberately missing'
  else
    if [[ -n "${EXTRA_EFFECTIVE:-}" ]]; then cat "$EXTRA_EFFECTIVE"; fi
    cat "$NGINX_TARGET"
    if [[ "${DUPLICATE_TARGET_VHOST:-0}" == "1" ]]; then cat "$NGINX_TARGET"; fi
  fi
  [[ "$count" == "1" ]]
else
  exit 2
fi
""",
        encoding="utf-8",
    )
    nginx.chmod(0o755)
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "restart" && "$2" == "phase-detector-api" && "$3" == "phase-detector-web" ]]; then
  exit 0
fi
if [[ "$1" == "is-active" && "$2" == "--quiet" ]]; then
  exit 0
fi
[[ "$1" == "reload" && "$2" == "nginx" ]]
count=0
[[ ! -f "$FAKE_STATE/reload-count" ]] || count="$(cat "$FAKE_STATE/reload-count")"
count=$((count + 1))
printf '%s' "$count" > "$FAKE_STATE/reload-count"
if [[ "${KILL_ON_RELOAD:-0}" == "$count" ]]; then kill -KILL "$PPID"; sleep 1; fi
if [[ -n "${REPLACE_TARGET_ON_RELOAD:-}" && "$count" == "1" ]]; then
  cp "$REPLACE_TARGET_ON_RELOAD" "$NGINX_TARGET"
fi
if [[ "${FAIL_RELOAD_ALWAYS:-0}" == "1" ]]; then exit 1; fi
if [[ "${FAIL_RELOAD_ON:-0}" == "$count" ]]; then exit 1; fi
""",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "TMPDIR": str(tmp_path),
            "STRUCTURAL_NGINX_TEST_ROOT": str(tmp_path),
            "FAKE_STATE": str(tmp_path),
            "NGINX_TARGET": str(target),
        }
    )
    command = [
        "bash",
        str(INSTALLER),
        str(source),
        str(target),
        "private.example.test",
        "test_privacy",
    ]
    state = tmp_path / "var/lib/structural-isomorphism/nginx-privacy"
    return source, target, prior, state, env, command


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, capture_output=True, text=True, check=False)


_PHASE_TEST_CONTAINMENT_GUARD = (
    'phase_test_root="$(cd -P -- "$STRUCTURAL_PHASE_TEST_ROOT" && pwd)" || exit 97; '
    'phase_repo_root="$(cd -P -- "$PHASE_REPO" && pwd)" || exit 97; '
    '[[ "$phase_repo_root" != "$phase_test_root" ]] || '
    '{ echo "refusing Phase recovery at test root" >&2; exit 97; }; '
    'case "$phase_repo_root" in "$phase_test_root"/*) ;; '
    '*) echo "refusing Phase recovery outside test root" >&2; exit 97 ;; esac; '
    '[[ -d "$phase_repo_root/.git" && ! -L "$phase_repo_root/.git" ]] || '
    '{ echo "refusing non-isolated Phase recovery repository" >&2; exit 97; }; '
)


def _phase_test_command(body: str) -> list[str]:
    return [
        "bash",
        "-c",
        _PHASE_TEST_CONTAINMENT_GUARD
        + 'source "$PHASE_DEPLOY_SCRIPT"; '
        + '[[ "$(cd -P -- "$REPO" && pwd)" == "$phase_repo_root" ]] || exit 97; '
        + body,
    ]


def _bind_phase_test_repository(
    env: dict[str, str], repository: Path, tmp_path: Path
) -> None:
    test_root = tmp_path.resolve(strict=True)
    repository_root = repository.resolve(strict=True)
    assert repository_root != ROOT.resolve(strict=True)
    assert repository_root != test_root
    assert repository_root.is_relative_to(test_root)
    assert not repository.is_symlink()
    assert (repository / ".git").is_dir()
    assert not (repository / ".git").is_symlink()
    marker = repository_root / ".git" / PHASE_TEST_ISOLATION_MARKER
    marker.write_text(
        f"protocol={PHASE_TEST_ISOLATION_MARKER}\n"
        f"test_root={test_root}\n"
        f"repo_root={repository_root}\n",
        encoding="utf-8",
    )
    marker.chmod(0o600)
    env["PHASE_REPO"] = str(repository_root)
    env["STRUCTURAL_PHASE_TEST_ROOT"] = str(test_root)


def _phase_recovery_repository(tmp_path: Path, fake_bin: Path) -> tuple[Path, str]:
    repository = tmp_path / "phase-repository"
    phase_dir = repository / "web/phase-detector"
    requirements = repository / "v4/product/d1_phase_detector/api/requirements.txt"
    pip = repository / ".venv/bin/pip"
    phase_dir.mkdir(parents=True)
    requirements.parent.mkdir(parents=True)
    pip.parent.mkdir(parents=True)
    (phase_dir / PHASE_CONFIG.name).write_bytes(PHASE_CONFIG.read_bytes())
    dropin = ROOT / "web/phase-detector/phase-detector-api-privacy.conf"
    (phase_dir / dropin.name).write_bytes(dropin.read_bytes())
    requirements.write_text("", encoding="utf-8")
    pip.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pip.chmod(0o755)
    (repository / "release.txt").write_text("committed\n", encoding="utf-8")

    pnpm = fake_bin / "pnpm"
    pnpm.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pnpm.chmod(0o755)

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init", "-q")
    git("config", "user.email", "phase-recovery@example.test")
    git("config", "user.name", "Phase Recovery Test")
    git("add", ".")
    git("commit", "-qm", "isolated previous release")
    return repository, git("rev-parse", "HEAD")


def _test_hook(tmp_path: Path, name: str, body: str) -> Path:
    hook = tmp_path / name
    hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
    hook.chmod(0o700)
    return hook


@pytest.mark.parametrize("existing", [True, False])
def test_installer_rolls_back_candidate_nginx_test_failure(tmp_path: Path, existing: bool) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path, existing=existing)
    env["FAIL_NGINX_T_ON"] = "1"

    result = _run(command, env)

    assert result.returncode != 0
    if existing:
        assert target.read_bytes() == prior
        assert stat.S_IMODE(target.stat().st_mode) == 0o640
    else:
        assert not target.exists()
    assert (tmp_path / "reload-count").read_text() == "1"
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize(
    ("failure_variable", "expected_reloads"),
    [("FAIL_RELOAD_ON", "2"), ("FAIL_EFFECTIVE", "2")],
)
def test_installer_rolls_back_reload_or_effective_failure(
    tmp_path: Path, failure_variable: str, expected_reloads: str
) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    env[failure_variable] = "1"

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert (tmp_path / "reload-count").read_text() == expected_reloads
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize("sig", ["INT", "TERM", "HUP"])
def test_installer_rolls_back_on_process_signals(tmp_path: Path, sig: str) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    env["SIGNAL_ON_NGINX_T"] = sig

    result = _run(command, env)

    assert result.returncode == 128 + getattr(signal, f"SIG{sig}")
    assert target.read_bytes() == prior
    assert (tmp_path / "reload-count").read_text() == "1"
    assert not list(state.glob("test_privacy.*"))


def test_installer_recovers_after_untrappable_kill(tmp_path: Path) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    env["KILL_ON_RELOAD"] = "1"

    killed = _run(command, env)

    assert killed.returncode == -signal.SIGKILL
    assert target.read_bytes() == source.read_bytes()
    assert (state / "test_privacy.journal").is_file()
    assert (state / "test_privacy.backup").read_bytes() == prior
    assert stat.S_IMODE((state / "test_privacy.journal").stat().st_mode) == 0o600
    assert stat.S_IMODE((state / "test_privacy.backup").stat().st_mode) == 0o600

    env.pop("KILL_ON_RELOAD")
    recovered = _run(command, env)

    assert recovered.returncode == 0, recovered.stderr
    assert target.read_bytes() == source.read_bytes()
    assert not list(state.glob("test_privacy.*"))
    assert (tmp_path / "reload-count").read_text() == "3"


def test_installer_supports_outer_prepare_commit_transaction(tmp_path: Path) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    env["STRUCTURAL_NGINX_TRANSACTION_ACTION"] = "prepare"

    prepared = _run(command, env)

    assert prepared.returncode == 0, prepared.stderr
    assert target.read_bytes() == source.read_bytes()
    assert (state / "test_privacy.journal").is_file()
    assert (state / "test_privacy.backup").read_bytes() == prior

    env["STRUCTURAL_NGINX_TRANSACTION_ACTION"] = "commit"
    committed = _run(command, env)

    assert committed.returncode == 0, committed.stderr
    assert target.read_bytes() == source.read_bytes()
    assert not list(state.glob("test_privacy.*"))
    assert (tmp_path / "reload-count").read_text() == "1"
    assert (tmp_path / "effective-count").read_text() == "1"


def test_installer_supports_outer_prepare_rollback_transaction(tmp_path: Path) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    env["STRUCTURAL_NGINX_TRANSACTION_ACTION"] = "prepare"
    assert _run(command, env).returncode == 0
    assert target.read_bytes() == source.read_bytes()

    env["STRUCTURAL_NGINX_TRANSACTION_ACTION"] = "rollback"
    rolled_back = _run(command, env)

    assert rolled_back.returncode == 0, rolled_back.stderr
    assert target.read_bytes() == prior
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not list(state.glob("test_privacy.*"))
    assert (tmp_path / "reload-count").read_text() == "2"


def test_installer_serializes_same_format_transactions(tmp_path: Path) -> None:
    _, target, _, state, env, command = _installer_fixture(tmp_path)
    entered = tmp_path / "lock-entered"
    release = tmp_path / "lock-release"
    hook = _test_hook(
        tmp_path,
        "hold-after-snapshot.sh",
        'touch "$LOCK_ENTERED"\n'
        'while [[ ! -f "$LOCK_RELEASE" ]]; do sleep 0.05; done\n',
    )
    first_env = env.copy()
    first_env.update({
        "STRUCTURAL_NGINX_TEST_AFTER_SNAPSHOT_HOOK": str(hook),
        "LOCK_ENTERED": str(entered),
        "LOCK_RELEASE": str(release),
    })
    first = subprocess.Popen(
        command, env=first_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not entered.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert entered.exists(), "first installer did not reach the locked section"

        second_env = env.copy()
        second_env["STRUCTURAL_NGINX_LOCK_TIMEOUT_SECONDS"] = "0"
        second = _run(command, second_env)
        assert second.returncode != 0
        assert "another privacy vhost transaction is active" in second.stderr
        assert target.read_bytes() != _canonical_candidate().encode()
    finally:
        release.touch()
        stdout, stderr = first.communicate(timeout=10)
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
    assert first.returncode == 0, (stdout, stderr)
    assert target.read_text(encoding="utf-8") == _canonical_candidate()
    assert not list(state.glob("test_privacy.*"))


def test_installer_uses_the_validated_source_snapshot_after_source_swap(
    tmp_path: Path,
) -> None:
    source, target, _, state, env, command = _installer_fixture(tmp_path)
    original = source.read_bytes()
    hook = _test_hook(
        tmp_path,
        "replace-source.sh",
        'printf "%s\\n" "invalid source after snapshot" >"$SWAP_SOURCE"\n',
    )
    env["STRUCTURAL_NGINX_TEST_AFTER_SNAPSHOT_HOOK"] = str(hook)
    env["SWAP_SOURCE"] = str(source)

    result = _run(command, env)

    assert result.returncode == 0, result.stderr
    assert source.read_bytes() != original
    assert target.read_bytes() == original
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize("anchor", ["target", "state"])
def test_installer_rejects_parent_exchange_before_target_mutation(
    tmp_path: Path, anchor: str,
) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    parent = target.parent if anchor == "target" else state.parent
    saved = parent.with_name(parent.name + ".saved")
    hook = _test_hook(
        tmp_path,
        f"exchange-{anchor}-parent.sh",
        'mv "$SWAP_PARENT" "$SWAP_SAVED"\nmkdir "$SWAP_PARENT"\n',
    )
    env["STRUCTURAL_NGINX_TEST_BEFORE_TARGET_INSTALL_HOOK"] = str(hook)
    env["SWAP_PARENT"] = str(parent)
    env["SWAP_SAVED"] = str(saved)

    result = _run(command, env)

    assert result.returncode != 0
    assert not (tmp_path / "reload-count").exists()
    if anchor == "target":
        assert (saved / target.name).read_bytes() == prior
        assert not target.exists()
    else:
        assert target.read_bytes() == prior


def test_installer_retains_evidence_when_restore_reload_fails(tmp_path: Path) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    env["FAIL_RELOAD_ALWAYS"] = "1"

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert (state / "test_privacy.journal").is_file()
    assert (state / "test_privacy.backup").is_file()
    assert "journal and backup retained" in result.stderr


def test_installer_success_is_exact_single_capture_and_content_silent(tmp_path: Path) -> None:
    source, target, _, state, env, command = _installer_fixture(tmp_path)
    foreign = tmp_path / "foreign.conf"
    secret = "private-token-canary-never-print"
    foreign.write_text(
        f"# {secret}\nserver {{ listen 443 ssl; server_name other.example.test; }}\n",
        encoding="utf-8",
    )
    env["EXTRA_EFFECTIVE"] = str(foreign)

    result = _run(command, env)

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == source.read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert (tmp_path / "reload-count").read_text() == "1"
    assert (tmp_path / "effective-count").read_text() == "1"
    assert (tmp_path / "effective-output-mode").read_text() == "600"
    assert secret not in result.stdout + result.stderr
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda text: (
                "# whole-line closing brace: }\n"
                "# whole-line opening brace: {\n"
                "# whole-line semicolon: ;\n"
                + text.replace(
                    "server_name private.example.test;",
                    "server_name private.example.test; # inline } { ; comment",
                    1,
                )
            ),
            id="whole-line-and-inline-comments",
        ),
        pytest.param(
            lambda text: text.replace(
                "    'upstream_time=$upstream_response_time';",
                "    'upstream_time=$upstream_response_time '\n"
                '    "literal=escaped\\" # ; { }";',
            ),
            id="quoted-structural-characters-and-escaped-quote",
        ),
        pytest.param(
            lambda text: text.replace(
                "access_log /var/log/nginx/access.log test_privacy;",
                "access_log\n"
                "        /var/log/nginx/access.log\n"
                "        test_privacy;",
            ),
            id="multiline-directive",
        ),
    ],
)
def test_installer_lexer_accepts_nonstructural_comment_and_quoted_tokens(
    tmp_path: Path, mutation,
) -> None:
    source, target, _, state, env, command = _installer_fixture(tmp_path)
    candidate = mutation(source.read_text(encoding="utf-8"))
    source.write_text(candidate, encoding="utf-8")

    result = _run(command, env)

    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == candidate
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda text: text.replace(
                "        proxy_set_header X-Request-ID $request_id;\n"
                "    }\n"
                "}\n"
                "server {",
                "        proxy_set_header X-Request-ID $request_id;\n"
                "    }\n"
                "    # } old raw-brace scanner stopped the server here\n"
                "    access_log /tmp/private-query.log combined;\n"
                "    # { old raw-brace scanner never resumed this server\n"
                "}\n"
                "server {",
                1,
            ),
            id="comment-braces-cannot-hide-a-second-access-log",
        ),
        pytest.param(
            lambda text: text.replace(
                "    'upstream_time=$upstream_response_time';",
                "    'upstream_time=$upstream_response_time' # ; old capture stopped here\n"
                "    '$request_uri';",
            ),
            id="comment-semicolon-cannot-hide-unsafe-log-variable",
        ),
        pytest.param(
            lambda text: text.replace(
                'add_header Referrer-Policy "no-referrer" always;',
                'add_header Referrer-Policy "no-referrer # ; { } always;',
                1,
            ),
            id="unterminated-quote-fails-closed",
        ),
    ],
)
def test_installer_lexer_rejects_comment_and_quote_boundary_attacks(
    tmp_path: Path, mutation,
) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    source.write_text(mutation(source.read_text(encoding="utf-8")), encoding="utf-8")

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace("$request_id method=", "$uri method="),
        lambda text: text.replace(
            "error_log /dev/null crit;",
            "error_log /dev/null crit;\n    access_log /tmp/private-query.log combined;",
            1,
        ),
        lambda text: text.replace(
            "error_log /dev/null crit;",
            "error_log /dev/null crit;\n    access_log\n      /tmp/private-query.log combined;",
            1,
        ),
        lambda text: text.replace(
            "error_log /dev/null crit;",
            "error_log /dev/null crit; access_log /tmp/private-query.log combined;",
            1,
        ),
        lambda text: text.replace(
            "error_log /dev/null crit;",
            "error_log /dev/null crit;\n    error_log /tmp/private-errors.log info;",
            1,
        ),
        lambda text: text.replace(
            "error_log /dev/null crit;",
            "error_log /dev/null crit;\n    include /tmp/unreviewed-vhost.conf;",
            1,
        ),
        lambda text: text + "log_format unreviewed '$request_uri';\n",
        lambda text: text.replace(
            "server_name private.example.test;",
            "server_name injected.example.test;",
            1,
        ),
        lambda text: text.replace("error_log /dev/null crit;", "error_log /tmp/request-errors warn;", 1),
        lambda text: text.replace("proxy_hide_header Referrer-Policy;", "", 1),
        lambda text: text + "server { server_name injected.example.test; }\n",
    ],
)
def test_installer_rejects_source_contract_bypasses(tmp_path: Path, mutation) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    source.write_text(mutation(source.read_text(encoding="utf-8")), encoding="utf-8")

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert not list(state.glob("test_privacy.*"))


def test_installer_rejects_duplicate_effective_domain_vhosts(tmp_path: Path) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    env["DUPLICATE_TARGET_VHOST"] = "1"

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert not list(state.glob("test_privacy.*"))


def test_installer_validates_the_real_applied_file_and_rolls_back_disk_tampering(
    tmp_path: Path,
) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    tampered = tmp_path / "tampered-applied.conf"
    tampered.write_text(
        source.read_text(encoding="utf-8").replace(
            "error_log /dev/null crit;",
            "error_log /dev/null crit;\n    access_log /tmp/raw-request.log combined;",
            1,
        ),
        encoding="utf-8",
    )
    env["REPLACE_TARGET_ON_RELOAD"] = str(tampered)

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert (tmp_path / "reload-count").read_text() == "2"
    assert not list(state.glob("test_privacy.*"))


@pytest.mark.parametrize("kind", ["source_symlink", "target_symlink", "source_fifo", "target_fifo"])
def test_installer_rejects_symlink_and_special_file_paths(tmp_path: Path, kind: str) -> None:
    source, target, prior, state, env, command = _installer_fixture(tmp_path)
    if kind == "source_symlink":
        real = tmp_path / "real-source.conf"
        source.rename(real)
        source.symlink_to(real)
    elif kind == "target_symlink":
        target.unlink()
        real = tmp_path / "real-target.conf"
        real.write_bytes(prior)
        target.symlink_to(real)
    elif kind == "source_fifo":
        source.unlink()
        os.mkfifo(source)
    else:
        target.unlink()
        os.mkfifo(target)

    result = _run(command, env)

    assert result.returncode != 0
    assert not state.exists()


@pytest.mark.parametrize(
    ("arg_index", "value"),
    [
        (2, "../private.example.test"),
        (2, "Private.Example.Test"),
        (3, "bad-format;include"),
    ],
)
def test_installer_rejects_domain_and_format_injection(
    tmp_path: Path, arg_index: int, value: str
) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    command[arg_index + 2] = value

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert not state.exists()


def test_installer_rejects_parent_traversal_before_mutation(tmp_path: Path) -> None:
    _, target, prior, state, env, command = _installer_fixture(tmp_path)
    command[2] = str(target.parent / ".." / "conf.d" / target.name)

    result = _run(command, env)

    assert result.returncode != 0
    assert target.read_bytes() == prior
    assert not state.exists()


def test_installer_is_bash3_compatible_by_construction() -> None:
    script = _read(INSTALLER)
    for unsupported in ("declare -A", "mapfile", "readarray", "${BASH_SOURCE[0],,"):
        assert unsupported not in script
    subprocess.run(["bash", "-n", str(INSTALLER)], check=True)


def test_beta_runtime_exposes_the_privacy_installer_interface() -> None:
    unit = _read(ROOT / "web/scripts/structural-web.service")
    deploy = _read(ROOT / "scripts/deploy-vps.sh")
    exec_lines = [line for line in unit.splitlines() if line.startswith("ExecStart=")]
    assert len(exec_lines) == 1
    assert exec_lines[0].endswith("--no-access-log")
    assert 'bash "$NGINX_INSTALLER"' in deploy
    assert "beta.structural.bytedance.city:443:127.0.0.1" in deploy


def test_phase_deploy_owns_dropin_and_nginx_privacy_transactions() -> None:
    dropin = _read(ROOT / "web/phase-detector/phase-detector-api-privacy.conf")
    deploy = _read(ROOT / "scripts/deploy-phase-detector-vps.sh")
    assert "\nExecStart=\n" in f"\n{dropin}"
    assert dropin.count("--no-access-log") == 1
    assert "install_phase_privacy_dropin" in deploy
    assert "restore_phase_privacy_dropin" in deploy
    assert "rollback_phase_nginx" in deploy
    assert "commit_phase_privacy" in deploy
    assert "STRUCTURAL_NGINX_TRANSACTION_ACTION=prepare" in deploy
    assert "STRUCTURAL_NGINX_TRANSACTION_ACTION=commit" in deploy
    assert "STRUCTURAL_NGINX_TRANSACTION_ACTION=rollback" in deploy
    assert 'bash "$NGINX_PRIVACY_INSTALLER"' in deploy
    assert "phase.bytedance.city:443:127.0.0.1" in deploy
    assert "Referrer-Policy: no-referrer" in deploy
    prepare_at = deploy.index("STRUCTURAL_NGINX_TRANSACTION_ACTION=prepare", deploy.index("trap 'rollback_phase"))
    dropin_at = deploy.index("install_phase_privacy_dropin", prepare_at)
    restart_at = deploy.index("systemctl restart phase-detector-api phase-detector-web", dropin_at)
    assert prepare_at < dropin_at < restart_at
    for sig in ("ERR", "INT", "TERM", "HUP"):
        assert "trap 'rollback_phase" in deploy and sig in deploy
    for durable_marker in (
        "PHASE_DEPLOY_JOURNAL",
        "begin_phase_outer_transaction",
        "recover_phase_outer_transaction",
        "phase_outer_mark smoke_passed",
        "phase_outer_mark nginx_committed",
    ):
        assert durable_marker in deploy


def test_phase_recovery_guard_rejects_shared_repository(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PHASE_REPO": str(ROOT),
            "STRUCTURAL_PHASE_TEST_ROOT": str(tmp_path),
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
        }
    )

    rejected = subprocess.run(
        _phase_test_command('echo "guard unexpectedly passed"'),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert rejected.returncode == 97
    assert "refusing Phase recovery outside test root" in rejected.stderr
    assert "guard unexpectedly passed" not in rejected.stdout


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
def test_invalid_phase_privacy_hmac_key_is_zero_mutation_before_normal_deploy(
    tmp_path: Path, fault: str, privacy_key: str | None,
) -> None:
    repository = tmp_path / "phase-repository"
    repository.mkdir()
    code = repository / "release.txt"
    code.write_bytes(b"live-release-sentinel\n")
    state = tmp_path / "phase-state"
    nginx_target = tmp_path / "phase.nginx.conf"
    nginx_target.write_bytes(b"nginx-sentinel\n")
    dropin_target = tmp_path / "20-privacy.conf"
    dropin_target.write_bytes(b"dropin-sentinel\n")
    auth_env = tmp_path / "phase-auth.env"
    valid_key = CANONICAL_PRIVACY_KEY
    lines = ["AUTH_ENABLED=true"]
    if privacy_key is not None:
        lines.append(f"STRUCTURAL_PRIVACY_HMAC_KEY={privacy_key}")
    if fault == "duplicate":
        lines.append(f"STRUCTURAL_PRIVACY_HMAC_KEY={valid_key}")
    auth_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    auth_env.chmod(0o600)

    immutable = {
        path: path.read_bytes() for path in (code, nginx_target, dropin_target, auth_env)
    }
    env = os.environ.copy()
    env.update(
        {
            "PHASE_REPO": str(repository),
            "PHASE_AUTH_ENV_FILE": str(auth_env),
            "PHASE_DEPLOY_STATE_DIR": str(state),
            "PHASE_NGINX_TARGET": str(nginx_target),
            "PHASE_PRIVACY_DROPIN_TARGET": str(dropin_target),
            "STRUCTURAL_DEPLOY_LOCK_HELD": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(PHASE_DEPLOY)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (result.stdout, result.stderr)
    assert "STRUCTURAL_PRIVACY_HMAC_KEY" in result.stderr
    assert {path: path.read_bytes() for path in immutable} == immutable
    assert not state.exists()


def test_phase_privacy_hmac_preflight_uses_canonical_ascii_before_mutation() -> None:
    deploy = _read(PHASE_DEPLOY)
    validator_start = deploy.index("validate_phase_privacy_hmac_key()")
    validator_end = deploy.index("\n}\n\nvalidate_phase_privacy_hmac_preflight", validator_start)
    validator = deploy[validator_start:validator_end]
    assert "/usr/bin/python3 -I -c" in validator
    assert 're.fullmatch(rb"[0-9a-f]{64}", raw)' in validator
    assert "len(set(raw)) >= 12" in validator

    first_preflight = deploy.index("validate_phase_privacy_hmac_preflight || exit 1")
    lock = deploy.index("exec 9>/var/lock/structural-isomorphism-deploy.lock", first_preflight)
    second_preflight = deploy.index(
        "validate_phase_privacy_hmac_preflight || exit 1", lock
    )
    recovery = deploy.index("recover_phase_outer_transaction ||", second_preflight)
    journal = deploy.index("begin_phase_outer_transaction ||", second_preflight)
    checkout = deploy.index('phase_sync_exact_commit "$DEPLOY_SHA"', second_preflight)
    third_preflight = deploy.index(
        "validate_phase_privacy_hmac_preflight || exit 1", checkout
    )
    assert (
        first_preflight
        < lock
        < second_preflight
        < recovery
        < journal
        < checkout
        < third_preflight
    )


def test_phase_privacy_hmac_validator_rejects_noncanonical_utf8() -> None:
    value = "结构同构隐私密钥-2026-AbCdEfG"
    assert len(value) < 32 <= len(value.encode("utf-8"))
    assert len(set(value.encode("utf-8"))) >= 12
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$PHASE_DEPLOY_SCRIPT"; '
            'validate_phase_privacy_hmac_key "$TEST_PRIVACY_KEY"',
        ],
        env={
            **os.environ,
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "TEST_PRIVACY_KEY": value,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_phase_recovery_only_does_not_require_privacy_key(tmp_path: Path) -> None:
    state = tmp_path / "phase-state"
    result = subprocess.run(
        ["bash", str(PHASE_DEPLOY)],
        env={
            **os.environ,
            "PHASE_REPO": str(tmp_path / "unused-repository"),
            "PHASE_AUTH_ENV_FILE": str(tmp_path / "missing-auth.env"),
            "PHASE_DEPLOY_STATE_DIR": str(state),
            "STRUCTURAL_DEPLOY_LOCK_HELD": "1",
            "STRUCTURAL_PHASE_RECOVERY_ONLY": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert state.is_dir()


def test_phase_destructive_guard_cannot_be_bypassed_by_direct_source(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    git_marker = tmp_path / "git-called"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\nprintf called >\"$FAKE_GIT_MARKER\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$PHASE_DEPLOY_SCRIPT"; '
            'restore_previous_phase_release "$TEST_SHA"',
        ],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
            "PHASE_REPO": str(ROOT),
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "STRUCTURAL_PHASE_TEST_ROOT": str(tmp_path),
            "FAKE_GIT_MARKER": str(git_marker),
            "TEST_SHA": "0" * 40,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "refusing destructive Phase recovery" in result.stderr
    assert not git_marker.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "unset STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY",
        "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY=0",
        "export STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY=0",
    ],
)
def test_phase_library_context_cannot_be_downgraded_after_source(
    tmp_path: Path, mutation: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    git_marker = tmp_path / "git-called"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\nprintf called >\"$FAKE_GIT_MARKER\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$PHASE_DEPLOY_SCRIPT"; '
            f"{mutation}; "
            'if (PHASE_DEPLOY_LIBRARY_CONTEXT=0) 2>/dev/null; then exit 88; fi; '
            'restore_previous_phase_release "$TEST_SHA"',
        ],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
            "PHASE_REPO": str(ROOT),
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "STRUCTURAL_PHASE_TEST_ROOT": str(tmp_path),
            "FAKE_GIT_MARKER": str(git_marker),
            "TEST_SHA": "0" * 40,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "refusing destructive Phase recovery" in result.stderr
    assert not git_marker.exists()


@pytest.mark.parametrize(
    "attack",
    [
        "repo_equals_root",
        "old_tree_without_capability",
        "marker_symlink",
        "marker_wrong_mode",
        "marker_wrong_binding",
        "marker_extra_line",
        "repository_symlink",
    ],
)
def test_phase_destructive_capability_rejects_self_reported_or_forged_isolation(
    tmp_path: Path, attack: str,
) -> None:
    declared_root = tmp_path / "declared-root"
    repository = declared_root / "old-tree"
    git_dir = repository / ".git"
    git_dir.mkdir(parents=True)
    repository_arg = repository
    if attack == "repo_equals_root":
        declared_root = repository
    elif attack == "repository_symlink":
        repository_arg = declared_root / "repository-link"
        repository_arg.symlink_to(repository, target_is_directory=True)

    physical_root = declared_root.resolve(strict=True)
    physical_repo = repository.resolve(strict=True)
    marker = git_dir / PHASE_TEST_ISOLATION_MARKER
    content = (
        f"protocol={PHASE_TEST_ISOLATION_MARKER}\n"
        f"test_root={physical_root}\n"
        f"repo_root={physical_repo}\n"
    )
    if attack not in {"old_tree_without_capability", "marker_symlink"}:
        marker.write_text(content, encoding="utf-8")
        marker.chmod(0o600)
    if attack == "marker_symlink":
        marker_target = tmp_path / "forged-marker"
        marker_target.write_text(content, encoding="utf-8")
        marker_target.chmod(0o600)
        marker.symlink_to(marker_target)
    elif attack == "marker_wrong_mode":
        marker.chmod(0o644)
    elif attack == "marker_wrong_binding":
        marker.write_text(
            content.replace(f"test_root={physical_root}", "test_root=/forged/root"),
            encoding="utf-8",
        )
        marker.chmod(0o600)
    elif attack == "marker_extra_line":
        marker.write_text(content + "extra=forged\n", encoding="utf-8")
        marker.chmod(0o600)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    git_marker = tmp_path / "git-called"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\nprintf called >\"$FAKE_GIT_MARKER\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$PHASE_DEPLOY_SCRIPT"; '
            'restore_previous_phase_release "$TEST_SHA"',
        ],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
            "PHASE_REPO": str(repository_arg),
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "STRUCTURAL_PHASE_TEST_ROOT": str(declared_root),
            "FAKE_GIT_MARKER": str(git_marker),
            "TEST_SHA": "0" * 40,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "refusing destructive Phase recovery" in result.stderr
    assert not git_marker.exists()


def test_all_phase_git_resets_are_guarded_in_the_implementation() -> None:
    deploy = _read(PHASE_DEPLOY)
    restore_start = deploy.index("restore_previous_phase_release()")
    restore_reset = deploy.index('git -C "$REPO" reset --hard "$sha"', restore_start)
    assert deploy.index("phase_destructive_repo_safe", restore_start) < restore_reset

    rollback_start = deploy.index("rollback_phase()")
    rollback_reset = deploy.index('git -C "$REPO" reset --hard "$PREVIOUS_SHA"', rollback_start)
    assert deploy.index("phase_destructive_repo_safe", rollback_start) < rollback_reset

    sync_start = deploy.index("phase_sync_exact_commit()")
    sync_reset = deploy.index('git -C "$REPO" reset --hard "$deploy_sha"', sync_start)
    assert deploy.index("phase_destructive_repo_safe", sync_start) < sync_reset


def test_phase_outer_transaction_recovers_after_sigkill_by_finishing_commit(
    tmp_path: Path,
) -> None:
    target_dropin = tmp_path / "etc/systemd/system/phase-detector-api.service.d/20-privacy.conf"
    target_nginx = tmp_path / "etc/nginx/conf.d/phase.bytedance.city.conf"
    target_dropin.parent.mkdir(parents=True)
    target_nginx.parent.mkdir(parents=True)
    target_dropin.write_text("old dropin\n", encoding="utf-8")
    target_nginx.write_text("old nginx\n", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    nginx = fake_bin / "nginx"
    nginx.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n[[ \"$1\" == \"-t\" ]]\n",
        encoding="utf-8",
    )
    nginx.chmod(0o755)
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "case \"$1\" in daemon-reload|restart) exit 0;; is-active) exit 0;; *) exit 2;; esac\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    repository, previous_sha = _phase_recovery_repository(tmp_path, fake_bin)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "PHASE_PRIVACY_DROPIN_TARGET": str(target_dropin),
            "PHASE_NGINX_TARGET": str(target_nginx),
            "PHASE_DEPLOY_STATE_DIR": str(tmp_path / "state"),
            "STRUCTURAL_NGINX_TEST_ROOT": str(tmp_path),
            "STRUCTURAL_DEPLOY_LOCK_HELD": "1",
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
        }
    )
    _bind_phase_test_repository(env, repository, tmp_path)
    first = subprocess.run(
        _phase_test_command(
            'PREVIOUS_SHA="$(git -C "$REPO" rev-parse HEAD)"; '
            "begin_phase_outer_transaction; "
            'install -m 0644 "$PHASE_NGINX_SOURCE" "$PHASE_NGINX_TARGET"; '
            'install -m 0644 "$PHASE_PRIVACY_DROPIN_SOURCE" "$PHASE_PRIVACY_DROPIN_TARGET"; '
            "phase_outer_mark smoke_passed; kill -KILL $$"
        ),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == -signal.SIGKILL
    journal = tmp_path / "state/privacy.journal"
    backup = tmp_path / "state/privacy-dropin.backup"
    assert journal.is_file() and backup.is_file()
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600

    recovered = subprocess.run(
        _phase_test_command("recover_phase_outer_transaction"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert target_nginx.read_bytes() == (ROOT / "web/phase-detector/phase.bytedance.city.nginx.conf").read_bytes()
    assert target_dropin.read_bytes() == (ROOT / "web/phase-detector/phase-detector-api-privacy.conf").read_bytes()
    assert subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == previous_sha
    assert not journal.exists()
    assert not backup.exists()


def test_phase_outer_transaction_recovers_sigkill_between_nginx_prepare_and_mark(
    tmp_path: Path,
) -> None:
    _, target_nginx, prior, nginx_state, env, _ = _installer_fixture(tmp_path)
    target_dropin = tmp_path / "phase-systemd/20-privacy.conf"
    target_dropin.parent.mkdir(parents=True)
    target_dropin.write_text("old dropin\n", encoding="utf-8")
    outer_state = tmp_path / "phase-outer-state"
    repository, previous_sha = _phase_recovery_repository(tmp_path, tmp_path / "bin")
    env.update(
        {
            "PHASE_PRIVACY_DROPIN_TARGET": str(target_dropin),
            "PHASE_NGINX_TARGET": str(target_nginx),
            "PHASE_DEPLOY_STATE_DIR": str(outer_state),
            "STRUCTURAL_DEPLOY_LOCK_HELD": "1",
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
        }
    )
    _bind_phase_test_repository(env, repository, tmp_path)

    killed = subprocess.run(
        _phase_test_command(
            'PREVIOUS_SHA="$(git -C "$REPO" rev-parse HEAD)"; '
            "begin_phase_outer_transaction; "
            "STRUCTURAL_NGINX_TRANSACTION_ACTION=prepare "
            'bash "$NGINX_PRIVACY_INSTALLER" "$PHASE_NGINX_SOURCE" '
            '"$PHASE_NGINX_TARGET" phase.bytedance.city structural_phase_privacy; '
            "kill -KILL $$"
        ),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert killed.returncode == -signal.SIGKILL
    assert target_nginx.read_bytes() == PHASE_CONFIG.read_bytes()
    assert (outer_state / "privacy.journal").is_file()
    assert (nginx_state / "structural_phase_privacy.journal").is_file()
    (repository / "release.txt").write_text("dirty shared-worktree sentinel\n", encoding="utf-8")

    recovered = subprocess.run(
        _phase_test_command("recover_phase_outer_transaction"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert target_nginx.read_bytes() == prior
    assert target_dropin.read_text(encoding="utf-8") == "old dropin\n"
    assert (repository / "release.txt").read_text(encoding="utf-8") == "committed\n"
    assert subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == previous_sha
    assert subprocess.run(
        ["git", "-C", str(repository), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""
    assert not list(outer_state.glob("*"))
    assert not list(nginx_state.glob("structural_phase_privacy.*"))
    assert (tmp_path / "reload-count").read_text() == "2"


def test_phase_stale_recovery_rebinds_next_rollback_to_recovered_release(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    repository = tmp_path / "repository"
    remote.mkdir()
    repository.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git("init", "-q")
    git("config", "user.email", "phase-runtime@example.test")
    git("config", "user.name", "Phase Runtime Test")
    git("remote", "add", "origin", str(remote))
    git("checkout", "-qb", "main")
    app = repository / "release.txt"
    app.write_text("previous\n", encoding="utf-8")
    git("add", "release.txt")
    git("commit", "-qm", "previous")
    previous = git("rev-parse", "HEAD")
    app.write_text("interrupted\n", encoding="utf-8")
    git("commit", "-qam", "interrupted")
    interrupted = git("rev-parse", "HEAD")
    app.write_text("requested\n", encoding="utf-8")
    git("commit", "-qam", "requested")
    requested = git("rev-parse", "HEAD")
    git("push", "-qu", "origin", "main")
    git("reset", "--hard", interrupted)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("pnpm", "systemctl"):
        executable = fake_bin / name
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    pip = repository / ".venv/bin/pip"
    pip.parent.mkdir(parents=True)
    pip.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pip.chmod(0o755)
    requirements = repository / "v4/product/d1_phase_detector/api/requirements.txt"
    requirements.parent.mkdir(parents=True)
    requirements.write_text("", encoding="utf-8")
    (repository / "web/phase-detector").mkdir(parents=True)

    state = tmp_path / "state"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "PHASE_DEPLOY_STATE_DIR": str(state),
            "PHASE_PRIVACY_DROPIN_TARGET": str(tmp_path / "privacy.conf"),
            "PHASE_NGINX_TARGET": str(tmp_path / "phase.nginx.conf"),
            "STRUCTURAL_DEPLOY_LOCK_HELD": "1",
            "STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY": "1",
            "PHASE_DEPLOY_SCRIPT": str(PHASE_DEPLOY),
            "STALE_PREVIOUS_SHA": previous,
            "REQUESTED_SHA": requested,
        }
    )
    _bind_phase_test_repository(env, repository, tmp_path)
    stale = subprocess.run(
        _phase_test_command(
            'PREVIOUS_SHA="$STALE_PREVIOUS_SHA"; begin_phase_outer_transaction',
        ),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert stale.returncode == 0, stale.stderr
    assert (state / "privacy.journal").is_file()
    assert git("rev-parse", "HEAD") == interrupted

    failed = subprocess.run(
        _phase_test_command(
            "recover_phase_outer_transaction; "
            'PREVIOUS_SHA="$(git -C "$REPO" rev-parse --verify HEAD)"; '
            'begin_phase_outer_transaction; phase_sync_exact_commit "$REQUESTED_SHA"; '
            'rollback_phase 73 "injected failure"'
        ),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 73, failed.stderr
    assert git("rev-parse", "HEAD") == previous
    assert not (state / "privacy.journal").exists()
