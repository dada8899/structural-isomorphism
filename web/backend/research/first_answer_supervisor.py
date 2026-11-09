"""Main-owned consumer for persisted local first-answer jobs.

A live worker session supplies the cross-process lock and the durable claim
fence. This module never persists identity credentials or replays a claim.
"""
import threading
import time

from pydantic import ValidationError

from .errors import ResearchError
from .first_answer import AnswerBody
from .local_first_answer import produce_background_answer

_POLL_SECONDS = 0.4
_STATE_CHECK_SECONDS = 0.25


class _JobCancellation:
    def __init__(self, stopping, worker, claim):
        self._stopping = stopping
        self._worker = worker
        self._claim = claim
        self._next = 0.0
        self._cancelled = False

    def is_set(self):
        if self._stopping.is_set() or self._cancelled:
            return True
        now = time.monotonic()
        if now >= self._next:
            self._next = now + _STATE_CHECK_SECONDS
            try:
                self._cancelled = not self._worker.is_current(self._claim)
            except Exception:
                # Without a readable durable fence no result may be accepted.
                self._cancelled = True
        return self._cancelled


class FirstAnswerSupervisor:
    def __init__(self, service, search):
        self._service, self._search = service, search
        self._stopping, self._wake = threading.Event(), threading.Event()
        self._ready, self._entered = threading.Event(), threading.Event()
        self._thread = threading.Thread(target=self._run, name="structure-first-answer", daemon=True)

    def start(self):
        self._thread.start()
        self._entered.wait(2)
        return self

    @property
    def ready(self):
        return self._ready.is_set() and not self._stopping.is_set()

    def notify(self):
        self._wake.set()

    def close(self, *, deadline):
        self._stopping.set()
        self._wake.set()
        self._thread.join(max(0.0, deadline - time.monotonic()))
        if self._thread.is_alive():
            raise RuntimeError("first answer worker retirement uncertain")

    def _run(self):
        try:
            from .first_answer_queue import worker_session
            with worker_session(self._service) as worker:
                self._ready.set()
                self._entered.set()
                while not self._stopping.is_set():
                    item = worker.claim_next()
                    if item is None:
                        self._wake.wait(_POLL_SECONDS)
                        self._wake.clear()
                        continue
                    claim, question = item
                    self._run_claim(worker, claim, question)
        except Exception:
            # Leave durable state as observed. The next verified owner of the
            # worker lock reconciles a running claim as interrupted.
            pass
        finally:
            self._ready.clear()
            self._entered.set()

    def _run_claim(self, worker, claim, question):
        cancel = _JobCancellation(self._stopping, worker, claim)
        result = produce_background_answer(question, self._search, cancel=cancel)
        if cancel.is_set():
            if not self._stopping.is_set():
                # Even when DELETE already retired the durable row, the
                # worker session must release its in-memory claim.
                worker.finish(claim, reason="unavailable")
            return
        if result["status"] == "answered":
            try:
                answer = AnswerBody(**result["content"])
            except (ValidationError, KeyError, TypeError):
                worker.finish(claim, reason="invalid_answer")
            else:
                worker.finish(claim, answer=answer)
        elif result["status"] == "insufficient":
            reason = "needs_clarification" if result.get("reason") == "needs_clarification" else "insufficient"
            if reason == "needs_clarification":
                try:
                    worker.finish(claim, reason=reason, question=result.get("question"))
                except (ValueError, ResearchError) as error:
                    if isinstance(error, ResearchError) and error.code != "INPUT_INVALID":
                        raise
                    worker.finish(claim, reason="invalid_answer")
            else:
                worker.finish(claim, reason=reason)
        else:
            worker.finish(claim, reason="unavailable")


_active = {}
_active_lock = threading.Lock()


def activate(app, service, search):
    worker = FirstAnswerSupervisor(service, search)
    with _active_lock:
        if id(app) in _active:
            raise RuntimeError("first answer supervisor already active")
        _active[id(app)] = (app, worker)
    try:
        return worker.start()
    except BaseException:
        with _active_lock:
            _active.pop(id(app), None)
        raise


def current(app):
    with _active_lock:
        entry = _active.get(id(app))
    return entry[1] if entry and entry[0] is app and entry[1].ready else None


def retire(app, worker, *, deadline):
    # Withdraw admission before closing the thread or its search resource.
    with _active_lock:
        if _active.get(id(app)) == (app, worker):
            del _active[id(app)]
    worker.close(deadline=deadline)
