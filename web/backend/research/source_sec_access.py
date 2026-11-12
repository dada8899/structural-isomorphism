"""Optional, existing-only SEC resource owned by the actual Source lifetime.

Holding a flock or observing a pacing state never grants a request. A DOC flight
also requires the actual registered session, protected SENDING request, private
profile and original transport. Retirement is minted by its real finally only.
"""
from __future__ import annotations

import fcntl
import inspect
import math
import os
import stat
import threading
import time

_FACTORY = object()
_NAME = 'source-sec-access.lock'
_INTERVAL = 1.0


class _Cadence:
    """Pure timing state; contains neither native resources nor send authority."""
    __slots__ = ('next_due', 'flight', 'uncertain')

    def __init__(self):
        self.next_due, self.flight, self.uncertain = None, None, False

    def cleared(self, now):
        if self.next_due is not None or self.flight is not None or self.uncertain:
            raise RuntimeError('cleanup checkpoint already consumed')
        self.next_due = now + _INTERVAL

    def delay(self, now):
        if self.next_due is None or self.flight is not None or self.uncertain:
            raise PermissionError('SEC cadence is not clear')
        return max(0., self.next_due - now)

    def begin(self, now):
        if self.delay(now) != 0:
            raise PermissionError('SEC cadence is cooling down')
        self.flight = object()
        return self.flight

    def finished(self, token, now):
        # Pure mechanism only. The native finish_request port below never
        # accepts this token as evidence of actual transport retirement.
        if token is not self.flight or self.flight is None or self.uncertain:
            raise PermissionError('SEC cadence flight did not retire')
        self.flight, self.next_due = None, now + _INTERVAL

    def unknown(self, token):
        if token is not self.flight or self.flight is None:
            raise PermissionError('SEC cadence flight identity changed')
        self.uncertain = True


class _Governor:
    __slots__ = ('supervisor', 'binding', 'reference', 'context', 'pid', 'factory',
                 'fd', 'identity', 'state', 'reason', 'errors', 'cadence', 'retired', 'profile', 'flight')

    def __init__(self, supervisor, *, _factory=None):
        frame = inspect.currentframe().f_back
        if _factory is not _FACTORY or frame.f_globals is not globals() or frame.f_code is not attach.__code__:
            raise TypeError('canonical Source SEC attachment required')
        self.supervisor, self.binding = supervisor, supervisor._binding
        self.reference, self.context = self.binding.reference, self.binding.native_context
        self.pid, self.factory = os.getpid(), _factory
        self.fd = self.identity = None
        self.profile = None
        self.flight = None
        self.state, self.reason = 'UNBOUND', None
        self.errors, self.cadence, self.retired = [], _Cadence(), False

    def __repr__(self):
        return '<optional native Source SEC resource>'

    def __reduce__(self):
        raise TypeError('Source SEC resource cannot cross processes')


def _source():
    from . import source_supervisor
    return source_supervisor


def _identity(governor):
    source = _source()
    if type(governor) is not _Governor or governor.factory is not _FACTORY or governor.pid != os.getpid():
        raise RuntimeError('actual Source SEC resource required')
    supervisor, binding = governor.supervisor, governor.binding
    source._identity_handle(supervisor)
    source._binding_module(supervisor)
    source._same_store(supervisor, supervisor._service.store)
    if (getattr(supervisor, '_sec_access', None) is not governor or supervisor._binding is not binding
            or binding.reference != governor.reference or binding.native_context is not governor.context
            or binding.service is not supervisor._service):
        raise RuntimeError('Source SEC binding identity changed')
    from . import native_plan_supervisor as native
    native._scope_identity(governor.context, supervisor._service.store)
    return supervisor


