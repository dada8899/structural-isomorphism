"""Deletion-only v17 authority. No money or external dispatch writer."""
from contextlib import contextmanager
import json
import os
import sys

from .errors import ResearchError
from .external_first_answer_state import TABLE,_COLUMNS
from .provider_schemas import canonical

_WRITES={}


def require_deletion_frame(conn):
    from .authorization import OwnerGateLease
    from .service import ResearchService, _V17_DELETION_CODES
    frame=sys._getframe(1)
    try:
        while frame:
            if (frame.f_code in _V17_DELETION_CODES and frame.f_globals is sys.modules[ResearchService.__module__].__dict__
                    and frame.f_locals.get("conn") is conn
                    and type(frame.f_locals.get("self")) is ResearchService
                    and type(frame.f_locals.get("owner_lease")) is OwnerGateLease):
                frame.f_locals["owner_lease"].identity
                return
            frame=frame.f_back
    finally:del frame
    raise PermissionError("v17 deletion-only scope required")


def require_no_pending(conn,pid):
    if conn.execute("SELECT 1 FROM "+TABLE+
            " WHERE principal_id=? AND state IN ('reserved','consumed','unknown') LIMIT 1",(pid,)).fetchone():
        raise ResearchError("RECONCILIATION_REQUIRED",503,"仍有未核对的外部费用或预留；未删除账户或释放占用。")


def allowed_delete(conn,operation,before,after):
    entry=_WRITES.get(id(conn))
    if operation!="DELETE" or after is not None or not entry or entry[:2]!=(conn,os.getpid()) or not conn.in_transaction:
        return 0
    try:
        require_deletion_frame(conn)
        entry[2].identity
        return int(canonical(json.loads(before))==entry[3])
    except (PermissionError,ValueError,TypeError,OSError):
        return 0


@contextmanager
def _deleting_row(conn,lease,row):
    if id(conn) in _WRITES:
        raise PermissionError("nested external erasure")
    _WRITES[id(conn)]=(conn,os.getpid(),lease,canonical([row[k] for k in _COLUMNS]))
    try:yield
    finally:_WRITES.pop(id(conn),None)


def erase_in(conn,service,lease,pid,job_id):
    from .paid_control import verify_deletion_origin
    require_deletion_frame(conn)
    job=verify_deletion_origin(conn,store=service.store,lease=lease,job_id=job_id)
    principal=conn.execute("SELECT normalized_email,session_generation,status,gate_id FROM research_principals WHERE id=?",(pid,)).fetchone()
    if not job or job["state"]!="pending" or principal is None or tuple(principal)!=(
            job["owner_email"],job["session_generation"],"deleting",job["gate_id"]):
        raise PermissionError("external deletion owner mismatch")
    require_no_pending(conn,pid)
    rows=conn.execute("SELECT "+",".join(_COLUMNS)+" FROM "+TABLE+" WHERE principal_id=?",(pid,)).fetchall()
    for row in rows:
        with _deleting_row(conn,lease,row):
            if conn.execute("DELETE FROM "+TABLE+" WHERE id=? AND principal_id=?",(row["id"],pid)).rowcount!=1:
                raise PermissionError("external erasure compare failed")
    return len(rows)
