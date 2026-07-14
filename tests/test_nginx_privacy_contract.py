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
[[ "$1" == "reload" && "$2" == "nginx" ]]
count=0
[[ ! -f "$FAKE_STATE/reload-count" ]] || count="$(cat "$FAKE_STATE/reload-count")"
count=$((count + 1))
printf '%s' "$count" > "$FAKE_STATE/reload-count"
if [[ "${KILL_ON_RELOAD:-0}" == "$count" ]]; then kill -KILL "$PPID"; sleep 1; fi
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
        lambda text: text.replace("$request_id method=", "$uri method="),
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
