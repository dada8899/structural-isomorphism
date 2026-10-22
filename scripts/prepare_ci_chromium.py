"""One disposable Ubuntu CI installation; never a local setup or a perf grade.

Playwright's nested sudo does not explicitly forward APT_CONFIG. A root
controller therefore leases the existing Ubuntu source inode, changes only
its approved mirror URI, runs the unchanged SDK command as the original user,
then restores and verifies the inode before admitting the next workflow step.
The 100-second deadline includes termination and restoration. Kernel/FS stalls
cannot be promised a hard cleanup; an unproved cleanup always fails closed.
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import pwd
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

SOURCE = Path('/etc/apt/sources.list.d/ubuntu.sources')
KEYRING = Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg')
COMMAND = ('-m', 'playwright', 'install', '--with-deps', 'chromium')
TOTAL_SECONDS = 100


class Refused(RuntimeError):
    pass


class CleanupUnknown(Refused):
    def __init__(self, message='ci_chromium_cleanup_unknown', recovery=None):
        super().__init__(message)
        self.recovery = recovery


def require(condition):
    if not condition:
        raise Refused('ci_chromium_setup_refused')


def mirror_source(raw: bytes) -> bytes:
    """Accept only the fixed Noble deb822 fields; preserve all non-URI bytes."""
    require(type(raw) is bytes and 0 < len(raw) <= 16384)
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise Refused('ci_chromium_setup_refused') from None
    require('\r' not in text and '\x00' not in text)
    records, fields, replacements = [], {}, []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines + ['\n']):
        if not line.strip():
            if fields:
                records.append(fields)
                fields = {}
            continue
        if line.startswith('#'):
            continue
        require(not line[0].isspace() and ':' in line)
        name, value = line.rstrip('\n').split(':', 1)
        require(name in ('Types', 'URIs', 'Suites', 'Components', 'Signed-By'))
        require(name not in fields and value.startswith(' '))
        fields[name] = value.split()
        if name == 'URIs':
            require(len(fields[name]) == 1)
            uri = fields[name][0]
            require(uri in ('http://azure.archive.ubuntu.com/ubuntu',
                            'http://azure.archive.ubuntu.com/ubuntu/'))
            mapped = 'https://archive.ubuntu.com/ubuntu' + ('/' if uri.endswith('/') else '')
            replacements.append((index, line.replace(uri, mapped, 1)))
    require(len(records) in (1, 2))
    suites = []
    for item in records:
        require(set(item) == {'Types', 'URIs', 'Suites', 'Components', 'Signed-By'})
        require(item['Types'] == ['deb'])
        require(item['Signed-By'] == [str(KEYRING)])
        require(len(item['Components']) == 4 and set(item['Components']) == {'main', 'restricted', 'universe', 'multiverse'})
        require(item['Suites'] in (['noble', 'noble-updates', 'noble-backports', 'noble-security'],
                                   ['noble', 'noble-updates', 'noble-backports'], ['noble-security']))
        suites.extend(item['Suites'])
    require(len(suites) == 4 and set(suites) == {'noble', 'noble-updates', 'noble-backports', 'noble-security'})
    require(len(replacements) == len(records))
    for index, mapped in replacements:
        lines[index] = mapped
    return ''.join(lines).encode('utf-8')


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink)


def checked_read(fd, cap):
    os.lseek(fd, 0, os.SEEK_SET)
    value = os.read(fd, cap + 1)
    require(len(value) <= cap)
    return value


class SourceLease:
    def __init__(self, path, backup, expected_uid=0):
        self.path, self.fd, self.changed = path, None, False
        try:
            require(path.is_absolute() and path == path.resolve())
            self.fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(self.fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == expected_uid and stat.S_IMODE(info.st_mode) == 0o644 and info.st_nlink == 1)
            self.original_identity = identity(info)
            self.original = checked_read(self.fd, 16384)
            self.mapped = mirror_source(self.original)
            require(identity(path.lstat()) == self.original_identity)
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                self._write(fd, self.original)
            finally:
                os.close(fd)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _write(fd, data):
        at = 0
        while at < len(data):
            count = os.pwrite(fd, data[at:], at)
            require(count > 0)
            at += count
        os.ftruncate(fd, len(data))
        os.fsync(fd)

    def _verify(self, value):
        require(identity(os.fstat(self.fd)) == self.original_identity)
        require(identity(self.path.lstat()) == self.original_identity)
        require(checked_read(self.fd, 16384) == value)

    def apply(self):
        self._verify(self.original)
        self.changed = True  # Also recover a partial write, rather than claiming no change.
        self._write(self.fd, self.mapped)
        self._verify(self.mapped)

    def restore(self):
        try:
            if not self.changed:
                self._verify(self.original)
                return
            require(identity(os.fstat(self.fd)) == self.original_identity)
            require(identity(self.path.lstat()) == self.original_identity)
            # Do not overwrite a concurrent writer or an ambiguous partial write.
            require(checked_read(self.fd, 16384) in (self.original, self.mapped))
            self._write(self.fd, self.original)
            self._verify(self.original)
            self.changed = False
        except BaseException:
            raise CleanupUnknown('ci_chromium_cleanup_unknown') from None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def proc_rows():
    """Kernel PID/parent/start-time metadata only, never process arguments."""
    result = {}
    entries = list(Path('/proc').iterdir())
    require(len(entries) <= 32768)
    for path in entries:
        if not path.name.isdecimal():
            continue
        try:
            fields = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
        except FileNotFoundError:
            continue
        require(len(fields) >= 20)
        result[int(path.name)] = (int(fields[1]), int(fields[19]))
    return result


def descendants(rows, parent):
    result = set()
    for _ in range(len(rows) + 1):
        found = {pid for pid, (ppid, _) in rows.items() if ppid == parent or ppid in result}
        if found == result:
            return {pid: rows[pid] for pid in result}
        result = found
    raise CleanupUnknown('ci_chromium_cleanup_unknown')


def signal_children(number):
    require(os.geteuid() == 0)
    for pid, proof in descendants(proc_rows(), os.getpid()).items():
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            continue
        try:
            if proc_rows().get(pid) == proof:
                signal.pidfd_send_signal(fd, number)
        except ProcessLookupError:
            pass
        finally:
            os.close(fd)


def finish_children(process, deadline):
    """Only the privileged subreaper signals/reaps root sudo descendants."""
    term_until = min(time.monotonic() + 2, deadline - 8)
    while time.monotonic() < deadline - 5:
        signal_children(signal.SIGTERM if time.monotonic() < term_until else signal.SIGKILL)
        if process is None or process.poll() is not None:
            no_kernel_children = False
            while True:
                try:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    no_kernel_children = True
                    break
                if not pid:
                    break
            if no_kernel_children and not descendants(proc_rows(), os.getpid()):
                return
        time.sleep(min(0.02, max(0, deadline - 5 - time.monotonic())))
    raise CleanupUnknown('ci_chromium_cleanup_unknown')


def sdk_profile():
    require(sys.version_info[:2] == (3, 11))
    require(importlib.metadata.version('playwright') == '1.59.0')
    dist = importlib.metadata.distribution('playwright')
    registry = Path(dist.locate_file('playwright/driver/package/browsers.json'))
    rows = json.loads(registry.read_text())['browsers']
    for name in ('chromium', 'chromium-headless-shell'):
        entry = next(row for row in rows if row['name'] == name)
        require(entry['revision'] == '1217' and entry['browserVersion'] == '147.0.7727.15')


def child_environment(python, cache, temporary):
    return {'PATH': str(Path(python).parent) + ':/usr/local/bin:/usr/bin:/bin',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'CI': 'true',
            'PLAYWRIGHT_BROWSERS_PATH': str(cache), 'TMPDIR': str(temporary)}


def install_with_lease(lease, request, account, deadline, stopped):
    process, success, launch_attempted = None, False, False
    try:
        require(not stopped[0] and time.monotonic() < deadline - 12)
        lease.apply()
        launch_attempted = True
        process = subprocess.Popen([sys.executable, '-I', '-B', *COMMAND],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=child_environment(sys.executable, request['cache'], request['temporary']),
            start_new_session=True, user=request['uid'], group=request['gid'],
            extra_groups=os.getgrouplist(account.pw_name, request['gid']))
        while process.poll() is None and time.monotonic() < deadline - 12 and not stopped[0]:
            if select.select([sys.stdin], [], [], 0.02)[0]:
                stopped[0] = True
        success = process.poll() == 0 and not stopped[0] and time.monotonic() < deadline - 12
    except Exception:
        success = False
    finally:
        # A failed retirement must not be followed by a false restoration claim.
        if launch_attempted:
            finish_children(process, deadline)
        lease.restore()
        require(time.monotonic() < deadline)
    return {'status': 'ready' if success else 'failed',
            'children_closed': True, 'source_restored': True}


def root_worker(request):
    require(os.geteuid() == 0)
    uid, gid = int(os.environ.get('SUDO_UID', '0')), int(os.environ.get('SUDO_GID', '0'))
    os.environ.clear()
    require(set(request) == {'uid', 'gid', 'python', 'cache', 'temporary', 'deadline'})
    require(type(request['uid']) is int and request['uid'] == uid > 0 and request['gid'] == gid)
    account = pwd.getpwuid(uid)
    require(account.pw_gid == gid and request['python'] == sys.executable)
    require(request['cache'] == str(Path(account.pw_dir) / '.cache/ms-playwright'))
    temporary = Path(request['temporary'])
    info = temporary.lstat()
    require(temporary.is_absolute() and temporary == temporary.resolve() and stat.S_ISDIR(info.st_mode)
            and info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700)
    deadline = request['deadline']
    require(type(deadline) is float and math.isfinite(deadline) and 20 < deadline - time.monotonic() <= TOTAL_SECONDS)
    sdk_profile()
    # Root-only subreaper ownership survives sudo's own process-group choices.
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'))
    require(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0)
    probe = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(probe, 0)
    finally:
        os.close(probe)
    require(KEYRING == KEYRING.resolve())
    keyfd = os.open(KEYRING, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        keyinfo = os.fstat(keyfd)
        require(stat.S_ISREG(keyinfo.st_mode) and keyinfo.st_uid == 0 and keyinfo.st_nlink == 1 and stat.S_IMODE(keyinfo.st_mode) == 0o644)
        key_identity = identity(keyinfo)
        key_digest = hashlib.sha256(checked_read(keyfd, 1024 * 1024)).digest()
        recovery = Path(tempfile.mkdtemp(prefix='structure-ci-chromium-', dir='/tmp'))
        lease, result = None, None
        stopped = [False]
        for number in (signal.SIGTERM, signal.SIGINT):
            signal.signal(number, lambda *_: stopped.__setitem__(0, True))
        try:
            try:
                lease = SourceLease(SOURCE, recovery / 'ubuntu.sources.backup')
                result = install_with_lease(lease, request, account, deadline, stopped)
            finally:
                if lease is not None:
                    lease.close()
                require(identity(os.fstat(keyfd)) == key_identity and identity(KEYRING.lstat()) == key_identity)
                require(hashlib.sha256(checked_read(keyfd, 1024 * 1024)).digest() == key_digest)
                require(time.monotonic() < deadline)
                if result is not None and result['children_closed'] and result['source_restored']:
                    backup = recovery / 'ubuntu.sources.backup'
                    if backup.exists():
                        backup.unlink()
                    recovery.rmdir()
        except BaseException:
            raise CleanupUnknown(recovery=recovery.name) from None
        require(result is not None)
        require(time.monotonic() < deadline)
        return result
    finally:
        os.close(keyfd)


def host_guard():
    require(sys.platform == 'linux' and os.uname().machine == 'x86_64' and os.getuid() == os.geteuid() > 0)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted')
    require(os.environ.get('RUNNER_OS') == 'Linux' and os.environ.get('RUNNER_ARCH') == 'X64')
    release = Path('/etc/os-release').read_text()
    require('ID=ubuntu\n' in release and 'VERSION_ID="24.04"\n' in release)
    sdk_profile()


def prepare():
    deadline = time.monotonic() + TOTAL_SECONDS
    host_guard()
    directory = Path(os.environ['RUNNER_TEMP'])
    require(directory.is_absolute() and directory == directory.resolve() and directory.stat().st_uid == os.getuid())
    temporary = Path(tempfile.mkdtemp(prefix='structure-ci-chromium-user-', dir=directory))
    temporary_identity = identity(temporary.lstat())
    request = {'uid': os.getuid(), 'gid': os.getgid(), 'python': sys.executable,
               'cache': str(Path(pwd.getpwuid(os.getuid()).pw_dir) / '.cache/ms-playwright'),
               'temporary': str(temporary), 'deadline': deadline}
    try:
        process = subprocess.Popen(['/usr/bin/sudo', '-n', '--', sys.executable, '-I', '-B',
                                    str(Path(__file__).resolve()), '--root-worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    except BaseException:
        # The caller cannot infer whether sudo forked before the constructor
        # failed. Retain its task directory and never report a clean non-start.
        raise CleanupUnknown() from None
    try:
        process.stdin.write((json.dumps(request) + '\n').encode())
        process.stdin.flush()  # Keep the control pipe open during installation.
        try:
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
        except BaseException:
            process.stdin.close()  # The privileged controller owns termination.
            raise CleanupUnknown('ci_chromium_cleanup_unknown') from None
        output = process.stdout.read(8193)
        require(len(output) <= 8192 and time.monotonic() < deadline)
        result = json.loads(output)
        require(type(result) is dict and set(result) == {'status', 'children_closed', 'source_restored'})
        require((code, result['status']) in ((0, 'ready'), (1, 'failed')))
        require(result['children_closed'] is True and result['source_restored'] is True)
        require(identity(temporary.lstat()) == temporary_identity and temporary == temporary.resolve())
        require(shutil.rmtree.avoids_symlink_attacks and time.monotonic() < deadline)
        shutil.rmtree(temporary)
        require(time.monotonic() < deadline)
        return result
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
        # Failure/unknown retains this exact task directory for recovery. It is
        # removed only after the root controller has proved retirement/restoration.


def main():
    try:
        if sys.argv[1:] == ['--root-worker']:
            raw = sys.stdin.buffer.readline(4097)
            require(len(raw) <= 4096 and raw.endswith(b'\n'))
            result = root_worker(json.loads(raw))
        else:
            require(not sys.argv[1:])
            result = prepare()
    except BaseException as error:
        result = {'status': 'cleanup_unknown', 'children_closed': False, 'source_restored': False}
        if type(error) is CleanupUnknown and error.recovery is not None:
            result['recovery_ref'] = error.recovery
        print(json.dumps(result))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