def _parent(governor):
    binding = governor.binding
    if binding.roots != (binding.paths.STATE_ROOT, binding.paths.CACHE_ROOT, binding.paths.LOG_ROOT):
        raise RuntimeError('Source SEC private roots changed')
    witness = binding.witnesses[0]
    if (type(witness) is not binding.paths.PrivateAuthFile
            or witness.path != binding.roots[0] / 'auth.sqlite3'
            or witness.file_identity != governor.supervisor._identity):
        raise RuntimeError('Source SEC requires the original Auth witness')
    witness.check()  # Checks the named directory and original Auth inode.
    return witness.parent_fd


def _regular(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise RuntimeError('Source SEC lock metadata invalid')
    return info.st_dev, info.st_ino


def _held(governor):
    parent = _parent(governor)
    if governor.fd is None or governor.identity is None:
        raise RuntimeError('Source SEC lock not held')
    if (_regular(os.fstat(governor.fd)) != governor.identity
            or _regular(os.stat(_NAME, dir_fd=parent, follow_symlinks=False)) != governor.identity):
        raise RuntimeError('Source SEC lock pathname changed')


def _uncertain(governor, error):
    governor.errors.append(error)
    governor.state, governor.reason = 'CLEANUP_UNCERTAIN', 'CLOSE_UNCERTAIN'


def _close_owned(governor):
    # Retain the actual descriptor number on an indeterminate close. Never
    # retry it: an interrupted close could have released and reused that number.
    if governor.fd is not None:
        try:
            os.close(governor.fd)
        except BaseException as error:
            _uncertain(governor, error)
            return False
        governor.fd = None
    return True


def attach(supervisor):
    """Only canonical start, after registration, before native Thread.start."""
    source = _source()
    frame = inspect.currentframe().f_back
    if frame.f_globals is not vars(source) or frame.f_code is not source.start.__code__:
        raise TypeError('canonical Source start required')
    source._check(supervisor, published=True)
    from . import native_plan_supervisor as native
    native.require_startup_scope(supervisor._binding.native_context, supervisor._service.store)
    governor = _Governor(supervisor, _factory=_FACTORY)
    supervisor._sec_access = governor  # Publish the partial handle before open.
    try:
        _identity(governor)
        parent = _parent(governor)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        governor.fd = os.open(_NAME, flags, dir_fd=parent)
        governor.identity = _regular(os.fstat(governor.fd))
        _held(governor)
        fcntl.flock(governor.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _held(governor)
        governor.state = 'HELD_CLEANUP'
        from .source_document_access import attach_access
        attach_access(governor)
    except (OSError, RuntimeError) as error:
        # Optional absence/invalid configuration/contended flock closes only
        # our own FD. A failed close remains an owned uncertain resource.
        governor.reason = type(error).__name__
        if _close_owned(governor):
            governor.state = 'UNBOUND'
    except BaseException as error:
        _uncertain(governor, error)
    return governor


def cleanup_completed(governor):
    """The real worker's completed all-principal debt scan is the only input."""
    supervisor = _identity(governor)
    source = _source()
    frame = inspect.currentframe().f_back
    if (frame.f_globals is not vars(source) or frame.f_code is not source.SourceSupervisor._run_with_budget.__code__
            or threading.current_thread() is not supervisor._thread
            or supervisor._slot is not None or supervisor._lease is not None):
        raise RuntimeError('actual Source cleanup checkpoint required')
    # The earlier scan check can precede a real Main withdrawal. Only the
    # original check can establish sealed stopping provenance; an Event or
    # retired flag alone must never turn a resource/integrity failure normal.
    source._check(supervisor, published=True)
    if supervisor._state != 'STARTING' or supervisor._stop.is_set() or governor.retired:
        source._check(supervisor, published=True)
        raise RuntimeError('actual Source cleanup checkpoint required')
    if governor.state == 'UNBOUND':
        return
    if governor.state != 'HELD_CLEANUP':
        source._check(supervisor, published=True)
        raise RuntimeError('Source SEC cleanup unavailable')
    _held(governor)
    governor.cadence.cleared(time.monotonic())
    governor.state = 'COOLDOWN'


def wait_before_claim(governor):
    """Wait outside every Source/Owner/DB lock; stop uses the original event.

    This only rechecks a resource/cadence. DOC permission is still absent and
    must be checked by a future native DOC dispatcher after this returns.
    """
    supervisor = _identity(governor)
    if threading.current_thread() is not supervisor._thread:
        raise PermissionError('actual Source worker required')
    if supervisor._slot is not None or supervisor._lease is not None or supervisor._lock._is_owned():
        raise RuntimeError('SEC pacing must precede native slot birth')
    while True:
        _source()._check(supervisor, published=True)
        if governor.retired or governor.state not in ('COOLDOWN', 'RECHECK_REQUIRED'):
            raise PermissionError('Source SEC resource unavailable')
        _held(governor)
        delay = governor.cadence.delay(time.monotonic())
        if delay == 0:
            governor.state = 'RECHECK_REQUIRED'
            return
        supervisor._stop.wait(delay)


def begin_request(governor, actual_session, fixed_target):
    from .source_policy import PinnedPublicTransport
    from .source_document_access import session_supervisor
    from .source_document_raw import DocTarget,target_digest
    supervisor=_identity(governor);caller=inspect.currentframe().f_back
    transport=caller.f_locals.get('self')
    if (caller.f_code is not PinnedPublicTransport.get.__code__ or type(transport) is not PinnedPublicTransport
            or transport is not actual_session.transport or session_supervisor(actual_session) is not supervisor
            or type(fixed_target) is not DocTarget or governor.flight is not None):raise PermissionError('actual DOC transport request required')
    _source()._check(supervisor,published=True);_held(governor)
    if governor.retired or governor.errors or governor.profile is None:raise PermissionError('DOC access retired')
    governor.profile.check(network=True)
    witness=actual_session._doc_request
    if witness is None or not witness.issued:raise PermissionError('actual DOC SENDING required')
    if target_digest(fixed_target)!=witness.row['target_digest']:raise PermissionError('DOC SENDING target differs')
    with actual_session._transaction() as conn:witness.check(conn,network=True)
    deadline=caller.f_locals.get('doc_deadline')
    if type(deadline) is not float or not math.isfinite(deadline) or not 0<deadline-time.monotonic()<=12:raise PermissionError('original DOC deadline required')
    token=governor.cadence.begin(time.monotonic())
    flight=DocRequestFlight(governor,actual_session,transport,fixed_target,witness,token,deadline,_factory=_FACTORY)
    governor.flight=flight
    return flight


def finish_request(flight, actual_retirement):
    from .source_policy import PinnedPublicTransport,require_doc_retirement
    frame=inspect.currentframe().f_back
    if frame.f_code is not PinnedPublicTransport.get.__code__:raise PermissionError('actual DOC transport retirement required')
    flight.identity()
    require_doc_retirement(actual_retirement,flight)
    governor=flight.governor
    governor.cadence.finished(flight.token,actual_retirement.monotonic_at)
    governor.flight=None;flight.retirement=actual_retirement;flight.state='RETIRED'


def retire(governor):
    supervisor = _identity(governor)
    governor.retired = True
    supervisor._stop.set()
    if governor.state != 'CLEANUP_UNCERTAIN':
        governor.state = 'RETIRED'
    try:
        if supervisor._images != _source()._code_images():
            raise RuntimeError('Source SEC source image changed')
        if governor.fd is not None:
            _held(governor)
        if governor.profile is not None and governor.profile.state=='BOUND':
            governor.profile.check(network=False)
    except BaseException as error:
        _uncertain(governor, error)


def close(governor, original_deadline):
    supervisor = _identity(governor)
    if (type(original_deadline) not in (int, float) or not math.isfinite(original_deadline)
            or supervisor._deadline.get('absolute') != original_deadline):
        raise ValueError('original Main cleanup deadline required')
    if (not governor.retired or supervisor._thread.is_alive() or supervisor._slot is not None
            or supervisor._lease is not None or supervisor._session is not None or supervisor._guard is not None
            or governor.state == 'CLEANUP_UNCERTAIN' or governor.cadence.flight is not None
            or governor.cadence.uncertain):
        return False

    if governor.state == 'CLOSED':
        return True
    try:
        if time.monotonic() >= original_deadline:
            return False
        if governor.fd is not None:
            _held(governor)
        if governor.profile is not None and not governor.profile.close():return False
        if not _close_owned(governor):
            return False
        governor.state = 'CLOSED'
        return True
    except BaseException as error:
        _uncertain(governor, error)
        return False


_FLIGHTS = {}
_JOBS = {}


class DocRequestFlight:
    """Parent-only identity, tied to one actual request and owned transport."""
    __slots__=('governor','session','transport','target','witness','profile','token','deadline','wire','pid','thread',
        'epoch','state','process','popen','handed_off','retirement','outcome','_factory',
        'valid_from_epoch','expires_epoch','_profiles','_requests')
    def __new__(cls,*args,**kwargs):
        if cls is not DocRequestFlight or kwargs.get('_factory') is not _FACTORY:raise PermissionError('native DOC flight factory required')
        return object.__new__(cls)
    def __init__(self,governor,session,transport,target,witness,token,deadline,*,_factory=None):
        from .source_document_raw import DocWireTarget
        from .source_document_access import approved_references,_stamp,_PROFILES,_DOC_REQUESTS
        if inspect.currentframe().f_back.f_code is not begin_request.__code__:raise PermissionError('canonical DOC flight issuer required')
        profile=governor.profile;ref,rights=approved_references()
        self.governor,self.session,self.transport,self.target,self.witness,self.profile=governor,session,transport,target,witness,profile
        self.token,self.deadline,self.pid,self.thread,self.epoch=token,deadline,os.getpid(),threading.current_thread(),governor.supervisor._slot_epoch
        self.state='OPENING';self.process=self.popen=self.retirement=self.outcome=None;self.handed_off=False;self._factory=_factory
        self._profiles,self._requests=_PROFILES,_DOC_REQUESTS
        identity=profile._data['network_identity']
        self.valid_from_epoch,self.expires_epoch=_stamp(identity['valid_from']).timestamp(),_stamp(identity['expires_at']).timestamp()
        send_limit=min(deadline,time.monotonic()+max(0.,_stamp(identity['expires_at']).timestamp()-time.time()))
        self.wire=DocWireTarget(record_schema='DocWireTarget-v1',target=target,access_profile_ref=ref,rights_digest=rights,
            request_id=witness.row['id'],dispatch_id=witness.row['dispatch_id'],task_id=session.task_id,
            write_epoch=witness.row['write_epoch'],slot_epoch=self.epoch,attempted_at=witness.row['started_at'],
            user_agent=profile._data['operator']['user_agent'],valid_from=identity['valid_from'],expires_at=identity['expires_at'],
            send_not_after=float(send_limit))
        _FLIGHTS[id(self)]=self
        _JOBS[id(self)]=(self,governor,session,transport,target,witness,profile,token,deadline,self.wire,self.pid,self.thread,self.epoch)
    def __repr__(self):return '<native DOC request flight>'
    def __reduce__(self):raise TypeError('DOC flight cannot cross processes')
    def _job_memory(self):
        original=_JOBS.get(id(self))
        current=(self,self.governor,self.session,self.transport,self.target,self.witness,self.profile,self.token,
            self.deadline,self.wire,self.pid,self.thread,self.epoch)
        return original is not None and all(before is after for before,after in zip(original,current))
    def identity(self):
        if (type(self) is not DocRequestFlight or _FLIGHTS.get(id(self)) is not self or self._factory is not _FACTORY
                or not self._job_memory()
                or self.pid!=os.getpid() or self.thread is not threading.current_thread()):raise PermissionError('actual DOC flight required')
        _identity(self.governor)
        if self.governor.supervisor._slot_epoch!=self.epoch or self.governor.supervisor._session is not self.session:raise PermissionError('DOC flight slot retired')
    def check_spawn(self,arguments,process=None):
        from .source_document_access import session_supervisor
        from .source_policy import _network_get
        self.identity();supervisor=session_supervisor(self.session)
        _source()._check(supervisor,published=True);self.profile.check(network=True);_held(self.governor)
        with self.session._transaction() as conn:self.witness.check(conn,network=True)
        if (self.governor.flight is not self or self.state!='OPENING' or time.monotonic()>=self.deadline
                or type(arguments) is not tuple or len(arguments)!=6 or arguments[1] is not self.wire
                or arguments[2] is not _network_get or arguments[4]!=self.deadline or arguments[5]!=self.witness.owner.identity
                or (process is not None and self.process is not process)):raise PermissionError('DOC spawn job differs')
    def memory_handoff(self,session,transport):
        governor=self.governor;supervisor=governor.supervisor
        if (type(self) is not DocRequestFlight or _FLIGHTS.get(id(self)) is not self or self._factory is not _FACTORY or self.pid!=os.getpid()
                or not self._job_memory()
                or self.thread is not threading.current_thread() or governor.flight is not self
                or governor.cadence.flight is not self.token or governor.cadence.uncertain or governor.retired or governor.errors
                or self.state!='OPENING' or self.handed_off or self.session is not session or self.transport is not transport
                or supervisor._slot_epoch!=self.epoch or supervisor._session is not session
                or self._profiles.get(id(self.profile)) is not self.profile or self.profile is not governor.profile
                or self.profile.state!='BOUND' or self.profile.fd is None or self.witness is not session._doc_request
                or self._requests.get(id(self.witness)) is not self.witness
                or not self.witness.active or not self.witness.issued or self.witness.epoch!=self.epoch
                or self.process is None or self.popen is None or time.monotonic()>=self.wire.send_not_after
                or not self.valid_from_epoch<=time.time()<self.expires_epoch):
            raise PermissionError('DOC flight handoff retired')
    def unknown(self,error):
        self.identity();self.state='CLEANUP_UNCERTAIN'
        self.governor.cadence.unknown(self.token);_uncertain(self.governor,error)


def wait_before_request(governor,actual_session):
    from .source_document_access import session_supervisor
    supervisor=_identity(governor)
    if session_supervisor(actual_session) is not supervisor or actual_session._doc_request is not None or supervisor._lock._is_owned():
        raise PermissionError('DOC request pacing outside Owner/DB/G required')
    while True:
        _source()._check(supervisor,published=True)
        if governor.retired or governor.errors or governor.profile is None or governor.flight is not None:raise PermissionError('DOC request pacing unavailable')
        governor.profile.check(network=True);_held(governor)
        delay=governor.cadence.delay(time.monotonic())
        if delay==0:return
        supervisor._stop.wait(delay)


def release_request(witness):
    """Forget only physically retired handles at the original gate's exit."""
    from .source_workflow import SourceSession
    from . import source_policy,source_spawn
    if inspect.currentframe().f_back.f_code is not SourceSession._raw_request_gate.__wrapped__.__code__:
        raise PermissionError('canonical DOC request release required')
    for flight in tuple(_FLIGHTS.values()):
        if flight.witness is not witness:continue
        flight.identity()
        if flight.state!='RETIRED' or flight.governor.flight is flight:raise PermissionError('DOC physical retirement absent')
        source_policy.require_doc_retirement(flight.retirement,flight)
        if flight.outcome is not None:source_policy._DOC_OUTCOMES.pop(id(flight.outcome),None)
        source_policy._DOC_RETIREMENTS.pop(id(flight.retirement),None)
        source_spawn._DOC_PROCESSES.pop(id(flight.process),None)
        _FLIGHTS.pop(id(flight),None)
        _JOBS.pop(id(flight),None)
    from .source_document_access import _COMPLETIONS,_COMPLETION_DOMAINS
    for completion in tuple(_COMPLETIONS.values()):
        if completion.witness is witness:
            completion.state='ABORTED';_COMPLETIONS.pop(id(completion),None)
            _COMPLETION_DOMAINS.pop(id(completion),None)
