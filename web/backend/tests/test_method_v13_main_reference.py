"""Main's current paths must reconstruct the exact, offline historical closure."""
import hashlib
import json
from pathlib import Path

import pytest

from web.backend.tests.method_v13_reference import reconstruct


@pytest.mark.parametrize('mode',['native','fixture'])
def test_current_main_reconstructs_original13_without_git(tmp_path,mode):
    root=Path(__file__).resolve().parents[3]
    reference='web/backend/tests/reference/method_v13/'
    manifest=json.loads((root/reference/'manifest.json').read_text())['cases'][mode]['files']
    current=tmp_path/'shallow-source'
    # Only this tracked closure and its two manifests, no Git/history/DB/venv.
    for relative in (*manifest,reference+'manifest.json',reference+'deltas.json'):
        source=root/relative
        assert not source.is_symlink()
        destination=current/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(source.read_bytes())
    assert not (current/'.git').exists()
    package,_=reconstruct(current,tmp_path/'original13',mode)
    actual={path.relative_to(package).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in package.rglob('*.py')}
    assert actual=={name:entry['sha256'] for name,entry in manifest.items()}
    assert not (package/'.git').exists()
    assert all(not path.is_symlink() for path in package.rglob('*'))
