"""Bounded systemd metadata rules. Import has no IO or authority side effects.

Collectors receive held FDs and finite proc bytes from the owning fixed-path
consumer. Data returned here is never a credential, witness or capability.
"""
import errno
import os
import stat
import struct

DIRECTORY = '/run/credentials/structural-web.service'
SHAPES = ('ROOT_ACL_RO', 'SERVICE_OWNER_RO')
CHECKS = ('DIR_OWNER', 'FILE_OWNER', 'MODE', 'ACL_SHAPE', 'ACL_MASK', 'DEFAULT_ACL',
          'LINK', 'MOUNT_RO', 'MOUNT_ID', 'IDENTITY', 'CONSUMER', 'NAMESPACE', 'IO')
ACL_STATES = ('ABSENT', 'PRESENT', 'UNSUPPORTED', 'IO', 'INVALID', 'TOO_MANY')
TAGS = (1, 2, 4, 8, 16, 32)
UNDEFINED = 4294967295
SNAPSHOT_FIELDS = ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime', 'ctime',
                   'access', 'default', 'readonly', 'mount_id', 'mount_matches')
CONSUMER_FIELDS = ('pid', 'start', 'uid', 'gid', 'user_ns', 'mount_ns')


def decode_acl(raw, state='PRESENT'):
    """Return a canonical finite ACL description; never interpret permissively."""
    if state not in ACL_STATES or state != 'PRESENT':
        if raw is not None or state not in ('ABSENT', 'UNSUPPORTED', 'IO'):
            raise ValueError('ACL_SHAPE')
        return (state, (), None)
    if type(raw) is not bytes or len(raw) < 4 or (len(raw) - 4) % 8:
        return ('INVALID', (), None)
    count = (len(raw) - 4) // 8
    if count > 5:
        return ('TOO_MANY', (), min(count, 65535))
    if len(raw) > 44 or count not in (3, 5) or struct.unpack('<I', raw[:4])[0] != 2:
        return ('INVALID', (), count)
    result = []
    for offset in range(4, len(raw), 8):
        tag, perm, qualifier = struct.unpack('<HHI', raw[offset:offset+8])
        if (tag not in TAGS or perm > 7
                or (tag in (1, 4, 16, 32) and qualifier != UNDEFINED)
                or (tag in (2, 8) and qualifier == UNDEFINED)):
            return ('INVALID', (), count)
        result.append((tag, qualifier, perm))
    if len({(tag, qualifier) for tag, qualifier, _ in result}) != len(result):
        return ('INVALID', (), count)
    return ('PRESENT', tuple(sorted(result)), count)


def _xattr(fd, name):
    try:
        raw = os.getxattr(fd, name)
    except OSError as error:
        if error.errno == errno.ENODATA:
            return decode_acl(None, 'ABSENT')
        if error.errno in (errno.EOPNOTSUPP, errno.ENOTSUP):
            return decode_acl(None, 'UNSUPPORTED')
        return decode_acl(None, 'IO')
    except (AttributeError, TypeError):
        return decode_acl(None, 'IO')
    return decode_acl(raw)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def parse_fdinfo(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise ValueError('MOUNT_ID')
    rows = [line.split() for line in raw.splitlines() if line.startswith(b'mnt_id:')]
    if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].isdigit():
        raise ValueError('MOUNT_ID')
    number = int(rows[0][1])
    if not 0 < number < 2**63:
        raise ValueError('MOUNT_ID')
    return number


def capture_fd(fd, fdinfo, mountinfo):
    """Bracket xattr/vfs reads with fstat; caller owns FD/proc IO and closure."""
    if type(fd) is not int or fd < 0:
        raise ValueError('IO')
    before = os.fstat(fd)
    access = _xattr(fd, 'system.posix_acl_access')
    default = _xattr(fd, 'system.posix_acl_default') if stat.S_ISDIR(before.st_mode) else ('ABSENT', (), None)
    readonly = bool(os.fstatvfs(fd).f_flag & os.ST_RDONLY)
    after = os.fstat(fd)
    if _identity(before) != _identity(after):
        raise ValueError('IDENTITY')
    mount_id = parse_fdinfo(fdinfo)
    try:matched = mount_matches(mountinfo, mount_id)
    except ValueError:matched = False
    return dict(zip(SNAPSHOT_FIELDS, (*_identity(after), access, default, readonly, mount_id, matched)))


