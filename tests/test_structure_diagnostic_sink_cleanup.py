"""Tiny in-memory controls: no Source imports, browser, server or network."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
import signal
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/structure_analyze_mobile_diagnostic_once.py'
SPEC = importlib.util.spec_from_file_location('sink_collector_under_test', SOURCE)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class Writer:
    def __init__(self): self.records = {}
    def write_json(self, name, value, **kwargs):
        if name in self.records: raise AssertionError('exclusive evidence overwritten')
        self.records[name] = copy.deepcopy(value)
    def write_chunks(self, name, chunks):
        if name in self.records: raise AssertionError('exclusive evidence overwritten')
        self.records[name] = b''.join(chunks)


class Browser:
    def __init__(self, fail=False): self.connected, self.fail, self.calls = True, fail, 0
    def is_connected(self): return self.connected
    def close(self):
        self.calls += 1
        if self.fail: raise RuntimeError('synthetic close failure')
        self.connected = False


class Page:
    def __init__(self, fail=False): self.fail = fail
    def evaluate(self, expression):
        if self.fail: raise RuntimeError('synthetic snapshot failure')
        return {'timeOrigin':1000, 'now':100, 'fcp':0,
                'longTasks':[{'start':0, 'duration':100}],
                'click':dict.fromkeys(('count','pointerDown','pointerUp','at'),0),
                'navigation':None, 'resources':[]}
    def wait_for_timeout(self, milliseconds):
        raise AssertionError('synthetic terminal must be delivered synchronously')


class CDP:
    def __init__(self, capture, fail=False): self.capture, self.fail, self.detached = capture, fail, False
    def send(self, method):
        if self.fail: raise RuntimeError('synthetic trace failure')
        self.capture.on_data({'value':[{'name':'RunTask','ph':'X','pid':1,'tid':1,'ts':100,'dur':100}]})
        self.capture.on_complete({'dataLossOccurred':False})
    def detach(self): self.detached = True


class Beta:
    @staticmethod
    def _checkpoint_run_evidence(sample): return copy.deepcopy(sample)


class Perf:
    @staticmethod
    def compute_tbt(tasks, start, end):
        return sum(max(0, min(t['start']+t['duration'],end)-max(t['start'],start)-50) for t in tasks)


def capture(trace_failure=False, snapshot_failure=False, browser_failure=False):
    c = collector.Capture(Writer(), Beta(), Perf(), time.monotonic()+120)
    c.page, c.browser = Page(snapshot_failure), Browser(browser_failure)
    c.cdp, c.tracing = CDP(c, trace_failure), True
    return c


def pending(passed=False, **extra):
    sample = {'run_index':1,'audit_status':'passed' if passed else 'failed',
              'cleanup_status':'pending'}
    if not passed: sample.update(stage='navigation',error='navigation_failed',error_detail={'code':'navigation_failed','type':'Error'})
    sample.update(extra)
    return sample


def result(verified=False):
    return {'status':'UNKNOWN','error':None if verified else 'diagnostic_incomplete_no_retry',
            'primary_failure':None,'secondary_errors':[], 'capture_evidence_verified':verified,
            'source_postflight_verified':False,'server_closed':False,'browser_closed':False,
            'driver_closed':False,'work_removed':False}


class SinkControls(unittest.TestCase):
    def test_navigation_failure_without_metric_preserves_primary_and_final(self):
        c = capture(); original = pending(); c.sink(original)
        self.assertEqual(c.writer.records['audit-pending.json']['sample'], original)
        self.assertFalse(c.metric_verified)
        self.assertNotIn('tbt-contributions.json', c.writer.records)
        self.assertNotIn('browser-window.json', c.writer.records)
        c.browser.close(); final = {**original,'cleanup_status':'passed'}; c.sink(final)
        self.assertEqual(c.final, final)
        self.assertEqual(c.primary_failure['error'], 'navigation_failed')
        self.assertTrue(c.close())
        self.assertTrue(c.writer.records['trace-terminal.json']['trace_complete'])

    def test_failed_zero_metric_is_never_accepted(self):
        c = capture(); c.sink(pending(tbt_ms=0))
        self.assertFalse(c.metric_verified)
        self.assertNotIn('tbt-contributions.json', c.writer.records)

    def test_trace_failure_does_not_suppress_final_or_native_close(self):
        c = capture(trace_failure=True); c.sink(pending())
        c.browser.close(); c.sink({**pending(),'cleanup_status':'passed'})
        self.assertEqual(c.primary_failure['error'], 'navigation_failed')
        self.assertIsNotNone(c.final)
        self.assertIn('trace_finalize_unknown', c.errors)
        self.assertTrue(c.close())

    def test_success_metric_path_keeps_original_contributions(self):
        c = capture(); c.sink(pending(True,tbt_ms=50.0))
        record = c.writer.records['tbt-contributions.json']
        self.assertEqual(record['recomputed_tbt_ms'],50.0)
        self.assertTrue(record['matches_original_sample'])
        self.assertEqual(record['tasks'],[{'start':0,'duration':100,'clipped_overlap':100,'blocking_ms':50}])
        self.assertTrue(c.metric_verified)
        self.assertTrue(c.writer.records['trace-terminal.json']['trace_complete'])
        self.assertEqual(c.errors,[])

    def test_metric_mismatch_stays_unknown_but_allows_final(self):
        c = capture(); c.sink(pending(True,tbt_ms=51.0))
        self.assertFalse(c.metric_verified)
        self.assertIn('capture_incomplete',c.errors)
        c.browser.close(); c.sink({**pending(True,tbt_ms=51.0),'cleanup_status':'passed'})
        self.assertIsNotNone(c.final)
        self.assertFalse(c.writer.records['trace-terminal.json']['trace_complete'])

    def test_snapshot_error_still_attempts_trace_and_native_close(self):
        c = capture(snapshot_failure=True); c.sink(pending(True,tbt_ms=50.0))
        self.assertIn('capture_incomplete',c.errors)
        self.assertIn('trace-terminal.json',c.writer.records)
        self.assertTrue(c.close())

    def test_browser_close_error_is_independent_of_primary(self):
        c = capture(browser_failure=True); c.sink(pending())
        self.assertFalse(c.close())
        self.assertEqual(c.primary_failure['error'],'navigation_failed')
        self.assertIn('browser_close_unknown',c.errors)


class RetirementControls(unittest.TestCase):
    def exact_run_boundary(self, state, interrupt):
        """Execute the real final assignment/except, without running Source."""
        tree=ast.parse(SOURCE.read_bytes())
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        handler=next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='interrupt')
        body=next(n for n in run.body if isinstance(n,ast.Try))
        assignment=body.body[-1]
        self.assertIsInstance(assignment,ast.Assign)
        self.assertEqual(ast.literal_eval(assignment.targets[0].slice),'capture_evidence_verified')
        self.assertIs(ast.literal_eval(assignment.value),True)
        actions=[copy.deepcopy(assignment)]
        if interrupt:actions+=ast.parse('os.kill(os.getpid(), signal.SIGINT)').body
        trial=ast.Try(body=actions,handlers=copy.deepcopy(body.handlers),orelse=[],finalbody=[])
        namespace={'result':state,'os':os,'signal':signal}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(handler)],type_ignores=[])),'exact-run-handler','exec'),namespace)
        previous=signal.signal(signal.SIGINT,namespace['interrupt'])
        try:exec(compile(ast.fix_missing_locations(ast.Module(body=[trial],type_ignores=[])),'exact-run-boundary','exec'),namespace)
        finally:signal.signal(signal.SIGINT,previous)

    def retire(self, state, c, postflight_failure=False, driver_failure=False, server_failure=False):
        calls=[]
        class Driver:
            def stop(self):
                calls.append('driver')
                if driver_failure: raise RuntimeError('synthetic driver failure')
        def postflight(*args):
            calls.append('postflight')
            if postflight_failure: raise RuntimeError('synthetic source drift')
        def server(*args):
            calls.append('server')
            return not server_failure
        def work(*args): calls.append('work'); return True
        with patch.object(collector,'source_postflight',postflight), patch.object(collector,'stop_server',server), patch.object(collector,'cleanup_work',work):
            collector.finalize_diagnostic(state,c,Driver(),object(),None,None,None,('original',),time.monotonic()+120)
        return calls

    def test_primary_failure_still_checks_source_and_retires_resources(self):
        c=capture(); c.sink(pending()); state=result(); calls=self.retire(state,c)
        self.assertEqual(state['primary_failure']['error'],'navigation_failed')
        self.assertEqual(state['error'],'diagnostic_incomplete_no_retry')
        self.assertEqual(state['status'],'UNKNOWN')
        self.assertTrue(state['source_postflight_verified'])
        self.assertTrue(all(state[k] for k in ['browser_closed','driver_closed','server_closed','work_removed']))
        self.assertEqual(set(calls),{'postflight','driver','server','work'})

    def test_postflight_failure_keeps_primary_and_closes_other_resources(self):
        c=capture(); c.sink(pending()); state=result(); calls=self.retire(state,c,postflight_failure=True)
        self.assertEqual(state['primary_failure']['error'],'navigation_failed')
        self.assertFalse(state['source_postflight_verified'])
        self.assertIn('source_postflight_unknown',state['secondary_errors'])
        self.assertEqual(state['error'],'diagnostic_incomplete_no_retry')
        self.assertEqual(set(calls),{'postflight','driver','server','work'})

    def test_browser_driver_server_failures_do_not_cancel_independent_attempts(self):
        c=capture(browser_failure=True); c.sink(pending()); state=result()
        calls=self.retire(state,c,driver_failure=True,server_failure=True)
        self.assertEqual(set(calls),{'postflight','driver','server'})
        self.assertFalse(state['work_removed'])
        self.assertEqual(state['primary_failure']['error'],'navigation_failed')
        self.assertEqual(state['status'],'UNKNOWN')

    def test_complete_requires_all_original_capture_and_retirement_evidence(self):
        c=capture(); c.sink(pending(True,tbt_ms=50.0)); state=result(True)
        self.retire(state,c)
        self.assertEqual(state['status'],'diagnostic_capture_complete_not_a_grade')
        state=result(False); self.retire(state,c)
        self.assertEqual(state['status'],'UNKNOWN')

    def test_exact_after_verified_SIGINT_never_becomes_complete(self):
        c=capture();c.sink(pending(True,tbt_ms=50.0));state=result(True)
        state['capture_evidence_verified']=False
        self.exact_run_boundary(state,interrupt=True)
        self.assertTrue(state['capture_evidence_verified'])
        self.assertEqual(state['error'],'diagnostic_incomplete_no_retry')
        self.retire(state,c)
        self.assertEqual(state['status'],'UNKNOWN')
        self.assertEqual(state['error'],'diagnostic_incomplete_no_retry')
        self.assertTrue(all(state[k] for k in ('source_postflight_verified','browser_closed','driver_closed','server_closed','work_removed')))
        self.assertEqual(0 if state['status']=='diagnostic_capture_complete_not_a_grade' else 2,2)

    def test_exact_without_interrupt_keeps_original_success(self):
        c=capture();c.sink(pending(True,tbt_ms=50.0));state=result(True)
        state['capture_evidence_verified']=False
        self.exact_run_boundary(state,interrupt=False)
        self.retire(state,c)
        self.assertEqual(state['status'],'diagnostic_capture_complete_not_a_grade')
        self.assertIsNone(state['error'])

    def test_existing_primary_failure_is_sticky_without_capture_primary(self):
        c=capture();c.sink(pending(True,tbt_ms=50.0));state=result(True)
        primary={'stage':'cancelled','error':'previous_failure'}
        state['primary_failure']=dict(primary)
        self.retire(state,c)
        self.assertEqual(state['primary_failure'],primary)
        self.assertEqual(state['status'],'UNKNOWN')

    def test_expired_action_never_launches(self):
        called=[]
        with self.assertRaises(collector.Refused):
            collector.bounded_action(time.monotonic()-1,lambda:called.append(True))
        self.assertEqual(called,[])

    def test_expired_capture_skips_source_but_still_uses_bounded_retirement(self):
        c=capture(); c.sink(pending()); state=result(); calls=[]
        class Driver:
            def stop(self): calls.append('driver')
        with patch.object(collector,'source_postflight',lambda *a:calls.append('postflight')), patch.object(collector,'stop_server',lambda *a:calls.append('server') or True), patch.object(collector,'cleanup_work',lambda *a:True):
            collector.finalize_diagnostic(state,c,Driver(),object(),None,None,None,('original',),time.monotonic()-.01)
        self.assertNotIn('postflight',calls)
        self.assertEqual(set(calls),{'driver','server'})
        self.assertTrue(state['browser_closed'])
        self.assertEqual(state['primary_failure']['error'],'navigation_failed')
        self.assertEqual(state['status'],'UNKNOWN')

    def test_alarm_interrupts_slow_phase_without_renewing_capture(self):
        handler=signal.getsignal(signal.SIGALRM); timer=signal.getitimer(signal.ITIMER_REAL)
        try:
            with self.assertRaises(collector.Refused):
                collector.bounded_action(time.monotonic()+.01,lambda:time.sleep(1))
            self.assertIs(signal.getsignal(signal.SIGALRM),handler)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,handler)
            signal.setitimer(signal.ITIMER_REAL,*timer)

    def test_nested_alarm_restores_remaining_absolute_budget(self):
        old_handler=signal.getsignal(signal.SIGALRM); old_timer=signal.getitimer(signal.ITIMER_REAL)
        try:
            signal.setitimer(signal.ITIMER_REAL,5)
            before=signal.getitimer(signal.ITIMER_REAL)[0]
            self.assertEqual(collector.bounded_action(time.monotonic()+1,lambda:'ok'),'ok')
            after=signal.getitimer(signal.ITIMER_REAL)[0]
            self.assertGreater(after,4)
            self.assertLessEqual(after,before)
            self.assertIs(signal.getsignal(signal.SIGALRM),old_handler)
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
            signal.setitimer(signal.ITIMER_REAL,*old_timer)


if __name__ == '__main__': unittest.main()
