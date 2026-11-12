"""Stdlib-only, synthetic Source kernel controls on the actual interpreter.

This is not formal Auth/Main/Source admission. Four unmodified current modules
are loaded from an owned temporary package, with hashes checked in both parent
and sender. No installed application/development packages are required.
"""
import argparse
from contextlib import contextmanager
import fcntl
import functools
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import threading
import time

sys.dont_write_bytecode = True
MODULES = ('source_spawn', 'source_policy', 'authorization', 'errors')
SENSITIVE = ('JWT_SECRET', 'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY', 'SMTP_PASSWORD')


def _source_facts(package):
    facts = {}
    for name in MODULES:
        module = importlib.import_module('source_kernel_fixture.' + name)
        path = Path(module.__file__).resolve()
        if path.parent != Path(package).resolve():
            raise AssertionError('mixed Source kernel import')
        facts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return facts


def observe_worker(package, forbidden, target):
    import multiprocessing
    parent = multiprocessing.parent_process()
    inherited = []
    for fd in range(3, 256):
        try:
            info = os.fstat(fd)
        except OSError:
            continue
        if (info.st_dev, info.st_ino) == forbidden:
            inherited.append(fd)
    raw = json.dumps({'env_names': sorted(os.environ), 'inherited_business_fds': inherited,
        'parent_alive': parent.is_alive(), 'parent_pid': parent.pid, 'actual_parent_pid': os.getppid(),
        'timer_armed': 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= 12,
        'stdio_devnull': [stat.S_ISCHR(os.fstat(fd).st_mode)
            and os.fstat(fd).st_rdev == os.stat(os.devnull).st_rdev for fd in (0, 1, 2)],
        'loaded_hashes': _source_facts(package)}).encode()
    return 200, 'application/json', raw, raw


def local_get(port, target):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
    try:
        connection.request('GET', '/owned-source')
        response = connection.getresponse()
        raw = response.read(64)
        return response.status, 'text/plain', raw, raw
    finally:
        connection.close()


def fail_worker(target):
    raise OSError('synthetic Source body failure')


def blocked_worker(ready, target):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(ready).write_text('owned sender entered')
    time.sleep(10)
    return 200, 'text/plain', b'late', b'late'


@contextmanager
def native_owner(auth, root):
    # Actual locked OFD and original capability class; synthetic kernel fixture,
    # never a substitute for registered-owner/grant/Source admission checks.
    fd = os.open(root / 'owner.lock', os.O_CREAT | os.O_RDWR, 0o600)
    lease = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        lease = auth.OwnerGateLease(fd, _factory=auth._LEASE_FACTORY)
        yield lease
    finally:
        if lease is not None:
            lease._deactivate()
        os.close(fd)