def _acl_valid(acl):
    if (type(acl) is not tuple or len(acl) != 3 or acl[0] not in ACL_STATES
            or type(acl[1]) is not tuple or len(acl[1]) > 5
            or acl[2] is not None and (type(acl[2]) is not int or not 0 <= acl[2] <= 65535)):
        return False
    if acl[0] == 'PRESENT':
        if acl[2] != len(acl[1]):return False
        for row in acl[1]:
            if (type(row) is not tuple or len(row) != 3 or any(type(x) is not int for x in row)
                    or row[0] not in TAGS or not 0 <= row[1] <= UNDEFINED or not 0 <= row[2] <= 7):return False
        return len(set((x[0], x[1]) for x in acl[1])) == len(acl[1]) and tuple(sorted(acl[1])) == acl[1]
    return not acl[1]


def validate_snapshot(snapshot, role, uid, gid):
    if (type(snapshot) is not dict or set(snapshot) != set(SNAPSHOT_FIELDS) or role not in ('directory', 'file', 'ancestor')
            or type(uid) is not int or not 0 < uid < UNDEFINED or type(gid) is not int or not 0 <= gid < UNDEFINED):
        raise ValueError('CONSUMER')
    if (any(type(snapshot[k]) is not int or not 0 <= snapshot[k] < 2**64 for k in SNAPSHOT_FIELDS[:9])
            or type(snapshot['readonly']) is not bool or type(snapshot['mount_matches']) is not bool or type(snapshot['mount_id']) is not int
            or not 0 < snapshot['mount_id'] < 2**63 or not _acl_valid(snapshot['access']) or not _acl_valid(snapshot['default'])):
        raise ValueError('IO')
    mode = snapshot['mode'];directory = role != 'file'
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError('MODE')
    if (not 1 <= snapshot['nlink'] < 2**32 or not directory and snapshot['nlink'] != 1):
        raise ValueError('LINK')
    access, default = snapshot['access'], snapshot['default']
    if role != 'ancestor' and snapshot['readonly'] is not True:raise ValueError('MOUNT_RO')
    if access[0] == 'IO' or default[0] == 'IO':raise ValueError('IO')
    if default[0] not in ('ABSENT', 'UNSUPPORTED'):
        raise ValueError('DEFAULT_ACL')
    if role == 'ancestor':
        if snapshot['uid'] != 0 or mode & 0o022:
            raise ValueError('DIR_OWNER')
        if access[0] not in ('ABSENT', 'UNSUPPORTED', 'PRESENT'):
            raise ValueError('ACL_SHAPE')
        if access[0] == 'PRESENT':
            # A POSIX ACL's mask is represented by stat group bits. Hidden
            # write is harmless only when masked off; root owner is trusted.
            masks = [p for tag, _, p in access[1] if tag == 16]
            mask = masks[0] if len(masks) == 1 else (mode >> 3) & 7
            if any(p & 2 for tag, _, p in access[1] if tag == 32):raise ValueError('ACL_SHAPE')
            if any(p & mask & 2 for tag, q, p in access[1] if tag in (2, 4, 8) and (tag != 2 or q != 0)):
                raise ValueError('ACL_SHAPE')
        return 'ANCESTOR'
    if snapshot['readonly'] is not True:
        raise ValueError('MOUNT_RO')
    if snapshot['mount_matches'] is not True:raise ValueError('MOUNT_ID')
    permission = 5 if directory else 4
    if snapshot['uid'] == 0 and snapshot['gid'] == 0:
        shape = 'ROOT_ACL_RO';expected_mode = 0o550 if directory else 0o440
        expected = ((1, UNDEFINED, permission), (2, uid, permission), (4, UNDEFINED, 0), (16, UNDEFINED, permission), (32, UNDEFINED, 0))
        if access != ('PRESENT', expected, 5):raise ValueError('ACL_SHAPE')
        if default[0] != 'ABSENT':raise ValueError('DEFAULT_ACL')
    elif snapshot['uid'] == uid and snapshot['gid'] == gid:
        shape = 'SERVICE_OWNER_RO';expected_mode = 0o500 if directory else 0o400
        base = ((1, UNDEFINED, permission), (4, UNDEFINED, 0), (32, UNDEFINED, 0))
        if access[0] not in ('ABSENT', 'UNSUPPORTED') and access != ('PRESENT', base, 3):raise ValueError('ACL_SHAPE')
    else:
        raise ValueError('DIR_OWNER' if directory else 'FILE_OWNER')
    if stat.S_IMODE(mode) != expected_mode:
        raise ValueError('ACL_MASK' if access[0] == 'PRESENT' else 'MODE')
    return shape


