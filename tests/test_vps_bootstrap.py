from pathlib import Path
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / 'scripts/bootstrap-structural-vps.sh'


def bootstrap_namespace():
    source = BOOTSTRAP.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    namespace = {'__name__': 'bootstrap_test'}
    exec(compile(source, str(BOOTSTRAP), 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('mode,uid', [(stat.S_IFLNK | 0o777, 0), (stat.S_IFDIR | 0o775, 0), (stat.S_IFDIR | 0o755, 501)])
def test_trusted_tool_parent_rejects_replaceable_paths(monkeypatch, mode, uid):
    ns = bootstrap_namespace()
    def metadata(path):
        return SimpleNamespace(st_mode=mode if path == Path('/opt/structural-tools') else stat.S_IFDIR | 0o755,
                               st_uid=uid if path == Path('/opt/structural-tools') else 0)
    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(SystemExit, match='untrusted bootstrap path'):
        ns['trusted']('/opt/structural-tools/bin/node')


def test_bootstrap_check_missing_prerequisite_does_not_write(monkeypatch):
    ns = bootstrap_namespace()
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    def missing():
        raise SystemExit('missing prerequisite')
    ns['prerequisites'] = missing
    monkeypatch.setattr(Path, 'mkdir', lambda *args, **kwargs: pytest.fail('check attempted mkdir'))
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('check attempted command mutation'))
    with pytest.raises(SystemExit, match='missing prerequisite'):
        ns['main']('--check')


def test_bootstrap_never_starts_services_or_fabricates_credentials():
    text = BOOTSTRAP.read_text()
    assert 'systemctl\', \'daemon-reload' in text
    assert 'systemctl start' not in text and 'systemctl enable' not in text
    assert 'curl' not in text and 'SMTP_PASSWORD=' not in text
    assert "'-m', 'venv', '--copies'" in text
    assert 'EnvironmentFile=/root/.config/structural-isomorphism/phase-auth.env' in text
    assert 'next start -p 3210 --hostname 127.0.0.1' in text
    assert 'Environment=DB_URL=sqlite:////var/lib/structural-isomorphism/phase/d1.sqlite' in text
    assert "Path('/var/lib/structural-isomorphism/phase')" in text


@pytest.mark.parametrize('workflow', ['deploy-beta-backend.yml', 'deploy-phase-detector.yml'])
def test_deploy_workflows_use_pinned_new_host_identity(workflow):
    text = (ROOT / '.github/workflows' / workflow).read_text()
    for name in ('HOST', 'USER', 'DEPLOY_KEY', 'KNOWN_HOSTS'):
        assert f'secrets.STRUCTURAL_VPS_{name}' in text
        assert f'secrets.VPS_{name}' not in text
    assert 'ssh-keyscan' not in text
    assert 'StrictHostKeyChecking=yes' in text
    assert 'ssh-keygen -F "$HOST" -f ~/.ssh/known_hosts' in text


def test_bootstrap_shell_and_embedded_python_compile():
    subprocess.run(['bash', '-n', str(BOOTSTRAP)], check=True)
    bootstrap_namespace()