def run(source_root, owned_root):
    source_root, root = Path(source_root).resolve(), Path(owned_root).resolve()
    if root.exists() or any(name in os.environ for name in SENSITIVE):
        raise RuntimeError('new owned root and no signing environment required')
    root.mkdir(mode=0o700)
    package = root / 'source_kernel_fixture'
    package.mkdir(mode=0o700)
    (package / '__init__.py').write_text('')
    expected = {}
    for name in MODULES:
        source = source_root / 'web/backend/research' / (name + '.py')
        if source.is_symlink():
            raise RuntimeError('original Source module required')
        raw = source.read_bytes()
        expected[name] = hashlib.sha256(raw).hexdigest()
        (package / source.name).write_bytes(raw)
    sys.path.insert(0, str(root))
    records = []
    completed = False
    try:
        policy = importlib.import_module('source_kernel_fixture.source_policy')
        spawn = importlib.import_module('source_kernel_fixture.source_spawn')
        auth = importlib.import_module('source_kernel_fixture.authorization')
        assert _source_facts(package) == expected
        spawn.require_supported()
        original_exec = spawn._exec
        def observed_exec(command, descriptors):
            process = original_exec(command, descriptors)
            records.append(process)
            return process
        spawn._exec = observed_exec
        for name in SENSITIVE:
            os.environ[name] = 'synthetic-source-spawn-sentinel'
        from multiprocessing import resource_tracker
        default_tracker = (resource_tracker._resource_tracker._pid, resource_tracker._resource_tracker._fd)
        def get(worker, *, authorized=lambda: True, wall=12):
            with native_owner(auth, root) as owner:
                return policy.PinnedPublicTransport(_worker=worker, wall_seconds=wall).get(
                    policy.article_target('10.1371/journal.pone.0015032'),
                    still_authorized=authorized, owner_lease=owner)
        witness = os.open(root / 'business-file', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.set_inheritable(witness, True)
            info = os.fstat(witness)
            facts = json.loads(get(functools.partial(observe_worker, str(package), (info.st_dev, info.st_ino)))[2])
        finally:
            os.close(witness)
        assert facts['loaded_hashes'] == expected and facts['inherited_business_fds'] == []
        assert not set(facts['env_names']) & set(SENSITIVE)
        platform_names = {'__CF_USER_TEXT_ENCODING'} if sys.platform == 'darwin' else set()
        assert set(facts['env_names']) <= {'LC_CTYPE', 'PYTHONDONTWRITEBYTECODE', 'PYTHONUTF8'} | platform_names
        assert facts['parent_alive'] and facts['parent_pid'] == facts['actual_parent_pid'] == os.getpid()
        assert facts['timer_armed'] and facts['stdio_devnull'] == [True, True, True]
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                calls.append(self.path)
                self.send_response(200)
                self.send_header('Content-Length', '5')
                self.end_headers()
                self.wfile.write(b'owned')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            value = get(functools.partial(local_get, server.server_port))
            assert value[2] == value[3] == b'owned' and calls == ['/owned-source']
        finally:
            server.shutdown();server.server_close();thread.join(2)
            assert not thread.is_alive()
        ready = root / 'ready'
        try:
            get(functools.partial(blocked_worker, str(ready)), authorized=lambda: not ready.exists(), wall=2)
        except PermissionError:
            pass
        else:
            raise AssertionError('stop did not revoke sender')
        assert records[-1].returncode == -signal.SIGKILL
        fault = []
        original_close = spawn._Tracker._close_fd
        def close_after(self, fd):
            writer = fd == self.fd
            original_close(self, fd)
            if writer and not fault:
                fault.append(fd)
                raise OSError('synthetic post-close failure')
        spawn._Tracker._close_fd = close_after
        try:
            get(fail_worker)
        except policy.SourceFailure as primary:
            assert primary._source_cleanup_uncertainty == ('Source transport retirement uncertain',)
        else:
            raise AssertionError('primary failure was not preserved')
        finally:
            spawn._Tracker._close_fd = original_close
        assert fault and spawn._UNCERTAIN and all(process.poll() is not None for process in records)
        try:
            os.fstat(fault[0])
        except OSError:
            pass
        else:
            raise AssertionError('faulted descriptor remains open')
        # These intentionally uncertain test records are retired only after the
        # actual process/FD facts above, not by clearing an operational registry.
        spawn._UNCERTAIN.clear()
        assert (resource_tracker._resource_tracker._pid, resource_tracker._resource_tracker._fd) == default_tracker
        assert all(os.environ[name] == 'synthetic-source-spawn-sentinel' for name in SENSITIVE)
        completed = True
        return {'runtime': list(sys.version_info[:3]), 'platform': sys.platform, 'module_hashes': expected,
            'parent_alive': True, 'exec_env_sensitive_names': [], 'business_fd_inherited': False,
            'stdio_devnull': True, 'timer_armed_max12s': True, 'loopback_gets': len(calls),
            'source_modes': ['offline_probe'], 'actual_owned_processes_reaped': len(records),
            'stop_killed_sender': True, 'primary_preserved_with_cleanup_uncertain': True,
            'default_tracker_unchanged': True, 'formal_auth_or_Main_ready_claimed': False}
    finally:
        for name in SENSITIVE:
            os.environ.pop(name, None)
        sys.path.remove(str(root))
        for process in records:
            if process.poll() is None:
                process.kill();process.wait(timeout=2)
        if completed:
            shutil.rmtree(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root')
    parser.add_argument('owned_root')
    args = parser.parse_args()
    # Importable worker module: standard spawn does not replay this Main script.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    driver = importlib.import_module(Path(__file__).stem)
    print(json.dumps(driver.run(args.source_root, args.owned_root), sort_keys=True))
