#!/usr/bin/env bash
# Prepare first-install directories and inactive units; never supply secrets,
# install downloaded tools, issue certificates, change DNS or start services.
set -euo pipefail
[[ $# -eq 0 || ( $# -eq 1 && "$1" == --check ) ]] || { echo 'usage: bootstrap-structural-vps.sh [--check]' >&2; exit 2; }
exec /usr/bin/python3 -I - "${1:-prepare}" <<'PY'
import os
import stat
import subprocess
import sys
from pathlib import Path

TOOLS = Path('/opt/structural-tools/bin')
REPO = Path('/root/Projects/structural-isomorphism-v4')
TARGET = Path('/root/Projects/structural-isomorphism')
DIRS = [TARGET / 'web/backend', Path('/root/structural-runtime/releases'),
        Path('/root/structural-artifacts'), Path('/root/.config/structural-isomorphism'),
        Path('/root/scripts'), Path('/var/lib/structural-isomorphism/phase-deploy'),
        Path('/var/lib/structural-isomorphism/phase')]
UNITS = {
    'phase-detector-api.service': '''[Unit]
Description=Structural Phase API
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/root/Projects/structural-isomorphism-v4
Environment=DB_URL=sqlite:////var/lib/structural-isomorphism/phase/d1.sqlite
Environment=STRUCTURAL_ENV=prod
EnvironmentFile=/root/.config/structural-isomorphism/phase-auth.env
ExecStart=/root/Projects/structural-isomorphism-v4/.venv/bin/uvicorn v4.product.d1_phase_detector.api.main:app --host 127.0.0.1 --port 8200 --no-access-log
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
''',
    'phase-detector-web.service': '''[Unit]
Description=Structural Phase Web
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/root/Projects/structural-isomorphism-v4/web/phase-detector
Environment=NODE_ENV=production
Environment=PATH=/opt/structural-tools/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/structural-tools/bin/node /root/Projects/structural-isomorphism-v4/web/phase-detector/node_modules/next/dist/bin/next start -p 3210 --hostname 127.0.0.1
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
''',
}

def trusted(path, *, missing=False):
    path = Path(path)
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if missing:
                return False
            raise SystemExit(f'missing prerequisite: {component}')
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise SystemExit(f'untrusted bootstrap path: {component}')
    return True

def prerequisites():
    trusted(REPO / '.git')
    for name in ('python3.11', 'node', 'pnpm'):
        tool = TOOLS / name
        trusted(tool)
        if not tool.is_file() or not os.access(tool, os.X_OK):
            raise SystemExit(f'non-executable tool: {tool}')
    abi = subprocess.check_output([str(TOOLS / 'python3.11'), '-I', '-c',
                                  'import sys; print(sys.implementation.cache_tag)'], text=True).strip()
    if abi != 'cpython-311':
        raise SystemExit('bootstrap requires Python 3.11')
    node = subprocess.check_output([str(TOOLS / 'node'), '--version'], text=True).strip()
    if not node.startswith('v22.'):
        raise SystemExit('bootstrap requires Node 22')
    subprocess.run([str(TOOLS / 'pnpm'), '--version'], check=True,
                   env={**os.environ, 'PATH': f'{TOOLS}:/usr/bin:/bin'})

def main(mode):
    if os.geteuid() != 0:
        raise SystemExit('bootstrap requires root')
    prerequisites()
    # Check all pre-existing state before writing anything. Existing units are
    # operator-owned and must never be silently replaced by this first installer.
    plans = [(Path('/etc/systemd/system') / name, body) for name, body in UNITS.items()]
    for path in DIRS + [REPO / '.venv']:
        if trusted(path, missing=True) and not path.is_dir():
            raise SystemExit(f'expected directory: {path}')
    for path, body in plans:
        if trusted(path, missing=True) and (not path.is_file() or path.read_text() != body):
            raise SystemExit(f'existing unit differs: {path}')
    if mode == '--check':
        for path in DIRS + [REPO / '.venv']:
            trusted(path)
        trusted(REPO / '.venv/bin/python')
        for path in (TARGET / 'web/backend/.env',
                     Path('/root/.config/structural-isomorphism/beta-auth.env'),
                     Path('/root/.config/structural-isomorphism/phase-auth.env')):
            trusted(path)
            if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise SystemExit(f'private configuration must be a regular 0600 file: {path}')
        # Certificates use Certbot's root-owned symlinks into archive/. Verify
        # their resolved identities; do not read keys or fabricate certificates.
        for domain in ('beta.structural.bytedance.city', 'phase.bytedance.city'):
            for name in ('fullchain.pem', 'privkey.pem'):
                trusted(Path(f'/etc/letsencrypt/live/{domain}/{name}').resolve(strict=True))
        for name in ('manifest.json', 'kb-expanded.jsonl', 'kb_v2_embeddings.npy', 'structural-v2'):
            trusted((Path('/root/structural-artifacts/current') / name).resolve(strict=True))
        for path, _ in plans:
            trusted(path)
        print('bootstrap structural prerequisites verified; secrets, TLS, artifacts and live deployment require separate checks')
        return
    for path in DIRS:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (REPO / '.venv').exists():
        subprocess.run([str(TOOLS / 'python3.11'), '-I', '-m', 'venv', '--copies', str(REPO / '.venv')], check=True)
    for path, body in plans:
        if not path.exists():
            with path.open('x') as handle:
                handle.write(body)
            path.chmod(0o644)
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
    print('bootstrap prepared inactive units; no auth configuration, TLS, data or running services were supplied')

if __name__ == '__main__':
    main(sys.argv[1])
PY
