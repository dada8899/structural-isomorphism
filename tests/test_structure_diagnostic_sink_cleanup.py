"""Tiny in-memory controls: no Source imports, browser, server or network."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, urljoin

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


class NavigationObserverControls(unittest.TestCase):
    class Error(Exception): pass
    class TimeoutError(Exception): pass
    CANARY='SECRET_CANARY_do_not_export_cookie_password_token'

    def bind(self, behavior, writer=None, error_type=None, timeout_type=None):
        class Target:
            def goto(self,*args,**kwargs):return behavior(*args,**kwargs)
        target=Target(); c=capture(); writer=writer or Writer()
        collector.bind_navigation_observer(target,writer,c,time.monotonic()+120,error_type or self.Error,timeout_type or self.TimeoutError)
        return target,writer,c

    def record(self,writer):
        record=writer.records['navigation-outcome.json']
        self.assertEqual(set(record),{'classification','kind','outcome','calls_observed','exception_type','failure_category'})
        self.assertEqual(record['calls_observed'],1)
        raw=json.dumps(record)
        self.assertNotIn(self.CANARY,raw)
        self.assertNotIn('http',raw)
        self.assertLessEqual(len(raw.encode()),512)
        return record

    def test_success_preserves_single_call_all_arguments_and_return_identity(self):
        response=object();seen=[]
        def original(*args,**kwargs):seen.append((args,kwargs));return response
        target,writer,c=self.bind(original)
        url='http://127.0.0.1/analyze.html?'+self.CANARY
        self.assertIs(target.goto(url,wait_until='domcontentloaded',timeout=30000),response)
        self.assertEqual(seen,[((url,),{'wait_until':'domcontentloaded','timeout':30000})])
        self.assertEqual(c.errors,[])
        record=self.record(writer);self.assertEqual(record['outcome'],'returned');self.assertIsNone(record['failure_category'])

    def test_error_identity_and_secret_canary_are_preserved_only_in_original(self):
        error=self.Error('Page.goto: net::ERR_ABORTED at https://example.invalid/'+self.CANARY)
        def original(*args,**kwargs):raise error
        target,writer,c=self.bind(original)
        with self.assertRaises(self.Error) as raised:target.goto('ignored',timeout=30000)
        self.assertIs(raised.exception,error)
        record=self.record(writer);self.assertEqual(record['exception_type'],'Error');self.assertEqual(record['failure_category'],'net::ERR_ABORTED')

    def test_timeout_is_finite_without_exporting_message(self):
        error=self.TimeoutError(self.CANARY)
        target,writer,c=self.bind(lambda *a,**k:(_ for _ in ()).throw(error))
        with self.assertRaises(self.TimeoutError) as raised:target.goto('ignored')
        self.assertIs(raised.exception,error)
        self.assertEqual(self.record(writer)['failure_category'],'timeout')

    def test_unknown_class_is_other_without_even_stringifying_it(self):
        class UnknownError(Exception):
            def __str__(self):raise AssertionError('unknown exception was stringified')
        error=UnknownError();target,writer,c=self.bind(lambda *a,**k:(_ for _ in ()).throw(error))
        with self.assertRaises(UnknownError) as raised:target.goto('ignored')
        self.assertIs(raised.exception,error)
        record=self.record(writer);self.assertEqual(record['exception_type'],'other');self.assertEqual(record['failure_category'],'other')

    def test_unknown_network_code_and_prefixed_canary_are_other(self):
        for text in ['net::ERR_PRIVATE_'+self.CANARY,'net::ERR_ABORTED_'+self.CANARY]:
            with self.subTest(text_kind='unknown_network'):
                error=self.Error(text);target,writer,c=self.bind(lambda *a,**k:(_ for _ in ()).throw(error))
                with self.assertRaises(self.Error):target.goto('ignored')
                self.assertEqual(self.record(writer)['failure_category'],'other')

    def test_known_non_network_categories_remain_finite(self):
        for message,expected in [('Target page, context or browser has been closed','target_closed'),('Navigation interrupted by another navigation','navigation_interrupted'),('Protocol error '+self.CANARY,'other')]:
            with self.subTest(category=expected):
                error=self.Error(message);target,writer,c=self.bind(lambda *a,**k:(_ for _ in ()).throw(error))
                with self.assertRaises(self.Error):target.goto('ignored')
                self.assertEqual(self.record(writer)['failure_category'],expected)

    def test_original_cancellation_object_is_not_swallowed(self):
        for error in [KeyboardInterrupt(self.CANARY),SystemExit(self.CANARY)]:
            with self.subTest(cancellation=type(error).__name__):
                target,writer,c=self.bind(lambda *a,**k:(_ for _ in ()).throw(error))
                try:target.goto('ignored')
                except BaseException as raised:self.assertIs(raised,error)
                else:self.fail('original cancellation swallowed')
                self.assertEqual(self.record(writer)['failure_category'],'navigation_interrupted')

    def test_receipt_failure_cannot_replace_original_error_or_success(self):
        class BrokenWriter(Writer):
            def write_json(self,*args,**kwargs):raise RuntimeError(self.CANARY if hasattr(self,'CANARY') else 'synthetic storage error')
        error=self.Error('net::ERR_FAILED '+self.CANARY)
        target,writer,c=self.bind(lambda *a,**k:(_ for _ in ()).throw(error),BrokenWriter())
        with self.assertRaises(self.Error) as raised:target.goto('ignored')
        self.assertIs(raised.exception,error);self.assertIn('navigation_observer_receipt_unknown',c.errors)
        response=object();target,writer,c=self.bind(lambda *a,**k:response,BrokenWriter())
        self.assertIs(target.goto('ignored'),response);self.assertIn('navigation_observer_receipt_unknown',c.errors)

    def test_receipt_cancellation_wins_with_real_sdk_error_and_safe_primary(self):
        from playwright.sync_api import Error as SDKError, TimeoutError as SDKTimeout
        for cancellation in (KeyboardInterrupt(self.CANARY),SystemExit(self.CANARY)):
            with self.subTest(cancellation=type(cancellation).__name__):
                original=SDKError('Page.goto: net::ERR_ABORTED at https://example.invalid/'+self.CANARY)
                class CancelWriter(Writer):
                    def write_json(self,name,value,**kwargs):
                        self.attempted=copy.deepcopy(value)
                        raise cancellation
                calls=[]
                def goto(*args,**kwargs):calls.append((args,kwargs));raise original
                target,writer,c=self.bind(goto,CancelWriter(),SDKError,SDKTimeout)
                caught=None
                try:target.goto('synthetic-local-only',wait_until='domcontentloaded',timeout=30000)
                except BaseException as raised:caught=raised
                self.assertTrue(caught is cancellation,'receipt cancellation identity must take priority')
                self.assertTrue(caught.__context__ is original,'original SDK exception identity must remain in context')
                self.assertEqual(len(calls),1)
                self.assertEqual(c.primary_failure,{'stage':'navigation','error':'navigation_failed','error_detail':{'code':'navigation_failed','type':'Error'}})
                self.assertIn('navigation_observer_receipt_unknown',c.errors)
                raw=json.dumps({'attempted':writer.attempted,'primary':c.primary_failure,'errors':c.errors})
                self.assertNotIn(self.CANARY,raw)
                self.assertNotIn('https://',raw)
                self.assertNotIn('traceback',raw)

    def test_real_sdk_error_keeps_identity_for_ordinary_receipt_failure(self):
        from playwright.sync_api import Error as SDKError, TimeoutError as SDKTimeout
        original=SDKError('net::ERR_FAILED '+self.CANARY)
        class BrokenWriter(Writer):
            def write_json(self,*args,**kwargs):raise RuntimeError('synthetic receipt failure')
        def goto(*args,**kwargs):raise original
        target,writer,c=self.bind(goto,BrokenWriter(),SDKError,SDKTimeout)
        caught=None
        try:target.goto('synthetic-local-only',timeout=30000)
        except BaseException as raised:caught=raised
        self.assertTrue(caught is original,'ordinary receipt failure must preserve original SDK error identity')
        self.assertIn('navigation_observer_receipt_unknown',c.errors)
        self.assertEqual(writer.records,{})

    def test_classifier_cancellation_wins_with_real_sdk_error_context(self):
        from playwright.sync_api import Error as SDKError, TimeoutError as SDKTimeout
        for cancellation in (KeyboardInterrupt(self.CANARY),SystemExit(self.CANARY)):
            with self.subTest(cancellation=type(cancellation).__name__):
                original=SDKError('net::ERR_ABORTED '+self.CANARY)
                def bad_str(error):raise cancellation
                def goto(*args,**kwargs):raise original
                target,writer,c=self.bind(goto,Writer(),SDKError,SDKTimeout)
                caught=None
                with patch.object(SDKError,'__str__',bad_str):
                    try:target.goto('synthetic-local-only',timeout=30000)
                    except BaseException as raised:caught=raised
                self.assertTrue(caught is cancellation,'classifier cancellation identity must take priority')
                self.assertTrue(caught.__context__ is original,'original SDK error must remain in context')
                self.assertEqual(writer.records,{})
                self.assertEqual(c.primary_failure,{'stage':'navigation','error':'navigation_failed','error_detail':{'code':'navigation_failed','type':'Error'}})
                self.assertNotIn(self.CANARY,json.dumps({'primary':c.primary_failure,'errors':c.errors}))

    def test_classifier_real_self_SIGINT_propagates_and_restores_handler(self):
        from playwright.sync_api import Error as SDKError, TimeoutError as SDKTimeout
        original=SDKError('net::ERR_ABORTED '+self.CANARY);cancellation=KeyboardInterrupt(self.CANARY)
        previous=signal.getsignal(signal.SIGINT);previous_trace=sys.gettrace()
        def interrupt(signum,frame):raise cancellation
        def interrupted_str(error):
            os.kill(os.getpid(),signal.SIGINT)
            raise AssertionError('self signal must interrupt stringification')
        def goto(*args,**kwargs):raise original
        target,writer,c=self.bind(goto,Writer(),SDKError,SDKTimeout);caught=None
        try:
            signal.signal(signal.SIGINT,interrupt)
            with patch.object(SDKError,'__str__',interrupted_str):
                try:target.goto('synthetic-local-only',timeout=30000)
                except BaseException as raised:caught=raised
        finally:signal.signal(signal.SIGINT,previous)
        self.assertTrue(caught is cancellation,'real self SIGINT must propagate with original identity')
        self.assertTrue(caught.__context__ is original,'real self SIGINT must retain original SDK error context')
        self.assertIs(signal.getsignal(signal.SIGINT),previous)
        self.assertIs(sys.gettrace(),previous_trace)
        self.assertEqual(writer.records,{})
        self.assertEqual(c.primary_failure['error_detail'],{'code':'navigation_failed','type':'Error'})

    def test_ordinary_real_sdk_stringification_failure_is_safe_other(self):
        from playwright.sync_api import Error as SDKError, TimeoutError as SDKTimeout
        original=SDKError('net::ERR_FAILED '+self.CANARY)
        def bad_str(error):raise RuntimeError(self.CANARY)
        def goto(*args,**kwargs):raise original
        target,writer,c=self.bind(goto,Writer(),SDKError,SDKTimeout);caught=None
        with patch.object(SDKError,'__str__',bad_str):
            try:target.goto('synthetic-local-only',timeout=30000)
            except BaseException as raised:caught=raised
        self.assertTrue(caught is original,'ordinary stringification error must not replace original SDK exception')
        record=self.record(writer)
        self.assertEqual(record['outcome'],'raised')
        self.assertEqual(record['exception_type'],'Error')
        self.assertEqual(record['failure_category'],'other')

    def test_expired_observer_budget_does_not_repeat_or_alter_goto(self):
        calls=[];response=object()
        class Target:
            def goto(self,*args,**kwargs):calls.append(1);return response
        target=Target();writer=Writer();c=capture()
        collector.bind_navigation_observer(target,writer,c,time.monotonic()-1,self.Error,self.TimeoutError)
        self.assertIs(target.goto('ignored',timeout=30000),response)
        self.assertEqual(calls,[1]);self.assertEqual(writer.records,{})
        self.assertIn('navigation_observer_receipt_unknown',c.errors)


class FixtureNavigationControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read immutable contract data through AST only; never import Source.
        beta=SOURCE.with_name('beta_perf_audit.py').read_bytes()
        perf=SOURCE.with_name('perf_audit.py').read_bytes()
        assert hashlib.sha256(beta).hexdigest()=='e3360ea983d06d88908afa95cff43e714ea0d969f2a7da1dfca2d31b0d6655a4'
        assert hashlib.sha256(perf).hexdigest()=='6bca7e272d7c534b64fcd62cb6898154cd829047054caa04202eb7f7858b1433'
        bt,pt=ast.parse(beta),ast.parse(perf)
        pages=next(n.value for n in bt.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='PAGES')
        case=next(v for k,v in zip(pages.keys,pages.values) if ast.literal_eval(k)=='analyze')
        cls.relative=ast.literal_eval(case.args[0])
        audit=next(n for n in pt.body if isinstance(n,ast.FunctionDef) and n.name=='audit_one')
        cls.concat=next(n.value for n in ast.walk(audit) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='url' for t in n.targets))
        cls.goto=next(n for n in ast.walk(audit) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='page' and n.func.attr=='goto')

    def test_actual_relative_contract_reproduces_original_defect_then_normalizes(self):
        self.assertFalse(self.relative.startswith('/'))
        self.assertIsInstance(self.concat,ast.JoinedStr)
        self.assertEqual([v.value.id for v in self.concat.values],['base_url','path'])
        with self.assertRaises(ValueError):urlsplit(collector.BASE+self.relative).port
        base=collector.fixture_audit_base(collector.BASE,self.relative)
        target=urlsplit(base+self.relative)
        self.assertEqual((target.scheme,target.hostname,target.port,target.path),('http','127.0.0.1',4173,'/analyze.html'))
        self.assertEqual(target.query,urlsplit(self.relative).query)
        self.assertEqual(base+self.relative,urljoin(base,self.relative))

    def test_with_and_without_terminal_slash_are_equivalent(self):
        self.assertEqual(collector.fixture_audit_base(collector.BASE,self.relative),'http://127.0.0.1:4173/')
        self.assertEqual(collector.fixture_audit_base(collector.BASE+'/',self.relative),'http://127.0.0.1:4173/')
        self.assertEqual(collector.fixture_audit_base(collector.BASE,self.relative),collector.BASE.rstrip('/')+'/')

    def test_authoritative_goto_shape_is_one_call_with_original_query_and_timeout(self):
        base=collector.fixture_audit_base(collector.BASE,self.relative);seen=[];response=object()
        class Target:
            def goto(self,*args,**kwargs):seen.append((args,kwargs));return response
        self.assertEqual([k.arg for k in self.goto.keywords],['wait_until','timeout'])
        kwargs={k.arg:ast.literal_eval(k.value) for k in self.goto.keywords}
        self.assertIs(Target().goto(base+self.relative,**kwargs),response)
        self.assertEqual(seen,[((urljoin(base,self.relative),),{'wait_until':'domcontentloaded','timeout':30000})])

    def test_run_handoff_uses_normalized_base_and_unchanged_source_case(self):
        run=next(n for n in ast.parse(SOURCE.read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='run')
        assignment=next(n for n in ast.walk(run) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='normalized_base' for t in n.targets))
        self.assertEqual(assignment.value.func.id,'fixture_audit_base')
        self.assertEqual(ast.dump(assignment.value.args[0]),ast.dump(ast.Name(id='BASE',ctx=ast.Load())))
        self.assertEqual(ast.dump(assignment.value.args[1]),ast.dump(ast.Attribute(value=ast.Name(id='case',ctx=ast.Load()),attr='path',ctx=ast.Load())))
        audit=next(n for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='perf' and n.func.attr=='audit_one')
        self.assertEqual(audit.args[1].id,'normalized_base')
        self.assertEqual(ast.dump(audit.args[2]),ast.dump(assignment.value.args[1]))
        self.assertEqual(next(k.value.value for k in audit.keywords if k.arg=='runs'),1)

    def test_scheme_host_port_userinfo_and_base_path_escape_are_refused(self):
        bad=['https://127.0.0.1:4173','http://example.invalid:4173','http://localhost:4173',
             'http://127.0.0.1:4174','http://127.0.0.1:80','http://127.0.0.1:04173',
             'http://user@127.0.0.1:4173','http://127.0.0.1:4173/app',
             'http://127.0.0.1:4173//','http://127.0.0.1:4173?x=1',
             'http://127.0.0.1:4173#fragment',' http://127.0.0.1:4173',
             'http://127.0.0.1:4173\n','http://[']
        for base in bad:
            with self.subTest(base_kind='noncanonical_or_escaped'):
                with self.assertRaises(collector.Refused):collector.fixture_audit_base(base,self.relative)

    def test_absolute_or_cross_origin_page_targets_are_refused(self):
        bad=['https://example.invalid/analyze.html','http://127.0.0.1:4173/analyze.html',
             '//example.invalid/analyze.html','//127.0.0.1:4174/analyze.html',
             'javascript:alert(1)','\\\\example.invalid\\analyze.html']
        for relative in bad:
            with self.subTest(target_kind='absolute_or_escape'):
                with self.assertRaises(collector.Refused):collector.fixture_audit_base(collector.BASE,relative)

    def test_double_slash_traversal_or_swallowed_path_is_refused(self):
        bad=['/analyze.html','//analyze.html','../analyze.html','assets/../analyze.html',
             '%2e%2e/analyze.html','%61nalyze.html','analyze.html/extra','fooanalyze.html',
             'analyze.html#fragment','analyze.html?id=1#fragment','analyze.html?',
             'analyze.html\n','analyze.html\\extra']
        for relative in bad:
            with self.subTest(target_kind='ambiguous_path'):
                with self.assertRaises(collector.Refused):collector.fixture_audit_base(collector.BASE,relative)

    def test_query_bytes_preserved_and_non_strings_fail_closed(self):
        relative='analyze.html?id=a%2Fb&a_id=b%26c'
        base=collector.fixture_audit_base(collector.BASE,relative)
        self.assertEqual(base+relative,'http://127.0.0.1:4173/'+relative)
        for bad in [None,b'analyze.html',42,'']:
            with self.assertRaises(collector.Refused):collector.fixture_audit_base(collector.BASE,bad)
        for bad in [None,b'http://127.0.0.1:4173',42,'']:
            with self.assertRaises(collector.Refused):collector.fixture_audit_base(bad,self.relative)


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
