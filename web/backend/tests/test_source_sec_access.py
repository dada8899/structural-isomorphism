"""Pure negative ports/metadata/timing controls; none is a native DOC grant."""
import os
import threading
from types import SimpleNamespace

import pytest

from research import source_sec_access as sec


def test_public_ports_never_adopt_a_caller_path_uid_bool_or_receipt(tmp_path):
    fake = SimpleNamespace(path=tmp_path, uid=os.geteuid(), ready=True)
    for action in (lambda: sec.attach(fake), lambda: sec._Governor(fake),
                   lambda: sec.wait_before_claim(fake), lambda: sec.cleanup_completed(fake),
                   lambda: sec.begin_request(fake, fake, fake), lambda: sec.finish_request(fake, True),
                   lambda: sec.retire(fake), lambda: sec.close(fake, 123.)):
        with pytest.raises((TypeError, RuntimeError, PermissionError)):
            action()


def test_metadata_rejects_symlink_hardlink_mode_and_wrong_uid(tmp_path):
    lock = tmp_path / 'lock'
    lock.touch(mode=0o600)
    assert sec._regular(lock.stat()) == (lock.stat().st_dev, lock.stat().st_ino)
    link = tmp_path / 'link'
    link.symlink_to(lock)
    with pytest.raises(RuntimeError): sec._regular(link.lstat())
    link.unlink(); os.link(lock, link)
    with pytest.raises(RuntimeError): sec._regular(lock.stat())
    link.unlink(); lock.chmod(0o640)
    with pytest.raises(RuntimeError): sec._regular(lock.stat())
    # A pure stat-record check; no chown of a real file or unowned system target.
    info = lock.stat()
    with pytest.raises(RuntimeError):
        sec._regular(SimpleNamespace(st_mode=0o100600, st_uid=os.geteuid()+1,
            st_nlink=1, st_dev=info.st_dev, st_ino=info.st_ino))


def test_cadence_requires_real_checkpoint_and_one_second_after_it():
    timing = sec._Cadence()
    with pytest.raises(PermissionError): timing.delay(50.)
    timing.cleared(50.)
    assert timing.delay(50.) == 1.
    assert timing.delay(50.75) == .25
    assert timing.delay(51.) == 0.
    with pytest.raises(RuntimeError): timing.cleared(52.)
    timing.flight = object()
    with pytest.raises(PermissionError): timing.delay(500.)
    timing.flight = None; timing.uncertain = True
    with pytest.raises(PermissionError): timing.delay(500.)


def test_original_stop_event_interrupts_pure_timing_wait():
    stop, entered = threading.Event(), threading.Event()
    done = []
    def wait():
        entered.set(); done.append(stop.wait(30))
    thread = threading.Thread(target=wait)
    thread.start(); assert entered.wait(1)
    stop.set(); thread.join(1)
    assert done == [True] and not thread.is_alive()


def test_pure_oneflight_completion_not_start_sets_next_due_and_unknown_blocks():
    # Pure clock/flight model, not a registered DOC or a transport receipt.
    timing = sec._Cadence(); timing.cleared(10.)
    with pytest.raises(PermissionError): timing.begin(10.99)
    first = timing.begin(11.)
    with pytest.raises(PermissionError): timing.begin(100.)
    with pytest.raises(PermissionError): timing.finished(object(), 12.)
    timing.finished(first, 14.)  # An index or failed HTTP also consumes a flight.
    assert timing.delay(14.) == 1.
    with pytest.raises(PermissionError): timing.begin(14.99)
    second = timing.begin(15.)
    timing.finished(second, 16.)
    assert timing.delay(16.) == 1.
    third = timing.begin(17.)
    timing.unknown(third)
    with pytest.raises(PermissionError): timing.begin(100.)
    with pytest.raises(PermissionError): timing.finished(third, 100.)
