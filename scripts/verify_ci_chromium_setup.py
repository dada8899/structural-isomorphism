"""One setup-only verification: metadata, fixed helper, then --version only.

No Source/application import, page, driver/CDP session or performance sample.
Only the three explicitly projected public JSON records may be uploaded.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pwd
import re
import signal
import stat
import subprocess
import sys
import time

HELPER_SHA = '6801bdfc0678eec08343e8ec43753d54270df096ed7a3103bb10c0ea80376db2'
BRANCH = 'refs/heads/codex/structure-analyze-mobile-setup-fixed-88830-attempt3'
HELPER = Path(__file__).resolve().with_name('prepare_ci_chromium.py')
SYSTEM_FILES = {'source': (Path('/etc/apt/sources.list.d/ubuntu.sources'), 16384),
                'keyring': (Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg'), 1024 * 1024)}
VERSION = '147.0.7727.15'
SCHEMA = 'chromium-pinned-keyring-setup-v1'
KEYRING_PROFILE = 'ubuntu-noble-archive-pinned-v1'
KEYRING_SHA = '80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31'
KEYRING_BYTES = 3607
FAILURE_PROTOCOL = 'ci-chromium-failure-v1'
FAILURE_STAGES = {
    'parent': ('entry', 'host', 'request', 'launch', 'response', 'retirement'),
    'root-worker': ('entry', 'request', 'sdk', 'subreaper', 'keyring', 'source', 'install', 'retirement'),
}
PINS = {'pytest':'9.0.3', 'playwright':'1.59.0', 'pytest-playwright':'0.7.2',
        'fastapi':'0.135.0', 'pydantic':'2.7.4', 'starlette':'1.3.1',
        'uvicorn':'0.27.1', 'PyJWT':'2.15.1', 'slowapi':'0.1.9', 'structlog':'25.5.0'}


class Unavailable(RuntimeError):
    pass


def need(value):
    if not value:
        raise Unavailable('setup_verification_unavailable')


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def metadata(path, cap, owner):
    need(path.is_absolute() and path == path.resolve())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_uid == owner and 0 <= first.st_size <= cap)
        identity = (first.st_dev, first.st_ino, first.st_uid, first.st_gid, first.st_mode, first.st_nlink, first.st_size)
        digest, total, deadline = hashlib.sha256(), 0, time.monotonic() + 5
        while True:
            need(time.monotonic() < deadline)
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            total += len(block)
            need(total <= cap)
            digest.update(block)
        final = os.fstat(fd)
        path_final = path.lstat()
        for current in (final, path_final):
            need((current.st_dev, current.st_ino, current.st_uid, current.st_gid, current.st_mode, current.st_nlink, current.st_size) == identity)
            need((current.st_mtime_ns, current.st_ctime_ns) == (first.st_mtime_ns, first.st_ctime_ns))
        need(total == first.st_size)
        return {'dev': first.st_dev, 'ino': first.st_ino, 'uid': first.st_uid, 'gid': first.st_gid,
                'mode': stat.S_IMODE(first.st_mode), 'nlink': first.st_nlink,
                'size': total, 'sha256': digest.hexdigest()}
    finally:
        os.close(fd)


def snapshot():
    value = {role: metadata(path, cap, 0) for role, (path, cap) in SYSTEM_FILES.items()}
    # The original keyring is an observed untrusted input, never the APT trust
    # endpoint. Only the root-born effective copy can satisfy that authority.
    need(value['source']['mode'] == 0o644)
    need(value['keyring']['size'] == KEYRING_BYTES and value['keyring']['sha256'] == KEYRING_SHA)
    return value


def keyring_material():
    return {'profile':KEYRING_PROFILE,'sha256':KEYRING_SHA,'size':KEYRING_BYTES,
            'input_trust':'untrusted','effective_created':False}


def keyring_material_safe(value):
    return (type(value) is dict and set(value)=={'profile','sha256','size','input_trust','effective_created'}
            and value['profile']==KEYRING_PROFILE and value['sha256']==KEYRING_SHA
            and type(value['size']) is int and value['size']==KEYRING_BYTES
            and value['input_trust']=='untrusted' and value['effective_created'] is False)


def helper_metadata():
    value = metadata(HELPER, 128 * 1024, os.getuid())
    need(value['sha256'] == HELPER_SHA)
    return value


def sdk():
    need(sys.version_info[:2] == (3, 11))
    versions = {name: importlib.metadata.version(name) for name in PINS}
    need(versions == PINS)
    distribution = importlib.metadata.distribution('playwright')
    path = Path(distribution.locate_file('playwright/driver/package/browsers.json'))
    need(path.stat().st_size <= 16384)
    data = strict_json(path.read_bytes())
    result = {}
    for name in ('chromium', 'chromium-headless-shell'):
        rows = [row for row in data['browsers'] if row['name'] == name]
        need(len(rows) == 1 and rows[0]['revision'] == '1217' and rows[0]['browserVersion'] == VERSION)
        need(not rows[0].get('revisionOverrides'))
        result[name] = {'revision': '1217', 'version': VERSION}
    return {'python': '.'.join(map(str, sys.version_info[:3])), 'versions': versions, 'browsers': result}


def context():
    need(sys.platform == 'linux' and os.uname().machine == 'x86_64' and os.getuid() == os.geteuid() > 0)
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted')
    need(os.environ.get('RUNNER_OS') == 'Linux' and os.environ.get('RUNNER_ARCH') == 'X64')
    need(os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_REF') == BRANCH)
    need(os.environ.get('GITHUB_REPOSITORY') == 'dada8899/structural-isomorphism')
    run = os.environ.get('GITHUB_RUN_ID', '')
    need(re.fullmatch('[1-9][0-9]{0,19}', run) is not None and os.environ.get('GITHUB_RUN_ATTEMPT') == '1')
    sha = os.environ.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', sha) is not None)
    temporary = Path(os.environ['RUNNER_TEMP'])
    need(temporary.is_absolute() and temporary == temporary.resolve() and temporary.stat().st_uid == os.getuid())
    root = temporary / ('structure-chromium-setup-once-' + run + '-1')
    if not root.exists():
        root.mkdir(mode=0o700)
    need(not root.is_symlink() and root.stat().st_uid == os.getuid() and stat.S_IMODE(root.stat().st_mode) == 0o700)
    public = root/'public'
    if not public.exists():
        public.mkdir(mode=0o700)
    need(not public.is_symlink() and public.stat().st_uid == os.getuid() and stat.S_IMODE(public.stat().st_mode) == 0o700)
    return root, {'schema': SCHEMA, 'classification': 'SETUP_ONLY_NOT_A_GRADE', 'run_id': run, 'event_sha': sha}


def write_json(path, value, exclusive=False):
    raw = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    need(len(raw) <= 32768)
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_CREAT
    flags |= os.O_EXCL if exclusive else 0
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600)
        at = 0
        while at < len(raw):
            count = os.write(fd, raw[at:])
            need(count > 0)
            at += count
        os.ftruncate(fd, len(raw))
        os.fsync(fd)
    finally:
        os.close(fd)


def read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid() and first.st_nlink == 1
             and stat.S_IMODE(first.st_mode) == 0o600 and first.st_size <= 32768)
        raw = os.read(fd, 32769)
        final = os.fstat(fd)
        need(len(raw) == first.st_size and (first.st_dev, first.st_ino, first.st_mtime_ns, first.st_ctime_ns)
             == (final.st_dev, final.st_ino, final.st_mtime_ns, final.st_ctime_ns))
        path_final = path.lstat()
        need((path_final.st_dev, path_final.st_ino) == (first.st_dev, first.st_ino))
        return strict_json(raw)
    finally:
        os.close(fd)


def source_predicate(expected):
    """Check the complete held source bytes with the hash-locked pure parser."""
    path, cap = SYSTEM_FILES['source']
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0)
        need({name:getattr(info,'st_'+name) for name in ('dev','ino','uid','gid','nlink','size')}
             == {name:expected[name] for name in ('dev','ino','uid','gid','nlink','size')})
        need(stat.S_IMODE(info.st_mode) == expected['mode'])
        raw = os.pread(fd, cap + 1, 0)
        need(len(raw) == expected['size'] <= cap and hashlib.sha256(raw).hexdigest() == expected['sha256'])
        stable = lambda row: (row.st_dev,row.st_ino,row.st_uid,row.st_gid,row.st_mode,
                              row.st_nlink,row.st_size,row.st_mtime_ns,row.st_ctime_ns)
        need(stable(os.fstat(fd)) == stable(info) == stable(path.lstat()))
        need(helper_metadata()['sha256'] == HELPER_SHA)
        helper_fd = os.open(HELPER, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            helper_raw = os.pread(helper_fd, 128 * 1024 + 1, 0)
            need(len(helper_raw) <= 128 * 1024 and hashlib.sha256(helper_raw).hexdigest() == HELPER_SHA)
        finally:
            os.close(helper_fd)
        # Execute the actual hash-locked source bytes, never a loader cache.
        module = {'__name__':'fixed_ci_chromium_predicate','__file__':str(HELPER)}
        exec(compile(helper_raw, str(HELPER), 'exec'), module)
        module['mirror_source'](raw, None)  # Discard render; never access/log an input URI.
        need(helper_metadata()['sha256'] == HELPER_SHA)
    finally:
        os.close(fd)


def before(root, header):
    value = {**header, 'phase': 'before', 'status': 'UNKNOWN'}
    try:
        value.update(helper=helper_metadata(), system=snapshot(), sdk=sdk(),keyring_material=keyring_material())
        source_predicate(value['system']['source'])
        write_json(root/'state.json', {'before': {**value, 'status':'ready'}, 'attempts': 0, 'claim':None}, exclusive=True)
        value['status'] = 'ready'
    finally:
        write_json(root/'public/setup-before.json', value)
    return 0


def outcome(header, code=None, ready=False, attempts=None, keyring=None, failure=None):
    return {**header, 'phase': 'helper', 'status': 'ready' if ready else 'UNKNOWN',
            'attempts': attempts, 'exit_code': code, 'children_closed': True if ready else None,
            'source_restored': True if ready else None,'keyring_receipt':keyring if ready else None,
            'failure_phase':failure['failure_phase'] if failure is not None else None,
            'failure_stage':failure['failure_stage'] if failure is not None else None}


def failure_stage_safe(phase, stage):
    return (type(phase) is str and phase in FAILURE_STAGES
            and type(stage) is str and stage in FAILURE_STAGES[phase])


def helper_failure(value, code):
    return (type(code) is int and code == 2 and type(value) is dict
            and set(value) == {'protocol','status','failure_phase','failure_stage'}
            and value['protocol'] == FAILURE_PROTOCOL and value['status'] == 'UNKNOWN'
            and failure_stage_safe(value['failure_phase'],value['failure_stage']))


def helper_ready(value, code):
    return (type(code) is int and code == 0 and type(value) is dict and set(value) == {'status', 'children_closed', 'source_restored','keyring'}
            and value['status'] == 'ready' and value['children_closed'] is True and value['source_restored'] is True
            and keyring_receipt_safe(value['keyring']))


def claim_body(header, state_info):
    return {'run_id':header['run_id'], 'event_sha':header['event_sha'],
            'state_dev':state_info.st_dev, 'state_ino':state_info.st_ino}


def create_launch_claim(root, header, state_info):
    """Exclusive durable reservation, never programmatically removed or reused.

    This bounds retries/replacement/concurrency in the fixed single-step job;
    it cannot isolate an adversary rewriting every authority as the same UID.
    """
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        info = os.fstat(directory)
        need(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
        fd = os.open('launch-claim.json', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        raw = json.dumps(claim_body(header, state_info), sort_keys=True).encode()
        need(os.pwrite(fd, raw, 0) == len(raw))
        os.fsync(fd)
        os.fsync(directory)
        value = metadata(root/'launch-claim.json', 4096, os.getuid())
        current = os.fstat(fd)
        need((current.st_dev,current.st_ino,current.st_nlink) == (value['dev'],value['ino'],1))
        need(read_json(root/'launch-claim.json') == claim_body(header,state_info))
        return fd, value
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    finally:
        os.close(directory)


def check_launch_claim(root, header, state, state_info, claim_fd=None):
    need(type(state['attempts']) is int and state['attempts'] == 1 and type(state['claim']) is dict)
    need(metadata(root/'launch-claim.json',4096,os.getuid()) == state['claim'])
    need(read_json(root/'launch-claim.json') == claim_body(header,state_info))
    if claim_fd is not None:
        current = os.fstat(claim_fd)
        need((current.st_dev,current.st_ino,current.st_nlink) == (state['claim']['dev'],state['claim']['ino'],1))


def install(root, header):
    state_path = root/'state.json'
    fd = os.open(state_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    value = outcome(header)
    attempted, code, claim_fd = False, None, None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid() and first.st_nlink == 1 and stat.S_IMODE(first.st_mode) == 0o600)
        need(not os.path.lexists(root/'public/helper-outcome.json'))
        state = read_json(state_path)
        need(state['before']['status'] == 'ready' and type(state['attempts']) is int and state['attempts'] == 0 and state['claim'] is None)
        need(helper_metadata() == state['before']['helper'] and snapshot() == state['before']['system'])
        current = state_path.lstat()
        need((current.st_dev, current.st_ino) == (first.st_dev, first.st_ino) and os.fstat(fd).st_nlink == 1)
        claim_fd, state['claim'] = create_launch_claim(root,header,first)
        attempted = True
        state['attempts'] = 1  # Persist before any possibly post-fork launch failure.
        raw = json.dumps(state).encode()
        need(os.pwrite(fd, raw, 0) == len(raw))
        os.ftruncate(fd, len(raw)); os.fsync(fd)
        current = state_path.lstat()
        need((current.st_dev,current.st_ino) == (first.st_dev,first.st_ino) and os.fstat(fd).st_nlink == 1)
        need(os.pread(fd,len(raw)+1,0) == raw and read_json(state_path) == state)
        check_launch_claim(root,header,state,first,claim_fd)
        value = outcome(header, attempts=1)
        env = {name: os.environ[name] for name in ('GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT', 'RUNNER_OS', 'RUNNER_ARCH', 'RUNNER_TEMP')}
        env.update(PATH=str(Path(sys.executable).parent)+':/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8')
        result = subprocess.run([sys.executable, '-I', '-B', str(HELPER)], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=100)
        need(len(result.stdout) <= 4096)
        code = result.returncode if type(result.returncode) is int else None
        need(code is not None)
        response = strict_json(result.stdout)
        ready = helper_ready(response, code)
        if ready:need(response['keyring']['original'] == state['before']['system']['keyring'])
        need(helper_metadata() == state['before']['helper'])
        need((state_path.lstat().st_dev,state_path.lstat().st_ino) == (first.st_dev,first.st_ino))
        need(os.pread(fd,len(raw)+1,0) == raw and read_json(state_path) == state)
        check_launch_claim(root,header,state,first,claim_fd)
        value = outcome(header, code, ready, 1,response['keyring'] if ready else None,
                        response if helper_failure(response, code) else None)
        return code if code != 0 else (0 if ready else 2)
    except BaseException:
        value = outcome(header, code, attempts=1 if attempted else None)
        return code if code is not None and code != 0 else 2
    finally:
        try:
            if attempted or not (root/'public/helper-outcome.json').exists():
                write_json(root/'public/helper-outcome.json', value)
        finally:
            if claim_fd is not None:
                os.close(claim_fd)
            os.close(fd)


def version_probe(binary):
    """Only --version, with a five-second total observation/termination budget."""
    deadline, process = time.monotonic()+5, None
    record = {'status':'UNKNOWN', 'pid':None, 'exit_code':None, 'version':None,
              'direct_process_reaped':None, 'group_absent':None}
    try:
        process = subprocess.Popen([str(binary), '--version'], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            env={'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8'})
        record['pid'] = process.pid
        output, _ = process.communicate(timeout=max(0, deadline-time.monotonic()-1))
        need(process.returncode == 0 and len(output) <= 512 and time.monotonic() < deadline)
        text = output.decode('ascii')
        need(re.fullmatch(r'(?:Google Chrome for Testing|Chromium|HeadlessChrome) '+re.escape(VERSION)+r'\s*', text) is not None)
        record['version'] = VERSION
    except BaseException:
        pass
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    # The live direct child anchors this user-owned session.
                    os.killpg(process.pid, signal.SIGKILL)
                record['exit_code'] = process.wait(timeout=max(0, deadline-time.monotonic()))
                record['direct_process_reaped'] = True
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    record['group_absent'] = True
                else:
                    record['group_absent'] = False
                if record['exit_code'] == 0 and record['version'] == VERSION and record['group_absent'] is True and time.monotonic() < deadline:
                    record['status'] = 'ready'
            except BaseException:
                record['status'] = 'UNKNOWN'
            finally:
                if process.stdout is not None:
                    process.stdout.close()
    return record


def payloads(result):
    cache = Path(pwd.getpwuid(os.getuid()).pw_dir)/'.cache/ms-playwright'
    paths = {'chromium': ('chromium-1217', 'chrome-linux64/chrome'),
             'chromium-headless-shell': ('chromium_headless_shell-1217', 'chrome-headless-shell-linux64/chrome-headless-shell')}
    for name, (directory, relative) in paths.items():
        binary = cache/directory/relative
        marker = cache/directory/'INSTALLATION_COMPLETE'
        mark = metadata(marker, 64, os.getuid())
        original = metadata(binary, 512*1024*1024, os.getuid())
        need(original['size'] > 0 and original['mode'] & 0o111 and os.access(binary, os.X_OK))
        result[name] = {'binary': original, 'installation_marker': mark, 'probe':None}
        probe = version_probe(binary)
        result[name]['probe'] = probe
        need(probe['status'] == 'ready')
        need(metadata(binary, 512*1024*1024, os.getuid()) == original)
    return result


PUBLIC_FILES = ('setup-before.json', 'helper-outcome.json', 'setup-after.json')
HEADER_KEYS = {'schema','classification','run_id','event_sha','phase','status'}
META_KEYS = {'dev','ino','uid','gid','mode','nlink','size','sha256'}
BROWSER_NAMES = {'chromium','chromium-headless-shell'}


def integer(value, low=0, high=2**64-1):
    return type(value) is int and low <= value <= high


def metadata_safe(value, cap):
    return (type(value) is dict and set(value) == META_KEYS
            and all(integer(value[k]) for k in META_KEYS-{'sha256'})
            and value['nlink'] == 1 and value['mode'] <= 0o7777 and value['size'] <= cap
            and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None)


def system_safe(value):
    return (type(value) is dict and set(value) == {'source','keyring'}
            and metadata_safe(value['source'],16384) and metadata_safe(value['keyring'],1024*1024))


def sdk_safe(value):
    return (type(value) is dict and set(value) == {'python','versions','browsers'}
            and type(value['python']) is str and re.fullmatch(r'3\.11\.[0-9]{1,3}',value['python']) is not None
            and type(value['versions']) is dict and value['versions'] == PINS
            and type(value['browsers']) is dict and set(value['browsers']) == BROWSER_NAMES
            and all(type(row) is dict and row == {'revision':'1217','version':VERSION} for row in value['browsers'].values()))


def keyring_receipt_safe(value):
    keys={'profile','reference','input_trust','original','effective','directory','original_unchanged','signed_by_bound','retired'}
    if type(value) is not dict or set(value)!=keys or value['profile']!=KEYRING_PROFILE or value['input_trust']!='untrusted':return False
    if type(value['reference']) is not str or re.fullmatch('[0-9a-f]{32}',value['reference']) is None:return False
    if any(value[k] is not True for k in ('original_unchanged','signed_by_bound','retired')):return False
    for name in ('original','effective'):
        row=value[name]
        if not metadata_safe(row,KEYRING_BYTES) or row['uid']!=0 or row['size']!=KEYRING_BYTES or row['sha256']!=KEYRING_SHA:return False
    if value['effective']['gid']!=0 or value['effective']['mode']!=0o644:return False
    row=value['directory']
    return (type(row) is dict and set(row)=={'dev','ino','uid','gid','mode','nlink'}
            and all(integer(v) for v in row.values()) and row['uid']==row['gid']==0
            and row['mode']==0o755 and row['nlink']>=2)


def probe_safe(value):
    keys = {'status','pid','exit_code','version','direct_process_reaped','group_absent'}
    if type(value) is not dict or set(value) != keys or value['status'] not in ('ready','UNKNOWN'):
        return False
    if value['pid'] is not None and not integer(value['pid'],1,2**31-1):
        return False
    if value['exit_code'] is not None and not integer(value['exit_code'],-255,255):
        return False
    if value['version'] not in (None,VERSION) or value['direct_process_reaped'] is not None and value['direct_process_reaped'] is not True:
        return False
    if value['group_absent'] is not None and type(value['group_absent']) is not bool:
        return False
    if value['pid'] is None and any(value[k] is not None for k in keys-{'pid','status'}):
        return False
    if value['exit_code'] is not None and value['direct_process_reaped'] is not True:
        return False
    if value['direct_process_reaped'] is True and value['exit_code'] is None:
        return False
    if value['group_absent'] is not None and value['direct_process_reaped'] is not True:
        return False
    return value['status'] == 'UNKNOWN' or (integer(value['pid'],1,2**31-1) and type(value['exit_code']) is int
            and value['exit_code'] == 0 and value['version'] == VERSION
            and value['direct_process_reaped'] is True and value['group_absent'] is True)


def payloads_safe(value, complete):
    if type(value) is not dict or not set(value) <= BROWSER_NAMES or complete and set(value) != BROWSER_NAMES:
        return False
    for row in value.values():
        if type(row) is not dict or set(row) != {'binary','installation_marker','probe'}:
            return False
        if not metadata_safe(row['binary'],512*1024*1024) or not metadata_safe(row['installation_marker'],64):
            return False
        if row['binary']['size'] == 0 or not row['binary']['mode'] & 0o111:
            return False
        if row['probe'] is None:
            if complete:
                return False
        elif not probe_safe(row['probe']) or complete and row['probe']['status'] != 'ready':
            return False
    return True


def public_safe(value):
    """Exact per-phase DTOs; a valid field in one phase grants no other phase."""
    if type(value) is not dict or not HEADER_KEYS <= set(value):
        return False
    if (value['schema'] != SCHEMA or value['classification'] != 'SETUP_ONLY_NOT_A_GRADE'
            or type(value['run_id']) is not str or re.fullmatch('[1-9][0-9]{0,19}',value['run_id']) is None
            or type(value['event_sha']) is not str or re.fullmatch('[0-9a-f]{40}',value['event_sha']) is None
            or value['status'] not in ('ready','UNKNOWN')):
        return False
    ready = value['status'] == 'ready'
    if value['phase'] == 'before':
        if not ready:
            return set(value) == HEADER_KEYS
        return (set(value) == HEADER_KEYS|{'helper','system','sdk','keyring_material'}
                and metadata_safe(value['helper'],128*1024) and value['helper']['sha256'] == HELPER_SHA
                and system_safe(value['system']) and sdk_safe(value['sdk'])
                and keyring_material_safe(value['keyring_material']))
    if value['phase'] == 'helper':
        if set(value) != HEADER_KEYS|{'attempts','exit_code','children_closed','source_restored','keyring_receipt','failure_phase','failure_stage'}:
            return False
        if ready:
            return (type(value['attempts']) is int and value['attempts'] == 1 and type(value['exit_code']) is int
                    and value['exit_code'] == 0 and value['children_closed'] is True and value['source_restored'] is True
                    and keyring_receipt_safe(value['keyring_receipt'])
                    and value['failure_phase'] is None and value['failure_stage'] is None)
        return ((value['attempts'] is None or type(value['attempts']) is int and value['attempts'] == 1)
                and (value['exit_code'] is None or value['attempts'] == 1 and integer(value['exit_code'],-255,255))
                and value['children_closed'] is None and value['source_restored'] is None and value['keyring_receipt'] is None
                and ((value['failure_phase'] is None and value['failure_stage'] is None)
                     or value['attempts'] == 1 and type(value['exit_code']) is int and value['exit_code'] == 2
                     and failure_stage_safe(value['failure_phase'],value['failure_stage'])))
    if value['phase'] == 'after':
        if set(value) != HEADER_KEYS|{'system','system_matches_before','sdk','payloads'} or type(value['system_matches_before']) is not bool:
            return False
        if value['system'] is not None and not system_safe(value['system']) or value['system_matches_before'] and value['system'] is None:
            return False
        if value['sdk'] is not None and not sdk_safe(value['sdk']):
            return False
        if value['payloads'] is not None and (value['sdk'] is None or not payloads_safe(value['payloads'],ready)):
            return False
        return not ready or (value['system_matches_before'] is True and value['system'] is not None
                             and value['sdk'] is not None and value['payloads'] is not None)
    return False


def unknown_record(header, phase):
    if phase == 'helper':
        return outcome(header)
    value = {**header,'phase':phase,'status':'UNKNOWN'}
    if phase == 'after':
        value.update(system=None,system_matches_before=False,sdk=None,payloads=None)
    return value


def project_public(root, header):
    records, rejected = {}, False
    for name, phase in zip(PUBLIC_FILES, ('before','helper','after')):
        try:
            value = read_json(root/'public'/name)
            need(type(value) is dict and public_safe(value))
            need(all(value.get(k) == v for k,v in header.items()) and value.get('phase') == phase)
        except BaseException:
            value = unknown_record(header,phase)
            rejected = True
        records[name] = value
    if rejected:
        records['setup-after.json'] = unknown_record(header,'after')
    for name, value in records.items():
        write_json(root/'public'/name, value)
    return rejected


def publish_safe_output(root, header):
    held, records = [], []
    def identity(info):
        return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,info.st_size)
    def valid(raw,phase):
        value=strict_json(raw)
        need(type(value) is dict and public_safe(value))
        need(all(value.get(k)==v for k,v in header.items()) and value.get('phase')==phase)
        return value
    try:
        for name,phase in zip(PUBLIC_FILES,('before','helper','after')):
            path=root/'public'/name
            fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd)
            info=os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=32768)
            raw=os.pread(fd,32769,0);need(len(raw)==info.st_size);valid(raw,phase)
            need(identity(info)==identity(path.lstat()))
            records.append((fd,path,info,raw,phase))
        output=Path(os.environ['GITHUB_OUTPUT']);need(output.is_absolute() and output==output.resolve())
        before=output.lstat();out_fd=os.open(output,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            out_info=os.fstat(out_fd)
            need(stat.S_ISREG(out_info.st_mode) and out_info.st_uid==os.getuid() and out_info.st_nlink==1 and not out_info.st_mode&0o022)
            need(identity(out_info)==identity(before)==identity(output.lstat()))
            # Original FDs remain held across the real output open. This is a
            # bounded single-writer check, not same-UID adversarial isolation.
            for fd,path,info,raw,phase in records:
                need(identity(os.fstat(fd))==identity(info)==identity(path.lstat()))
                checked=os.pread(fd,len(raw)+1,0);need(checked==raw);parsed=valid(checked,phase)
                need(read_json(path)==parsed and identity(os.fstat(fd))==identity(path.lstat()))
            flag=b'public_records_safe=true\n';need(os.write(out_fd,flag)==len(flag));os.fsync(out_fd)
            after=os.fstat(out_fd)
            need(identity(after)[:-1]==identity(out_info)[:-1]==identity(output.lstat())[:-1] and after.st_size==before.st_size+len(flag))
            return {'reports':[{'file_id':path.name,'dev':info.st_dev,'ino':info.st_ino,'sha256':hashlib.sha256(raw).hexdigest()} for _,path,info,raw,_ in records],
                    'output_dev':out_info.st_dev,'output_ino':out_info.st_ino,'offset':before.st_size,'bytes':len(flag),'fsynced':True}
        finally:os.close(out_fd)
    finally:
        for fd in reversed(held):os.close(fd)


def after(root, header):
    report = {**header, 'phase': 'after', 'status': 'UNKNOWN', 'system':None, 'system_matches_before': False,
              'payloads': None, 'sdk': None}
    try:
        state = read_json(root/'state.json')
        recorded = read_json(root/'public/helper-outcome.json')
        need(state['before']['status'] == 'ready' and type(state['attempts']) is int and state['attempts'] == 1)
        check_launch_claim(root,header,state,(root/'state.json').lstat())
        need(read_json(root/'public/setup-before.json') == state['before'])
        need(snapshot() == state['before']['system'] and helper_metadata() == state['before']['helper'])
        need(keyring_receipt_safe(recorded['keyring_receipt']) and recorded['keyring_receipt']['original']==state['before']['system']['keyring'])
        need(recorded == outcome(header, 0, True, 1,recorded['keyring_receipt']) and type(recorded['exit_code']) is int
             and type(recorded['attempts']) is int and recorded['children_closed'] is True and recorded['source_restored'] is True)
        report['sdk'] = sdk()
        report['payloads'] = {}
        payloads(report['payloads'])
        report['status'] = 'ready'
    except BaseException:
        report['status'] = 'UNKNOWN'
    finally:
        try:
            state = read_json(root/'state.json')
            report['system'] = snapshot()
            report['system_matches_before'] = report['system'] == state['before']['system']
            need(report['system_matches_before'] and helper_metadata() == state['before']['helper'])
        except BaseException:
            report['status'] = 'UNKNOWN'
        for file, value in (('setup-before.json', {**header, 'phase':'before', 'status':'UNKNOWN'}),
                            ('helper-outcome.json', outcome(header))):
            if not (root/'public'/file).exists():
                write_json(root/'public'/file, value, exclusive=True)
        write_json(root/'public/setup-after.json', report)
        if project_public(root, header):
            report['status'] = 'UNKNOWN'
    return 0 if report['status'] == 'ready' else 2


def main():
    try:
        need(sys.argv[1:] in (['before'], ['install'], ['after']))
        root, header = context()
        code = {'before': before, 'install': install, 'after': after}[sys.argv[1]](root, header)
        if sys.argv[1] == 'after':
            publish_safe_output(root, header)
        return code
    except BaseException:
        return 2  # Never print exception text, source configuration or environment.


if __name__ == '__main__':
    raise SystemExit(main())
