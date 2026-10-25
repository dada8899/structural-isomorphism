"""Actual Main15 HTTPS browser, stored synthetic Source, canonical Runtime.

The test controller explicitly advances an actually approved native task. There
is no product runner button, installed live authority, public GET or model call.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager, ExitStack
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parents[3]
_spec=importlib.util.spec_from_file_location('evidence_ui_browser_helpers',ROOT/'tests/test_research_browser.py')
helpers=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(helpers)


def ui_candidate():
    """Legal explanatory DTO, never a maturity or actual-model assertion."""
    from research.evidence_method_plan_schemas import EvidenceMethodPlanCandidate
    from web.backend.tests.test_research_evidence_method_native import example
    value=example();gap={'code':'maturity_not_established','detail':'短引不足以核定成熟方法、公式条件或迁移有效性。','evidence_handles':['e1']}
    value['summary']='以下是受控样例中的排队机制候选，仍需独立验证。'
    value['candidates']=[{'candidate_kind':'mechanism','label':'到达集中与等待累积','mechanism_hypothesis':'任务到达集中可能使等待累积；服务时间变化也可能造成同样现象。',
      'method_name':None,'formula_proposal':{'text':'L = λ × W','basis':'unverified_proposal','evidence_handles':[]},
      'evidence_links':[{'handle':'e1','role':'context','proposed_support':'原短引涉及到达、服务差异与等待。','missing_support':'没有给出数学模型、因果识别或适用条件。'}],
      'variable_map':[{'method_variable':'到达过程','target_variable':'任务进入系统的时间分布','rationale':'需要逐项测量后才能比较。','evidence_handles':['e1']}],
      'applicability':[{'condition':'测量边界与等待定义需一致。','evidence_handles':[],'gap':'尚缺真实到达与服务时间序列。'}],
      'competing_explanations':['服务时长或服务能力变化也会影响等待。'],
      'nontransferable':['该短引不能证明目标场景符合特定排队模型。'],
      'counterexamples_or_falsifiers':[{'statement':'若到达分散后等待仍不变，应优先检查服务过程。','evidence_handles':[]}],
      'verification_plan':{'question':'到达集中是否先于等待增加？','measurements':['到达时间、开始服务与完成时间'],'comparison':'比较相近工作量下的集中与分散到达。','primary_outcome':'等待时长分布','falsification':'控制服务时长后关联消失。','stop_rule':'记录缺失或定义不一致时停止推断。','inputs_needed':['同一测量边界的逐项时间记录']},
      'gaps':[gap]}]
    value['gaps']=[gap,{'code':'formula_not_recoverable','detail':'所选短引没有给出公式；公式只是未经核验的提议。','evidence_handles':[]}];value['clarification_questions']=[]
    return EvidenceMethodPlanCandidate.model_validate(value).model_dump(mode='json')


@asynccontextmanager
async def actual_browser(tmp_path,*,eight=False,funded=True,unknown_usage=False,bad_body=False,candidate=False):
    from web.backend.tests.test_research_evidence_method_plan import actual
    from web.backend.tests.test_research_funded_plan import provider
    from web.backend.tests.test_plan_runtime_transport import installed_evidence_runtime
    from web.backend.tests.test_research_evidence_method_native import example
    from web.backend.tests.acceptance import formal_main_browser_service as entry
    from web.backend.tests.acceptance.source_history_fixture import prepared_source_history_eight
    browser=context=None;service=None;primary=None;errors=[]
    facts={'scope':'actual Main15 HTTPS + controlled provider; explicit controller runner, no live model',
           'materials':8 if eight else 1,'historical_loopback_GETs':16 if eight else 2,'public_GETs':0,'model_calls':0,'real_fees':0}
    with ExitStack() as stack:
        if eight:stack.enter_context(patch.object(entry,'prepared_source_history',prepared_source_history_eight))
        service,client,store,actor=stack.enter_context(actual(tmp_path))
        assert len(service.seed.excerpt_refs)==(8 if eight else 1)
        if eight:
            assert service.seed.loopback_requests==16
            assert len({x['excerpt_id'] for x in service.seed.excerpt_refs})==8
            facts['per_task_loopback_GETs']=[material['loopback_gets'] for material in service.seed.materials]
        assert service.retire_source()=='unavailable'
        choices=[{'finish_reason':'stop','message':{'content':'{}' if bad_body else json.dumps(ui_candidate() if candidate else example())}}]
        server,calls=stack.enter_context(provider(choices=choices,unknown_usage=unknown_usage))
        if funded:stack.enter_context(installed_evidence_runtime(store,actor,server))
        bridge=stack.enter_context(service.browser_bridge())
        try:
            async with async_playwright() as playwright:
                browser=await playwright.chromium.launch()
                context=await browser.new_context(viewport={'width':390,'height':844})
                context.set_default_timeout(10000)
                try:
                    async with bridge.routed(context):
                        page=await context.new_page()
                        facts['observed_browser_pids']=helpers._method_main_owned_browser_pids()
                        await helpers._method_main_login(page,service)
                        await expect(page.locator('#evidence-method-section')).to_be_visible()
                        yield page,service,store,actor,calls,bridge,facts
                        await helpers._method_draft_drain_owned_bridge(page,bridge)
                except BaseException as error:
                    primary=error;raise
                finally:
                    for resource in (context,browser):
                        if resource is not None:
                            try:await resource.close()
                            except BaseException as error:errors.append(type(error).__name__)
                    if errors:
                        if primary:primary.add_note('owned browser cleanup uncertain: '+','.join(errors))
                        else:raise RuntimeError('owned browser cleanup uncertain: '+','.join(errors))
        finally:
            facts['provider_methods']=[call[0] for call in calls]
            facts['browser_closed']=browser is None or not browser.is_connected()
            facts['browser_cleanup_errors']=errors
            (tmp_path/'evidence-browser-resource.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
    assert not service.root.exists()


async def select_materials(page,bridge,count,*,keyboard=False):
    await page.locator('#evidence-method-tasks').click()
    await expect(page.locator('#evidence-method-task option')).to_have_count(count+1)
    # Each item is produced by a separate real Source task, never cloned IDs.
    values=await page.locator('#evidence-method-task option').evaluate_all('(xs)=>xs.map(x=>x.value).filter(Boolean)')
    for value in values:
        await page.locator('#evidence-method-task').select_option(value)
        async with bridge.material_read(page,value):
            await page.locator('#evidence-method-read-materials').click()
        await expect(page.locator('#evidence-method-status')).to_contain_text('短引已按当前权限读回')
    await expect(page.locator('#evidence-method-materials input')).to_have_count(count)
    for index,checkbox in enumerate(await page.locator('#evidence-method-materials input').all()):
        if keyboard and index==0:
            await checkbox.focus();await page.keyboard.press('Space');await expect(checkbox).to_be_checked()
        else:await checkbox.check()
    await expect(page.locator('#evidence-method-selection-count')).to_have_text(f'已选 {count} / 8 条短引')


async def preview_and_confirm(page,bridge,count,*,keyboard=False):
    await select_materials(page,bridge,count,keyboard=keyboard)
    await expect(page.locator('#evidence-method-confirm')).to_be_disabled()
    url=bridge.service.origin+'/api/research/'+bridge.service.seed.research_id
    async with bridge.capture_response(page,'POST',url+'/evidence-method-plan-previews') as captured:
        async with page.expect_response('**/evidence-method-plan-previews') as pending:
            await page.locator('#evidence-method-preview').click()
        response=await pending.value;assert response.status==200
        original=(await captured.json(response))['data']
    await expect(page.locator('#evidence-method-preview-panel')).to_be_visible()
    assert len(original['exact_input']['handles'])==count
    for handle in original['exact_input']['handles']:
        await expect(page.locator('#evidence-method-exact')).to_contain_text(handle['attribution'])
        await expect(page.locator('#evidence-method-exact')).to_contain_text(handle['quote'])
    await expect(page.locator('#evidence-method-quote')).to_contain_text('CNY 2.129920')
    await expect(page.locator('#evidence-method-confirm')).to_be_disabled()
    if keyboard:
        await page.locator('#evidence-method-consent').focus();await page.keyboard.press('Space')
    else:await page.locator('#evidence-method-consent').check()
    async with bridge.capture_response(page,'POST',url+'/evidence-method-plan-approvals') as captured:
        async with page.expect_response('**/evidence-method-plan-approvals') as pending:
            if keyboard:
                await page.locator('#evidence-method-confirm').focus();await page.keyboard.press('Enter')
            else:await page.locator('#evidence-method-confirm').click()
        response=await pending.value;assert response.status==200
        confirmed=(await captured.json(response))['data']
    await expect(page.locator('#evidence-method-status')).to_contain_text('等待实际执行')
    return original,confirmed


def test_original_default_single_source_preparation_unchanged(tmp_path):
    from web.backend.tests.acceptance.source_history_fixture import prepared_source_history
    with prepared_source_history(ROOT,tmp_path/'original-default') as seed:
        assert seed.schema_version==15 and len(seed.excerpt_refs)==1
        assert seed.current_input_revision==seed.source_input_revision==1
        assert seed.mode=='offline_probe'
    assert not (tmp_path/'original-default').exists()


@pytest.mark.parametrize('count',[1,8])
def test_actual_main_https_select_preview_confirm_runtime_save_refresh_original_ref_time(tmp_path,count):
    async def run():
        from research import ResearchRunner
        async with actual_browser(tmp_path,eight=count==8) as (page,service,store,actor,calls,bridge,facts):
            await page.locator('#method-draft-method').fill('本轮A综合不应改写的人工草稿。')
            preview,confirmed=await preview_and_confirm(page,bridge,count)
            assert calls==[]
            # This is a test-controller step after actual browser consent, not
            # an automatic Main worker or a product execution affordance.
            outcome=await asyncio.to_thread(ResearchRunner(store).run_once,confirmed['task_id'])
            assert outcome['data']['state']=='saved'
            assert [x[0] for x in calls]==['GET','POST']
            assert calls[0][2]==calls[1][2]
            await page.locator('#evidence-method-pending button').filter(has_text='读取这条原记录').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('按保守上限记账')
            await expect(page.locator('#evidence-method-body')).to_contain_text('未执行真实模型')
            await expect(page.locator('#method-draft-method')).to_have_value('本轮A综合不应改写的人工草稿。')
            saved=await helpers._native_tls_fetch(page,'/api/research/'+service.seed.research_id+'/evidence-method-plans/'+confirmed['result_ref'])
            assert saved['status']==200 and saved['body']['data']['content_state']=='available'
            original_time=saved['body']['data']['metadata']['recorded_at'];assert original_time is not None
            await expect(page.locator('#evidence-method-record-time')).to_contain_text(original_time)
            await page.locator('#evidence-method-section').screenshot(path=str(tmp_path/f'evidence-method-{count}-390px.png'))
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.locator('#evidence-method-history-load').focus()
            assert await page.locator('#evidence-method-history-load').evaluate('(x)=>x===document.activeElement')
            await page.reload()
            await page.locator('#evidence-method-history-load').click()
            await page.locator('#evidence-method-history button').click()
            await expect(page.locator('#evidence-method-record-ref')).to_contain_text(confirmed['result_ref'])
            await expect(page.locator('#evidence-method-record-time')).to_contain_text(original_time)
            assert calls[1][3]['response_format']=={'type':'json_object'}
            assert len(calls)==2
            # Real retirement closes new funding while the original history read
            # remains a current-ACL read, without replaying the provider call.
            from research import plan_native
            plan_native.retire_installation(store)
            await page.locator('#evidence-method-refresh').click()
            await expect(page.locator('#evidence-method-record-time')).to_contain_text(original_time)
            assert len(calls)==2
            facts.update({'result_ref':confirmed['result_ref'],'original_recorded_at':original_time,
                'exact_selected_handles':len(preview['exact_input']['handles']),'confirmed_browser_first':True,
                'explicit_actual_runner':True,'new_worker_or_live_model_claim':False,'same_ref_time_after_refresh':True,
                'funding_retired_history_readable':True,'viewport':[390,844]})
    asyncio.run(run())


@pytest.mark.parametrize('kind',['unknown_usage','bad_body'])
def test_actual_browser_separates_failed_candidate_and_unknown_cost_without_new_send(tmp_path,kind):
    async def run():
        from research import ResearchRunner
        async with actual_browser(tmp_path,unknown_usage=kind=='unknown_usage',bad_body=kind=='bad_body') as (page,service,store,actor,calls,bridge,facts):
            _,confirmed=await preview_and_confirm(page,bridge,1)
            await asyncio.to_thread(ResearchRunner(store).run_once,confirmed['task_id'])
            await page.locator('#evidence-method-pending button').filter(has_text='读取这条原记录').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('费用未知' if kind=='unknown_usage' else '未取得可用候选')
            await expect(page.locator('#evidence-method-status')).to_contain_text('保守上限记账' if kind=='bad_body' else '保留占用待核对')
            await expect(page.locator('#evidence-method-body')).not_to_contain_text('Example A, Example B')
            before=len(calls)
            await page.locator('#evidence-method-pending button').filter(has_text='用原操作核对确认回执').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('原确认回执已核对')
            assert len(calls)==before==2
            facts.update({'failure_kind':kind,'provider_calls_unchanged_after_original_key_recheck':True})
    asyncio.run(run())


def test_actual_browser_funding_closed_preview_not_sent_and_problem_edit_invalidates(tmp_path):
    async def run():
        async with actual_browser(tmp_path,funded=False) as (page,service,store,actor,calls,bridge,facts):
            await select_materials(page,bridge,1)
            await page.locator('#evidence-method-preview').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('资金执行尚未开放')
            await expect(page.locator('#evidence-method-confirm')).to_be_disabled()
            await expect(page.locator('#evidence-method-consent')).to_be_disabled()
            assert calls==[]
            await page.locator('#original-input').fill('我补充一条观察，旧外送预览必须失效。')
            await expect(page.locator('#evidence-method-preview-panel')).to_be_hidden()
            await expect(page.locator('#evidence-method-exact')).to_have_text('')
            await expect(page.locator('#evidence-method-preview')).to_be_disabled()
            facts['closed_no_provider_send_and_edit_clears_preview']=True
    asyncio.run(run())


def test_actual_browser_full_candidate_has_conditions_competing_explanations_and_validation(tmp_path):
    async def run():
        from research import ResearchRunner
        async with actual_browser(tmp_path,candidate=True) as (page,service,store,actor,calls,bridge,facts):
            _,confirmed=await preview_and_confirm(page,bridge,1,keyboard=True)
            await asyncio.to_thread(ResearchRunner(store).run_once,confirmed['task_id'])
            await page.locator('#evidence-method-pending button').filter(has_text='读取这条原记录').click()
            for text in ('到达集中与等待累积','机制假说（待验证）','公式提议（未经核验的提议）','变量对应','适用条件','竞争解释','不可迁移部分','反例或反证条件','最小验证计划','完整署名'):
                await expect(page.locator('#evidence-method-body')).to_contain_text(text)
            await page.locator('#evidence-method-body').screenshot(path=str(tmp_path/'evidence-candidate-390px.png'))
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            # A saved native run increments Root version without editing the
            # problem. A deliberate fresh preview must use the actual version,
            # without forcing the user to replace their main editor/draft.
            url=service.origin+'/api/research/'+service.seed.research_id+'/evidence-method-plan-previews'
            async with bridge.capture_response(page,'POST',url) as captured:
                async with page.expect_response(url) as latest:
                    await page.locator('#evidence-method-preview').click()
                newer=(await captured.json(await latest.value))['data']
            await expect(page.locator('#evidence-method-preview-panel')).to_be_visible()
            assert newer['research_version']==confirmed['execution_research_version']
            assert newer['preview_ref']!=confirmed['result_ref']
            assert len(calls)==2
            with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_plan_native_runs').fetchone()[0]==1
            facts.update(full_candidate_fields_visible=True,actual_keyboard_space_checkbox_and_consent_enter_confirm=True,explicit_second_preview_current_version_without_new_task=True)
    asyncio.run(run())


def test_actual_browser_lost_ack_reuses_original_confirm_then_cancel_never_sends(tmp_path):
    async def run():
        from research import ResearchRunner
        async with actual_browser(tmp_path) as (page,service,store,actor,calls,bridge,facts):
            await select_materials(page,bridge,1)
            await page.locator('#evidence-method-preview').click()
            await expect(page.locator('#evidence-method-preview-panel')).to_be_visible()
            await page.locator('#evidence-method-consent').check()
            observed=[];arrived=asyncio.Event()
            async def lose_ack(route,request):
                headers=await request.all_headers();raw=request.post_data_buffer
                returned=await asyncio.to_thread(bridge.forward,request.method,request.url,headers,raw)
                assert returned.status==200
                observed.append((headers['idempotency-key'],raw));arrived.set()
                await route.abort('failed')
            pattern='**/evidence-method-plan-approvals'
            await context_route(page,pattern,lose_ack)
            try:
                await page.locator('#evidence-method-confirm').click()
                await asyncio.wait_for(arrived.wait(),10)
                await expect(page.locator('#evidence-method-status')).to_contain_text('本次响应未能核实')
                await expect(page.locator('#evidence-method-pending')).to_contain_text('确认回执尚未核实')
                await expect(page.locator('#evidence-method-confirm')).to_be_disabled()
            finally:await page.context.unroute(pattern,lose_ack)
            async with page.expect_request(pattern) as retry:
                await page.locator('#evidence-method-pending button').filter(has_text='用原操作核对确认回执').click()
            request=await retry.value
            assert (await request.all_headers())['idempotency-key']==observed[0][0]
            assert request.post_data_buffer==observed[0][1]
            await expect(page.locator('#evidence-method-status')).to_contain_text('等待实际执行')
            assert calls==[]
            with store.transaction() as conn:
                runs=conn.execute('SELECT task_id,result_ref FROM research_plan_native_runs').fetchall()
                assert len(runs)==1
                tid,ref=runs[0]
            await page.locator('#evidence-method-pending button').filter(has_text='读取这条原记录').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('尚未预留费用')
            await page.locator('#evidence-method-cancel').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('已请求停止后续步骤')
            await page.locator('#evidence-method-refresh').click()
            await expect(page.locator('#evidence-method-status')).to_contain_text('已停止后续步骤')
            await asyncio.to_thread(ResearchRunner(store).run_once,tid)
            assert calls==[]
            facts.update({'lost_ack_after_actual_200':True,'same_confirm_key_and_body':True,'one_actual_task':True,'cancel_before_send_provider_calls':0,'result_ref':ref})
    asyncio.run(run())


async def context_route(page,pattern,handler):
    # The original canonical HTTPS bridge still performs the real HTTP call.
    await page.context.route(pattern,handler)


def test_actual_browser_account_delete_discards_late_private_result(tmp_path):
    async def run():
        from research import ResearchRunner
        async with actual_browser(tmp_path,candidate=True) as (page,service,store,actor,calls,bridge,facts):
            _,confirmed=await preview_and_confirm(page,bridge,1)
            await asyncio.to_thread(ResearchRunner(store).run_once,confirmed['task_id'])
            arrived=asyncio.Event();release=asyncio.Event()
            suffix='/api/research/'+service.seed.research_id+'/evidence-method-plans/'+confirmed['result_ref']
            async def hold_result(route,request):
                returned=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer)
                assert returned.status==200
                arrived.set();await release.wait()
                await route.fulfill(status=returned.status,body=returned.body,headers={'Content-Type':'application/json'})
            await context_route(page,'**'+suffix,hold_result)
            try:
                await page.locator('#evidence-method-pending button').filter(has_text='读取这条原记录').click()
                await asyncio.wait_for(arrived.wait(),10)
                # Actual authenticated delete, one finite client observation;
                # never dump cookies/token/body or synthesize a revoked identity.
                import urllib.request
                raw=json.dumps({'confirmation':'DELETE'}).encode()
                request=urllib.request.Request(service.origin+'/api/me/delete',data=raw,method='POST',headers={'Origin':service.origin,'Content-Type':'application/json'})
                def remove():
                    with service.client.opener.open(request,timeout=10) as response:
                        assert response.status==200
                await asyncio.to_thread(remove)
                release.set()
                await expect(page.locator('#problem-form')).to_be_hidden()
                await expect(page.locator('#evidence-method-section')).to_be_hidden()
                await expect(page.locator('#evidence-method-body')).to_have_text('')
                await expect(page.locator('#evidence-method-materials')).to_have_text('')
                facts['actual_delete_late_result_discarded']=True
            finally:
                release.set();await page.context.unroute('**'+suffix,hold_result)
    asyncio.run(run())


# Pure route lifecycle controls; they do not claim an actual product receipt.
from web.backend.tests.acceptance import plan_browser_service as component
import threading

class _BridgeControlContext:
 async def route(self,pattern,handler):self.handler=handler
 async def set_offline(self,value):pass
 async def unroute(self,pattern,handler):assert handler is self.handler
class _BridgeControlRoute:
 def __init__(self,error=None):self.handled=False;self.aborts=0;self.fulfills=0;self.error=error
 async def fulfill(self,**kwargs):
  self.fulfills+=1;self.handled=True
  if self.error:raise self.error
 async def abort(self,*args):
  self.aborts+=1
  if self.handled:raise RuntimeError('synthetic already handled masks first error')
  self.handled=True
class _BridgeControlRequest:
 method='GET';url='https://beta.structural.bytedance.city/api/synthetic';post_data_buffer=None
 async def all_headers(self):return {}
def _bridge_control(forward):
 value=component.CanonicalBrowserBridge.__new__(component.CanonicalBrowserBridge);value._routed_context=None;value.active=True;value._captures=[];value.condition=threading.Condition();value.pending={};value._handler_tasks=set();value._material_read=None;value._route_uncertain=False;value.forward=forward
 return value
@pytest.mark.parametrize('error_type',[ValueError,OSError,TimeoutError])
def test_terminal_fulfill_failure_preserves_first_error_without_second_abort(error_type):
 async def run():
  first=error_type('synthetic canary');route=_BridgeControlRoute(first);context=_BridgeControlContext();owned=_bridge_control(lambda *args:component.BridgeResponse(200,(),b'{}'))
  with pytest.raises(error_type) as caught:
   async with owned.routed(context):await context.handler(route,_BridgeControlRequest())
  assert caught.value is first and route.aborts==0 and route.fulfills==1
 asyncio.run(run())


def test_retirement_waits_for_owned_handler_before_unroute():
 async def run():
  started=threading.Event();release=threading.Event();finished=[]
  def forward(*args):
   started.set();assert release.wait(1);return component.BridgeResponse(200,(),b'{}')
  class Retiring_BridgeControlContext(_BridgeControlContext):
   async def set_offline(self,value):release.set()
   async def unroute(self,pattern,handler):assert finished==[True]
  class Finishing_BridgeControlRoute(_BridgeControlRoute):
   async def fulfill(self,**kwargs):await super().fulfill(**kwargs);finished.append(True)
  owned=_bridge_control(forward);context=Retiring_BridgeControlContext();route=Finishing_BridgeControlRoute()
  async with owned.routed(context):
   task=asyncio.create_task(context.handler(route,_BridgeControlRequest()))
   assert await asyncio.to_thread(started.wait,1)
  await task
  assert finished==[True] and not owned._handler_tasks and route.aborts==0
 asyncio.run(run())


@pytest.mark.parametrize('difference',['wrong_task','wrong_method','body','page','duplicate_auth','non200','unfinished','identity'])
def test_material_phase_rejects_wrong_binding_or_incomplete_actual_chain(difference):
    from types import SimpleNamespace
    page=object();phase=component._MaterialReadPhase(page,component.ORIGIN,'research','task')
    requests=[SimpleNamespace(frame=SimpleNamespace(page=page),url=url,method='GET',post_data_buffer=None) for url in phase.urls]
    if difference=='wrong_task':requests[2].url=requests[2].url.replace('task_id=task','task_id=other')
    elif difference=='wrong_method':requests[2].method='POST'
    elif difference=='body':requests[2].post_data_buffer=b'{}'
    elif difference=='page':requests[2].frame.page=object()
    try:
        for index,request in enumerate(requests):
            phase.bind(request)
            if difference=='duplicate_auth' and index==0:phase.bind(request)
            phase.forwarded(request,SimpleNamespace(status=403 if difference=='non200' and index==2 else 200))
            if difference=='unfinished' and index==2:continue
            phase.record_finished(SimpleNamespace(**vars(request)) if difference=='identity' and index==2 else request)
        with pytest.raises(AssertionError):phase.check()
    finally:phase.clear()
    assert phase.page is None and phase.urls==() and phase.requests==phase.finished==phase.statuses==[]


def test_route_retirement_stays_uncertain_when_owned_handler_misses_original_budget(monkeypatch):
    async def run():
        entered=asyncio.Event();release=asyncio.Event();unrouted=[]
        class HeldRoute(_BridgeControlRoute):
            async def fulfill(self,**kwargs):entered.set();await release.wait();await super().fulfill(**kwargs)
        class HeldContext(_BridgeControlContext):
            async def unroute(self,*args):unrouted.append(True)
        owned=_bridge_control(lambda *args:component.BridgeResponse(200,(),b'{}'));context=HeldContext();task=None
        # A shorter pure control deadline proves bounded failure; runtime value is unchanged.
        monkeypatch.setattr(component,'BRIDGE_WALL',.01)
        try:
            with pytest.raises(RuntimeError,match='handlers remain live'):
                async with owned.routed(context):
                    task=asyncio.create_task(context.handler(HeldRoute(),_BridgeControlRequest()))
                    await entered.wait()
            assert owned._route_uncertain and owned._handler_tasks and unrouted==[]
            with pytest.raises(RuntimeError,match='remains uncertain'):owned.close()
        finally:
            release.set()
            if task is not None:await task
        assert not owned._handler_tasks
        with pytest.raises(RuntimeError,match='remains uncertain'):owned.close()
    asyncio.run(run())


@pytest.mark.parametrize('error_type',[PermissionError,ValueError,OSError,TimeoutError])
def test_forward_refusal_aborts_once_without_fulfilling(error_type):
    async def run():
        def forward(*args):raise error_type('synthetic upstream refusal')
        owned=_bridge_control(forward);route=_BridgeControlRoute();context=_BridgeControlContext()
        async with owned.routed(context):await context.handler(route,_BridgeControlRequest())
        assert route.aborts==1 and route.fulfills==0 and not owned._route_uncertain
    asyncio.run(run())


def test_failed_abort_preserves_original_forward_error_and_bounds_cleanup_type():
    async def run():
        first=OSError('synthetic original');canary_type=type('CANARY_PRIVATE_TYPE',(RuntimeError,),{})
        class FailedAbort(_BridgeControlRoute):
            async def abort(self,*args):self.aborts+=1;raise canary_type('CANARY_PRIVATE_BODY')
        def forward(*args):raise first
        owned=_bridge_control(forward);route=FailedAbort();context=_BridgeControlContext()
        with pytest.raises(OSError) as caught:
            async with owned.routed(context):await context.handler(route,_BridgeControlRequest())
        assert caught.value is first and route.aborts==1 and route.fulfills==0
        assert all('CANARY' not in note for note in first.__notes__)
        assert any(note.endswith('OTHER') for note in first.__notes__)
    asyncio.run(run())


@pytest.mark.parametrize('difference',['key','body','receipt','status','method','duplicate_auth','invalid_json'])
def test_original_replay_phase_rejects_substitution_without_replacing_forwarded_response(difference):
    from types import SimpleNamespace
    page=object();pending={'key':'synthetic-original','task_request':{'data':{'scope':'synthetic'}}}
    original={'metadata':{'draft_ref':'synthetic-ref'}}
    phase=component._OriginalDraftReplayPhase(page,component.ORIGIN,'research',pending,original)
    requests=[SimpleNamespace(frame=SimpleNamespace(page=page),url=url,method=method,post_data_buffer=None) for url,method in zip(phase.urls,phase.methods)]
    data={'schema_version':'structure-research-v1','contract_revision':'method-draft-v1','data':pending['task_request']['data']}
    if difference=='body':data['data']={'scope':'different'}
    requests[1].post_data_buffer=json.dumps(data).encode()
    if difference=='method':requests[1].method='GET'
    body=b'not-json' if difference=='invalid_json' else json.dumps({'data':{} if difference=='receipt' else original}).encode()
    status=403 if difference=='status' else 200
    actual=component.BridgeResponse(status,(),body)
    try:
        for index,request in enumerate(requests):
            phase.bind(request)
            if difference=='duplicate_auth' and index==0:phase.bind(request)
            phase.forwarded(request,actual if index==1 else component.BridgeResponse(200,(),b'{}'),{'idempotency-key':'different' if difference=='key' else pending['key']})
            phase.record_finished(request)
        # Failed observation never edits the actual bytes/status given to fulfill.
        assert actual.status==status and actual.body is body
        with pytest.raises(AssertionError):phase.check_stage(1)
    finally:phase.clear()
    assert phase.pending is phase.original is phase.page is None


@pytest.mark.parametrize('kind',['deep_response','deep_request','bad_response','valid'])
def test_replay_observer_decode_failure_still_fulfills_original_response_once(kind):
    """Exercise the routed callback, not only the observation object in isolation."""
    from types import SimpleNamespace
    async def run():
        page=object();pending={'key':'synthetic-original','task_request':{'data':{'scope':'synthetic'}}}
        original={'metadata':{'draft_ref':'synthetic-ref'}}
        phase=component._OriginalDraftReplayPhase(page,component.ORIGIN,'research',pending,original)
        deep=b'{"data":'+b'['*2000+b'0'+b']'*2000+b'}'
        assert len(deep)==4010
        body=deep if kind=='deep_response' else b'not-json' if kind=='bad_response' else json.dumps({'data':original}).encode()
        actual=component.BridgeResponse(200,(('X-Owned-Control','one'),),body)
        first=SimpleNamespace(frame=SimpleNamespace(page=page),url=phase.urls[0],method='GET',post_data_buffer=None)
        phase.bind(first);phase.forwarded(first,component.BridgeResponse(200,(),b'{}'));phase.record_finished(first)
        class ReplayRequest(_BridgeControlRequest):
            method='POST';url=phase.urls[1]
            post_data_buffer=deep if kind=='deep_request' else json.dumps({'schema_version':'structure-research-v1','contract_revision':'method-draft-v1','data':pending['task_request']['data']}).encode()
            frame=SimpleNamespace(page=page)
            async def all_headers(self):return {'idempotency-key':pending['key']}
        request=ReplayRequest();phase.bind(request);delivered=[]
        class RecordedRoute(_BridgeControlRoute):
            async def fulfill(self,**kwargs):delivered.append(kwargs);await super().fulfill(**kwargs)
        route=RecordedRoute();context=_BridgeControlContext();owned=_bridge_control(lambda *args:actual);owned._material_read=phase
        try:
            async with owned.routed(context):await context.handler(route,request)
            assert route.fulfills==1 and route.aborts==0 and len(delivered)==1
            same_forwarded=(delivered[0]['status']==actual.status and delivered[0]['body'] is actual.body
                            and delivered[0]['headers']=={'x-owned-control':'one'})
            assert same_forwarded
            if kind=='valid':
                assert not phase.invalid and phase.same_operation and phase.same_receipt
            else:
                assert phase.invalid
                with pytest.raises(AssertionError):phase.check_stage(1)
        finally:phase.clear()
        assert phase.pending is phase.original is phase.page is None
    asyncio.run(run())


def test_replay_observer_does_not_consume_decode_cancellation(monkeypatch):
    from types import SimpleNamespace
    first=asyncio.CancelledError();page=object()
    pending={'key':'synthetic-original','task_request':{'data':{'scope':'synthetic'}}}
    phase=component._OriginalDraftReplayPhase(page,component.ORIGIN,'research',pending,{'metadata':{'draft_ref':'synthetic-ref'}})
    request0=SimpleNamespace(frame=SimpleNamespace(page=page),url=phase.urls[0],method='GET',post_data_buffer=None)
    request1=SimpleNamespace(frame=SimpleNamespace(page=page),url=phase.urls[1],method='POST',post_data_buffer=b'{}')
    phase.bind(request0);phase.bind(request1)
    def cancelled(*args,**kwargs):raise first
    try:
        monkeypatch.setattr(component.json,'loads',cancelled)
        with pytest.raises(asyncio.CancelledError) as caught:
            phase.forwarded(request1,component.BridgeResponse(200,(),b'{}'),{'idempotency-key':pending['key']})
        assert caught.value is first and not phase.invalid and not phase.same_receipt
    finally:phase.clear()


def test_terminal_fulfill_cancellation_keeps_original_instance_without_abort():
    async def run():
        first=asyncio.CancelledError();route=_BridgeControlRoute(first);context=_BridgeControlContext()
        owned=_bridge_control(lambda *args:component.BridgeResponse(200,(),b'{}'))
        with pytest.raises(asyncio.CancelledError) as caught:
            async with owned.routed(context):await context.handler(route,_BridgeControlRequest())
        assert caught.value is first and route.fulfills==1 and route.aborts==0
    asyncio.run(run())
