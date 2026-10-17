"""Read-only inspection of synthetic private paths; not migration/admission proof."""
from pathlib import Path
import os
import stat
from types import SimpleNamespace

import pytest

from services import runtime_paths as runtime


@pytest.fixture
def layout(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    state, cache, logs = root / 'state', root / 'cache', root / 'state/logs'
    repo, public = root / 'repo', root / 'public'
    for path in (state, cache, logs, repo, public):path.mkdir(mode=0o700)
    monkeypatch.setattr(runtime, 'STATE_ROOT', state)
    monkeypatch.setattr(runtime, 'CACHE_ROOT', cache)
    monkeypatch.setattr(runtime, 'LOG_ROOT', logs)
    return {'state': state, 'cache': cache, 'logs': logs, 'repo': repo, 'public': public}


def inspect(layout):
    return runtime.RuntimePaths.inspect_formal(repository=layout['repo'], public_roots=[layout['public']])


def test_inspection_keeps_two_distinct_databases_and_creates_nothing(layout):
    before = set(layout['state'].rglob('*')) | set(layout['cache'].rglob('*'))
    paths = inspect(layout)
    assert paths.file('auth') == layout['state'] / 'auth.sqlite3'
    assert paths.file('history') == layout['state'] / 'history.db'
    assert paths.file('auth') != paths.file('history')
    assert paths.file('sso') == layout['state'] / 'sso_replay.sqlite3'
    assert paths.file('mapping_cache') == layout['cache'] / 'mapping_cache.jsonl'
    assert paths.file('analysis_cache') == layout['cache'] / 'analysis_cache.jsonl'
    assert paths.file('server_log') == layout['logs'] / 'server.jsonl'
    assert paths.file('retrieval_log') == layout['logs'] / 'retrieval.jsonl'
    assert set(layout['state'].rglob('*')) | set(layout['cache'].rglob('*')) == before
    # Path resolution is explicitly not a successful consumer migration.
    with pytest.raises(runtime.FormalAdmissionError):runtime.require_formal_admission()
    with pytest.raises(runtime.RuntimePathError):paths.file('research-shadow-db')


@pytest.mark.parametrize('kind', ['favorites', 'newsletter', 'waitlist', 'checkout', 'billing', 'error', 'privacy_audit'])
def test_unconnected_asset_families_do_not_gain_an_invented_path(layout, kind):
    with pytest.raises(runtime.RuntimePathError):inspect(layout).file(kind)


@pytest.mark.parametrize('fault', ['missing', 'relative', 'traversal', 'file', 'symlink', 'ancestor-link',
                                   'wide-mode', 'wrong-uid', 'wrong-log-parent'])
def test_formal_roots_require_actual_private_existing_directories(layout, monkeypatch, fault):
    state = layout['state']
    if fault == 'missing':monkeypatch.setattr(runtime, 'CACHE_ROOT', layout['cache'] / 'not-created')
    elif fault == 'relative':monkeypatch.setattr(runtime, 'CACHE_ROOT', Path('relative-cache'))
    elif fault == 'traversal':monkeypatch.setattr(runtime, 'CACHE_ROOT', layout['cache'] / '../cache')
    elif fault == 'file':
        layout['cache'].rmdir()
        layout['cache'].write_text('not a directory')
    elif fault == 'symlink':
        link = state.parent / 'state-link'
        link.symlink_to(state, target_is_directory=True)
        monkeypatch.setattr(runtime, 'STATE_ROOT', link)
        monkeypatch.setattr(runtime, 'LOG_ROOT', link / 'logs')
    elif fault == 'ancestor-link':
        link = state.parent / 'parent-link'
        link.symlink_to(state.parent, target_is_directory=True)
        monkeypatch.setattr(runtime, 'CACHE_ROOT', link / 'cache')
    elif fault == 'wide-mode':state.chmod(0o750)
    elif fault == 'wrong-uid':
        uid = os.geteuid()
        monkeypatch.setattr(os, 'geteuid', lambda: uid + 1)
    else:monkeypatch.setattr(runtime, 'LOG_ROOT', layout['cache'])
    with pytest.raises(runtime.RuntimePathError):inspect(layout)
    assert not (layout['cache'] / 'not-created').exists()


@pytest.mark.parametrize('where', ['repo', 'public', 'repo-frontend', 'public-alias', 'peer-worktree'])
def test_private_storage_cannot_overlap_any_public_or_git_tree(layout, monkeypatch, where):
    if where == 'public-alias':
        # The actual externally mounted public path may itself be a symlink.
        link = layout['public'] / 'mount'
        link.symlink_to(layout['state'], target_is_directory=True)
        layout['public'] = link
    else:
        if where == 'peer-worktree':
            git = layout['repo'] / '.git'
            metadata = git / 'worktrees/peer'
            metadata.mkdir(parents=True)
            base = layout['state'].parent / 'peer-checkout'
            base.mkdir()
            (metadata / 'gitdir').write_text(str(base / '.git'))
        elif where == 'repo-frontend':base = layout['repo'] / 'web/frontend'
        else:base = layout[where]
        proposed = base / 'private'
        proposed.mkdir(mode=0o700, parents=True)
        (proposed / 'logs').mkdir(mode=0o700)
        monkeypatch.setattr(runtime, 'STATE_ROOT', proposed)
        monkeypatch.setattr(runtime, 'LOG_ROOT', proposed / 'logs')
    with pytest.raises(runtime.RuntimePathError):inspect(layout)


def test_repository_name_prefix_sibling_is_not_mistaken_for_a_checkout(layout, monkeypatch):
    state = layout['repo'].with_name('repo-private-sibling')
    state.mkdir(mode=0o700)
    (state / 'logs').mkdir(mode=0o700)
    monkeypatch.setattr(runtime, 'STATE_ROOT', state)
    monkeypatch.setattr(runtime, 'LOG_ROOT', state / 'logs')
    assert inspect(layout).file('auth') == state / 'auth.sqlite3'


@pytest.mark.parametrize('fault', ['mode', 'uid', 'symlink', 'hardlink', 'fifo', 'directory'])
def test_private_files_are_regular_single_link_600_and_owned(layout, monkeypatch, fault):
    paths = inspect(layout)
    target = layout['state'] / 'auth.sqlite3'
    target.write_bytes(b'synthetic-not-a-database')
    target.chmod(0o600)
    if fault == 'mode':target.chmod(0o644)
    elif fault == 'uid':
        original = os.stat
        def wrong_owner(path, *a, **k):
            if path == target.name and 'dir_fd' in k:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=os.geteuid() + 1, st_nlink=1)
            return original(path, *a, **k)
        monkeypatch.setattr(os, 'stat', wrong_owner)
    elif fault == 'hardlink':os.link(target, layout['state'] / 'alias')
    else:
        target.unlink()
        if fault == 'symlink':target.symlink_to(layout['public'] / 'unapproved')
        elif fault == 'fifo':os.mkfifo(target, 0o600)
        else:target.mkdir(mode=0o700)
    with pytest.raises(runtime.RuntimePathError):paths.file('auth')


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
@pytest.mark.parametrize('main_exists', [False, True])
def test_sqlite_sidecars_cannot_escape_private_file_boundary(layout, suffix, main_exists):
    paths = inspect(layout)
    target = layout['state'] / 'history.db'
    if main_exists:
        target.write_bytes(b'synthetic')
        target.chmod(0o600)
    side = target.with_name(target.name + suffix)
    side.write_bytes(b'synthetic-sidecar')
    side.chmod(0o644)
    with pytest.raises(runtime.RuntimePathError):paths.file('history')


def test_readonly_inspection_revalidates_path_after_directory_substitution(layout):
    paths = inspect(layout)
    layout['logs'].rmdir()
    layout['logs'].symlink_to(layout['public'], target_is_directory=True)
    with pytest.raises(runtime.RuntimePathError):paths.file('server_log')


def test_development_hook_preserves_default_without_inspecting_or_migrating(monkeypatch):
    def forbidden(*a, **k):raise AssertionError('development path performed IO')
    monkeypatch.setattr(runtime.RuntimePaths, 'inspect_formal', forbidden)
    previous = Path('../legacy/data/history.db')
    assert runtime.resolve_runtime_file('history', formal=False, development_path=previous,
        repository='/unused', public_roots=[]) == previous
