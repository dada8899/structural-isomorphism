"""CPython 3.11 Source-only spawn with per-GET, explicitly owned tracker.

The spawn payload and FD reductions are standard multiprocessing. Only exec,
stdio and tracker ownership differ: neither child inherits Main's environment.
This is not a sandbox against malicious code running as the same operating UID.
"""
import io
import os
import signal
import socket
import subprocess
import sys
from multiprocessing import context, reduction, spawn
from multiprocessing.popen_spawn_posix import Popen as SpawnPopen


class SourceCleanupUncertain(OSError):
    pass


_UNCERTAIN = []


def require_supported():
    if (sys.implementation.name != 'cpython' or sys.version_info[:3] != (3, 11, 15)
            or os.name != 'posix' or getattr(sys, 'frozen', False)
            or not getattr(reduction, 'HAVE_SEND_HANDLE', False) or not hasattr(socket, 'SCM_RIGHTS')
            or not all(hasattr(signal, name) for name in ('SIGALRM', 'ITIMER_REAL', 'setitimer', 'pthread_sigmask'))):
        raise RuntimeError('Source safe spawn unavailable')


def _exec(command, descriptors):
    # No inherited HOME/PATH/PYTHONPATH/TMPDIR, credentials or application config.
    command = [sys.executable, '-I', '-B', *command[1:]]
    return subprocess.Popen(command, executable=sys.executable,
        env={'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'},
        pass_fds=tuple(sorted(set(descriptors))), close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class _Tracker:
    def __init__(self):
        self.fd = None
        self.process = None
        self._owned_fds = []
        read, write = os.pipe()
        self._owned_fds.extend((read, write))
        try:
            command = [sys.executable, '-I', '-B', '-c',
                'from multiprocessing.resource_tracker import main;main(%d)' % read]
            self.process = _exec(command, (read,))
            self.fd = write
            self._close_fd(read)
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:
                primary.add_note('Source tracker cleanup uncertain: ' + type(cleanup).__name__)
            raise

    def _close_fd(self, fd):
        os.close(fd)
        self._owned_fds.remove(fd)
        if self.fd == fd:
            self.fd = None

    def close(self):
        errors = []
        for fd in tuple(self._owned_fds):
            try:
                self._close_fd(fd)
            except BaseException as error:
                errors.append(error)
        if self.process is not None:
            try:
                try:
                    self.process.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=.25)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=.25)
            except BaseException as error:
                errors.append(error)
            else:
                self.process = None
        if errors:
            _UNCERTAIN.append(self)
            raise SourceCleanupUncertain('Source tracker retirement uncertain') from errors[0]


class _SourcePopen(SpawnPopen):
    def _launch(self, process_obj):
        self.sender = None
        self.tracker = None
        self.pid = None
        self.sentinel = None
        self._owned_fds = []
        try:
            self.tracker = _Tracker()
            tracker_fd = self.tracker.fd
            self._fds.append(tracker_fd)
            preparation = spawn.get_preparation_data(process_obj._name)
            # The target is a fixed importable Source module, never an arbitrary
            # Main script re-execution (which could load application secrets).
            preparation.pop('init_main_from_name', None)
            preparation.pop('init_main_from_path', None)
            payload = io.BytesIO()
            context.set_spawning_popen(self)
            try:
                reduction.dump(preparation, payload)
                reduction.dump(process_obj, payload)
            finally:
                context.set_spawning_popen(None)
            parent_read, child_write = os.pipe()
            self._owned_fds.extend((parent_read, child_write))
            child_read, parent_write = os.pipe()
            self._owned_fds.extend((child_read, parent_write))
            command = spawn.get_command_line(tracker_fd=tracker_fd, pipe_handle=child_read)
            self.sender = _exec(command, (*self._fds, child_read, child_write))
            self.pid, self.sentinel = self.sender.pid, parent_read
            # Standard spawn uses a fully serialized, bounded-by-input payload.
            with open(parent_write, 'wb', closefd=False) as output:
                output.write(payload.getbuffer())
            self._close_fd(child_read)
            self._close_fd(child_write)
            self._close_fd(parent_write)
        except BaseException as primary:
            try:
                self.retire()
            except BaseException as cleanup:
                primary.add_note('Source spawn cleanup uncertain: ' + type(cleanup).__name__)
            raise

    def _close_fd(self, fd):
        os.close(fd)
        self._owned_fds.remove(fd)

    def poll(self, flag=os.WNOHANG):
        if self.sender is None:
            return self.returncode
        if flag == 0:
            self.returncode = self.sender.wait()
        else:
            self.returncode = self.sender.poll()
        return self.returncode

    def wait(self, timeout=None):
        if self.sender is None:
            return self.returncode
        try:
            self.returncode = self.sender.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        return self.returncode

    def retire(self):
        errors = []
        if self.sender is not None:
            try:
                if self.sender.poll() is None:
                    self.sender.terminate()
                try:
                    self.sender.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    self.sender.kill()
                    self.sender.wait(timeout=.25)
                self.returncode = self.sender.returncode
            except BaseException as error:
                errors.append(error)
        for fd in tuple(self._owned_fds):
            try:
                self._close_fd(fd)
            except BaseException as error:
                errors.append(error)
        if self.tracker is not None:
            try:
                self.tracker.close()
            except BaseException as error:
                errors.append(error)
        if errors:
            _UNCERTAIN.append(self)
            raise SourceCleanupUncertain('Source spawn retirement uncertain') from errors[0]

    def close(self):
        self.retire()


class SourceSpawnProcess(context.SpawnProcess):
    """Private transport-owned Process; no callable/environment install port."""
    def __init__(self, arguments):
        from .source_policy import _child, _network_get
        if type(arguments) is not tuple or len(arguments) != 6:
            raise TypeError('fixed Source sender arguments required')
        if arguments[2] is _network_get:
            # Live never accepts a caller target or a filename-only substitute.
            import types
            from pathlib import Path
            path = Path(__file__).with_name('source_policy.py')
            definitions = compile(path.read_bytes(), str(path), 'exec', dont_inherit=True)
            for function, name in ((_child, '_child'), (_network_get, '_network_get')):
                codes = [code for code in definitions.co_consts if isinstance(code, types.CodeType) and code.co_name == name]
                if len(codes) != 1 or function.__code__ != codes[0]:
                    raise PermissionError('fixed live Source sender required')
        super().__init__(target=_child, args=arguments, daemon=True)

    @staticmethod
    def _Popen(process_obj):
        require_supported()
        return _SourcePopen(process_obj)

    def close(self):
        if self._popen is not None:
            self._popen.retire()
        super().close()


def source_process(arguments):
    require_supported()
    return SourceSpawnProcess(arguments)