def same_snapshot(a, b):
    return type(a) is dict and type(b) is dict and set(a) == set(b) == set(SNAPSHOT_FIELDS) and a == b


def mount_matches(raw, mount_id):
    """Only the consumer mountinfo view can prove this fixed credential mount."""
    if type(raw) is not bytes or not 0 < len(raw) <= 262144 or not raw.endswith(b'\n'):
        raise ValueError('MOUNT_ID')
    matches = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 10 or b'-' not in parts or not parts[0].isdigit():raise ValueError('MOUNT_ID')
        if int(parts[0]) == mount_id:matches.append(parts)
    if (len(matches) != 1 or matches[0][4] != DIRECTORY.encode('ascii')
            or b'ro' not in matches[0][5].split(b',') or b'rw' in matches[0][5].split(b',')):
        raise ValueError('MOUNT_ID')
    return True


def parse_consumer(status, uid_map, gid_map, process_stat, pid, user_ns, mount_ns):
    if type(pid) is not int or not 1 <= pid < 2**31:
        raise ValueError('CONSUMER')
    if any(type(raw) is not bytes or not 0 < len(raw) <= 65536 for raw in (status, uid_map, gid_map, process_stat)):
        raise ValueError('CONSUMER')
    rows = {}
    for line in status.splitlines():
        if b':' in line:
            key, value = line.split(b':', 1)
            if key in (b'Uid', b'Gid', b'CapEff', b'CapPrm', b'CapAmb', b'NoNewPrivs'):
                if key in rows:raise ValueError('CONSUMER')
                rows[key] = value.split()
    if set(rows) != {b'Uid', b'Gid', b'CapEff', b'CapPrm', b'CapAmb', b'NoNewPrivs'}:
        raise ValueError('CONSUMER')
    identities = []
    for label in (b'Uid', b'Gid'):
        values = rows[label]
        if len(values) != 4 or any(not value.isdigit() for value in values):raise ValueError('CONSUMER')
        numbers = tuple(int(v) for v in values)
        if len(set(numbers)) != 1 or not 0 <= numbers[0] < UNDEFINED:raise ValueError('CONSUMER')
        identities.append(numbers[0])
    if identities[0] == 0:raise ValueError('CONSUMER')
    if rows[b'NoNewPrivs'] != [b'1']:raise ValueError('CONSUMER')
    for label in (b'CapEff', b'CapPrm', b'CapAmb'):
        values = rows[label]
        if len(values) != 1 or len(values[0]) != 16 or any(c not in b'0123456789abcdef' for c in values[0]) or int(values[0], 16):
            raise ValueError('CONSUMER')
    for raw in (uid_map, gid_map):
        if len(raw.splitlines()) != 1 or raw.split() != [b'0', b'0', b'4294967295']:raise ValueError('NAMESPACE')
    end = process_stat.rfind(b') ');fields = process_stat[end+2:].split()
    if end < 0 or process_stat.split(b' (', 1)[0] != str(pid).encode() or len(fields) < 20 or not fields[19].isdigit():
        raise ValueError('CONSUMER')
    for namespace in (user_ns, mount_ns):
        if type(namespace) is not tuple or len(namespace) != 2 or any(type(n) is not int or not 0 < n < 2**64 for n in namespace):
            raise ValueError('NAMESPACE')
    start = int(fields[19])
    if not 0 < start < 2**63:raise ValueError('CONSUMER')
    return dict(zip(CONSUMER_FIELDS, (pid, start, *identities, user_ns, mount_ns)))
