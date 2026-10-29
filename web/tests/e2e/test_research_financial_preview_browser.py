"""FIN1 actual Main browser: readonly temporary previews, not financial execution."""
from __future__ import annotations
import asyncio,csv,hashlib,importlib.util,io,json,os,subprocess,threading,time
from contextlib import asynccontextmanager
from pathlib import Path
import pytest
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parents[3]
_spec=importlib.util.spec_from_file_location('accepted_fin1_browser_helpers',ROOT/'tests/test_research_browser.py');helpers=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(helpers)
LEGAL_CSV='row_type,key,source_refs,url,locator,excerpt,declared_original_sha256,claimed_published_at,claimed_accessed_at,read_scope,source_chain,entity_scope,scope_kind,metric,period_start,period_end,period_grain,value,currency,unit,accounting_basis,declared_basis,alternative_refs,from_currency,to_currency,fx_kind\nsource,statement,,https://example.invalid/statement,owner says page 3,"é reported ""100""\nowner supplied only",,2026-08-01,2026-08-02,owner-selected excerpt,,,,,,,,,,,,,,,,\nobservation,interim,statement,,,,,,,,,Example group,group,revenue,2026-01-01,2026-06-30,interim,1e+02,USD,million,owner stated GAAP,disclosed,,,,\nhistorical_fx,average,statement,,,,,,,,,,,,2026-01-01,2026-06-30,interim,7.000,,,,media_estimate,,USD,CNY,period_average\n'
assert hashlib.sha256(LEGAL_CSV.encode()).hexdigest()=='e5b053b7c8ba654fde7bd0187e70b3c80edd6df39f952abafcfba815a0f20990'


def with_missing(csv_text=LEGAL_CSV):
    rows=list(csv.DictReader(io.StringIO(csv_text,newline='')));fields=list(rows[0]);missing={key:'' for key in fields};missing.update(row_type='observation',key='missing_op',entity_scope='Example group',scope_kind='group',metric='operating_profit',period_start='2026-01-01',period_end='2026-06-30',period_grain='interim',currency='CNY',unit='million',accounting_basis='owner stated GAAP',declared_basis='missing');rows.append(missing);out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(rows);return out.getvalue()


@asynccontextmanager
async def actual_browser(tmp_path):
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService
    owned=tmp_path/'actual-main';service=None;browser=None;context=None;primary=None;cleanup=[];facts={'scope':'FIN1 actualMain temporary readonly CSV preview'}
    try:
        with FormalMainBrowserService(owned) as service,service.browser_bridge() as bridge:
            # Retire the real accepted Source sub-lifetime; no fake capability.
            facts['source_status_before_retire']=service.source_status();facts['source_status_after_retire']=service.retire_source();assert facts['source_status_after_retire']=='unavailable'
            facts['ports']=[service.port,service._smtp.port]
            async with async_playwright() as playwright:
                browser=await playwright.chromium.launch();context=await browser.new_context(viewport={'width':390,'height':844});context.set_default_timeout(8000)
                try:
                    async with bridge.routed(context):
                        page=await context.new_page();facts['observed_browser_pids']=helpers._method_main_owned_browser_pids();await helpers._method_main_login(page,service);await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
                        yield page,service,bridge,facts
                        await helpers._method_draft_drain_owned_bridge(page,bridge)
                except BaseException as error:primary=error;raise
                finally:
                    for value in [context,browser]:
                        if value is not None:
                            try:await value.close()
                            except BaseException as error:cleanup.append(type(error).__name__)
                    if cleanup:
                        if primary:primary.add_note('owned browser cleanup uncertain: '+','.join(cleanup))
                        else:raise RuntimeError('owned browser cleanup uncertain: '+','.join(cleanup))
    finally:
        facts.update({'fixture_root_removed':not owned.exists(),'cleanup_errors':cleanup,'main_alive':service.server_thread.is_alive() if service and service.server_thread else None,'smtp_alive':service._smtp.thread.is_alive() if service and service._smtp else None,'owned_threads':[t.name for t in threading.enumerate() if t.name.startswith('formal-main-browser-')]});(tmp_path/'financial-preview-facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2))


async def submit_csv(page,service,text):
    await page.locator('#financial-preview-csv').fill(text)
    await expect(page.locator('#financial-preview-result')).to_have_text('')
    async with page.expect_response('**/financial-import-preview') as returned:await page.locator('#financial-preview-run').click()
    response=await returned.value
    return response,await response.json()


async def minimum_preview(tmp_path):
    async with actual_browser(tmp_path) as (page,service,bridge,facts):
        rid=service.seed.research_id;before=await helpers._native_tls_fetch(page,'/api/research/'+rid);assert before['status']==200 and before['body']['data']['capabilities']['source_evidence'] is False
        health=await helpers._native_tls_fetch(page,'/api/health');assert health['body']['checks']['native_planner']=='FUNDING_CLOSED'
        await page.locator('#method-draft-method').fill('FIN1预览不应替换的手稿B。');pending=await helpers._method_main_pending(page)
        response,first=await submit_csv(page,service,LEGAL_CSV);assert response.status==200;await expect(page.locator('#financial-preview-status')).to_contain_text('临时预览已返回');await expect(page.locator('#financial-preview-result')).to_contain_text('1e+02');await expect(page.locator('#financial-preview-result')).to_contain_text('7.000');await expect(page.locator('#financial-preview-result')).to_contain_text('账户声明为披露（未核验）');await expect(page.locator('#financial-preview-result')).to_contain_text('声明访问日期');await expect(page.locator('#financial-preview-result a')).to_have_count(0)
        assert first['data']['persisted'] is False and first['data']['execution_authorized'] is False and first['data']['original_available'] is False
        response,second=await submit_csv(page,service,with_missing());assert response.status==200;await expect(page.locator('#financial-preview-status')).to_contain_text('临时预览已返回');await expect(page.locator('#financial-preview-result')).to_contain_text('缺失（未按 0 处理）');assert second['data']['plan']['records'][-1]['value'] is None and second['data']['preview_digest']!=first['data']['preview_digest']
        after=await helpers._native_tls_fetch(page,'/api/research/'+rid);assert before['body']['data']['research_version']==after['body']['data']['research_version'];await expect(page.locator('#method-draft-method')).to_have_value('FIN1预览不应替换的手稿B。');assert await helpers._method_main_pending(page)==pending
        assert await page.evaluate('!Object.values(localStorage).some(v=>v.includes("owner supplied only"))&&!Object.values(sessionStorage).some(v=>v.includes("owner supplied only"))')
        await page.locator('#financial-preview-section').screenshot(path=str(tmp_path/'financial-preview-mobile.png'));assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        facts.update({'actual_capability':False,'funding':'closed','previews':2,'temporary_not_saved':True,'original_decimal_strings':['1e+02','7.000'],'null_preserved':True,'source_unverified':True,'research_version_unchanged':True,'handwriting_pending_unchanged':True,'url_plain_text_no_anchor':True,'no_csv_in_storage':True,'csv_sha256':second['data']['exact_received_csv_sha256']})


def test_fin1_actual_main_legal_edit_null_and_no_save(tmp_path):asyncio.run(minimum_preview(tmp_path))


def edited_source(*,malicious=False):
    rows=list(csv.DictReader(io.StringIO(LEGAL_CSV,newline='')));fields=list(rows[0])
    if malicious:
        rows[0]['url']='https://example.invalid/<svg-marker>'
        rows[0]['excerpt']='<img src="https://example.invalid/exfil" onerror="window.fin1Injected=1"> é'
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(rows);return out.getvalue()


def plan_limit_csv():
    fields=list(csv.DictReader(io.StringIO(LEGAL_CSV,newline='')).fieldnames);rows=[]
    for index in range(16):
        row={key:'' for key in fields};row.update(row_type='source',key='s'+str(index)+'_padding',url='https://example.invalid/'+'u'*1550,locator='l'*230,excerpt='e'*990,read_scope='r'*690);rows.append(row)
    refs=';'.join('s'+str(index)+'_padding' for index in range(16))
    for index in range(64):
        row={key:'' for key in fields};row.update(row_type='observation',key='o'+str(index),source_refs=refs,entity_scope='E'*119,scope_kind='group',metric='revenue',period_start='2025-01-01',period_end='2025-12-31',period_grain='annual',value='1',currency='USD',unit='million',accounting_basis='A'*239,declared_basis='disclosed');rows.append(row)
    for index in range(16):
        row={key:'' for key in fields};row.update(row_type='historical_fx',key='f'+str(index),source_refs=refs,period_start='2025-01-01',period_end='2025-12-31',period_grain='annual',value='7',declared_basis='disclosed',from_currency='USD',to_currency='CNY',fx_kind='period_average');rows.append(row)
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(rows);result=out.getvalue();assert len(result.encode())<=131072;return result


async def safe_errors(tmp_path):
    async with actual_browser(tmp_path) as (page,service,bridge,facts):
        requests=[];page.on('request',lambda request:requests.append(request.url) if request.url.startswith('https://example.invalid/') else None)
        response,body=await submit_csv(page,service,edited_source(malicious=True));assert response.status==200;await expect(page.locator('#financial-preview-status')).to_contain_text('临时预览已返回');await expect(page.locator('#financial-preview-result')).to_contain_text('<img src=');await expect(page.locator('#financial-preview-result img,#financial-preview-result svg,#financial-preview-result script,#financial-preview-result iframe,#financial-preview-result a')).to_have_count(0);assert await page.evaluate('window.fin1Injected===undefined') and not requests
        bad=LEGAL_CSV.replace('row_type,key,','wrong_header,key,',1);response,body=await submit_csv(page,service,bad);assert response.status==422 and body['validation']['code']=='EXACT_HEADER_REQUIRED';await expect(page.locator('#financial-preview-status')).to_contain_text('第 1 行');await expect(page.locator('#financial-preview-result')).to_have_text('');await expect(page.locator('#financial-preview-csv')).to_have_value(bad)
        large=plan_limit_csv();response,body=await submit_csv(page,service,large);assert response.status==413 and body['validation']['code']=='PLAN_LIMIT';await expect(page.locator('#financial-preview-status')).to_contain_text('超出有限范围');await expect(page.locator('#financial-preview-result')).to_have_text('');await expect(page.locator('#financial-preview-csv')).to_have_value(large)
        await page.locator('#financial-preview-csv').fill('中'*45000);await expect(page.locator('#financial-preview-run')).to_be_disabled();await expect(page.locator('#financial-preview-size')).to_contain_text('已超出预览范围')
        facts.update({'xss_literal_only':True,'url_not_fetched':True,'actual_422_safe_row_field':True,'actual_413_plan_limit':True,'client_utf8_size_limit':True,'errors_keep_current_csv_clear_old_preview':True})


def test_fin1_actual_main_safe_text_and_real_parse_limits(tmp_path):asyncio.run(safe_errors(tmp_path))


async def late_audit(tmp_path,change):
    async with actual_browser(tmp_path) as (page,service,bridge,facts):
        rid=service.seed.research_id;root_url=service.origin+'/api/research/'+rid;roots=[];held=[]
        async def root_route(route):
            request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200;roots.append(json.loads(actual.body)['data'])
            if len(roots)==2:held.append((route,actual));return
            await route.fulfill(status=actual.status,headers=dict(actual.headers),body=actual.body)
        await page.route(root_url,root_route);await page.locator('#method-draft-method').fill('迟到财务预览不能替换的手稿B。');pending=await helpers._method_main_pending(page)
        await page.locator('#financial-preview-csv').fill(LEGAL_CSV);await page.locator('#financial-preview-run').click();deadline=time.monotonic()+10
        while not held and time.monotonic()<deadline:await asyncio.sleep(.02)
        assert len(held)==1
        if change=='csv':
            current=with_missing();await page.locator('#financial-preview-csv').fill(current)
        elif change=='revision':
            await page.locator('#original-input').fill('财务预览返回前保存的新问题修订，不得被旧结果覆盖。');await page.locator('#summary').fill('实际保存新问题修订，使旧财务预览失效。');await page.locator('#confirmed').check()
            async def save_revision_with_actual_index():
                async with page.expect_response('**/revisions') as saved:await page.locator('#save').click()
                assert (await saved.value).status==200
            await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',save_revision_with_actual_index)
            await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究');await expect(page.locator('#financial-preview-context')).to_contain_text('问题修订 2');current=LEGAL_CSV
        else:
            assert (await helpers._native_tls_fetch(page,'/api/auth/logout','POST',{}))['status']==200;await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden();current=''
        route,actual=held.pop();await route.fulfill(status=actual.status,headers=dict(actual.headers),body=actual.body);await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        await expect(page.locator('#financial-preview-result')).to_have_text('');await expect(page.locator('#financial-preview-csv')).to_have_value(current)
        if change!='logout':await expect(page.locator('#method-draft-method')).to_have_value('迟到财务预览不能替换的手稿B。')
        assert await helpers._method_main_pending(page)==pending
        await page.unroute(root_url,root_route)
        if change=='logout':
            await page.goto(service.origin+'/research');other='fin1-other@example.invalid';assert (await helpers._native_tls_fetch(page,'/api/auth/request-link','POST',{'email':other}))['status']==200;token=service.take_latest_magic_token()
            try:verified=await helpers._native_tls_fetch(page,'/api/auth/verify','POST',{'token':token})
            finally:token=None
            assert verified['status']==200
            import uuid
            payload={'schema_version':'structure-research-v1','contract_revision':'financial-input-v2','data':{'input_revision':1,'expected_research_version':roots[0]['research_version'],'csv_text':LEGAL_CSV}}
            denied=await helpers._method_main_post(page,'/api/research/'+rid+'/financial-import-preview',payload,str(uuid.uuid4()));assert denied['status']==404
            async with page.expect_response(service.origin+'/api/research/'+rid) as denied_root:await page.goto(service.origin+'/research/'+rid)
            actual_root=await denied_root.value;assert actual_root.status==404;await actual_root.finished();await expect(page.locator('#status')).to_contain_text('研究不存在或当前无法访问');await expect(page.locator('#financial-preview-section')).to_be_hidden();await expect(page.locator('#financial-preview-csv')).to_have_value('');await expect(page.locator('#financial-preview-result')).to_have_text('');facts['actual_other_account_preview404_no_csv_leak']=True
        facts.update({'late_real_post_then_root_audit_held':True,'change':change,'stale_preview_not_rendered':True,'input_or_privacy_clear_preserved':True,'handwriting_and_existing_pending_unchanged':True})
        await page.unroute(root_url,root_route)


@pytest.mark.parametrize('change',['csv','revision','logout'])
def test_fin1_actual_main_late_audit_cannot_replace_new_scope(tmp_path,change):asyncio.run(late_audit(tmp_path,change))


async def conflict_and_readonly(tmp_path):
    import uuid
    async with actual_browser(tmp_path) as (page,service,bridge,facts):
        rid=service.seed.research_id;held=[]
        async def hold_root(route):
            request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200;held.append((route,actual))
        await page.route(service.origin+'/api/research/'+rid,hold_root,times=1);await page.locator('#financial-preview-csv').fill(LEGAL_CSV);await page.locator('#method-draft-method').fill('真实版本拒绝不能替换手稿B。');await page.locator('#financial-preview-run').click();deadline=time.monotonic()+8
        while not held and time.monotonic()<deadline:await asyncio.sleep(.02)
        assert len(held)==1;route,actual=held[0];root=json.loads(actual.body)['data'];old=root['current_problem'];problem={key:old[key] for key in ['entry','original_input','objective','summary','variables','constraints','unknowns','confirmed']};problem.update(original_input='另一真实HTTP保存的新修订，预览旧修订必须拒绝。',summary='新问题修订已真实保存。')
        changed=await helpers._method_main_post(page,'/api/research/'+rid+'/revisions',{'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{'expected_revision':1,'problem':problem}},str(uuid.uuid4()));assert changed['status']==200
        held.pop()
        async with page.expect_response('**/financial-import-preview') as preview:await route.fulfill(status=actual.status,headers=dict(actual.headers),body=actual.body)
        response=await preview.value;assert response.status==409 and (await response.json())['error']['code']=='VERSION_CONFLICT';await expect(page.locator('#financial-preview-status')).to_contain_text('问题版本已变化');await expect(page.locator('#financial-preview-csv')).to_have_value(LEGAL_CSV);await expect(page.locator('#financial-preview-result')).to_have_text('');await expect(page.locator('#method-draft-method')).to_have_value('真实版本拒绝不能替换手稿B。')
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.goto(service.origin+'/research/'+rid+'?task_id='+service.seed.source_task_id));await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究');await expect(page.locator('#financial-preview-context')).to_contain_text('只读或历史');await expect(page.locator('#financial-preview-run')).to_be_disabled();await expect(page.locator('#financial-preview-csv')).to_be_disabled();writes=[];page.on('request',lambda request:writes.append(request.url) if request.method=='POST' and request.url.endswith('/financial-import-preview') else None);await page.locator('#financial-preview-run').dispatch_event('click');assert not writes
        facts.update({'real_post_version_conflict':True,'csv_B_retained_after409':True,'fixed_historical_disabled_no_preview_post':True})


def test_fin1_actual_main_real_conflict_and_readonly(tmp_path):asyncio.run(conflict_and_readonly(tmp_path))


async def real_unknown_and_network(tmp_path):
    async with actual_browser(tmp_path) as (page,service,bridge,facts):
        rid=service.seed.research_id;await page.locator('#method-draft-task').select_option(service.seed.source_task_id)
        async with bridge.material_read(page,service.seed.source_task_id):
            await page.locator('#method-draft-read-sources').click()
        choice=page.locator('#method-draft-materials input[type=checkbox]').first;await expect(choice).to_be_visible();await expect(page.locator('#method-draft-read-sources')).to_be_enabled();await choice.check();await helpers._method_draft_type_manual_fields(page);saved=[]
        async def lose_method_ack(route):
            request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200;saved.append(json.loads(actual.body)['data']);await route.abort('failed')
        await page.route(service.origin+'/api/research/'+rid+'/method-drafts',lose_method_ack,times=1);await page.locator('#method-draft-save').click();await expect(page.locator('#method-draft-status')).to_contain_text('尚未确认');pending=await helpers._method_main_pending(page);assert len(pending)==1 and len(saved)==1;await page.locator('#method-draft-method').fill('金融预览及网络失败时必须保留的原手稿B。')
        original=await helpers._native_tls_fetch(page,'/api/research/'+rid+'/method-drafts/'+saved[0]['metadata']['draft_ref']);assert original['status']==200 and original['body']['data']==saved[0]
        response,_=await submit_csv(page,service,LEGAL_CSV);assert response.status==200;await expect(page.locator('#financial-preview-status')).to_contain_text('临时预览已返回')
        async with page.expect_response('**/method-drafts') as saved_b:await page.locator('#method-draft-save').click()
        response_b=await saved_b.value;assert response_b.status==200;await expect(page.locator('#method-draft-status')).to_contain_text('已保存新的验证草稿');await expect(page.locator('#financial-preview-result')).to_have_text('');await expect(page.locator('#financial-preview-status')).to_contain_text('研究版本已变化');assert await helpers._method_main_pending(page)==pending
        before=await helpers._native_tls_fetch(page,'/api/research/'+rid);response,_=await submit_csv(page,service,LEGAL_CSV);assert response.status==200;await expect(page.locator('#financial-preview-status')).to_contain_text('临时预览已返回');lost=[]
        async def lose_preview(route):
            request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200;lost.append(True);await route.abort('failed')
        await page.route(service.origin+'/api/research/'+rid+'/financial-import-preview',lose_preview,times=1);text=with_missing();await page.locator('#financial-preview-csv').fill(text);await page.locator('#financial-preview-run').click();await expect(page.locator('#financial-preview-status')).to_contain_text('响应尚未确认');await expect(page.locator('#financial-preview-result')).to_have_text('');await expect(page.locator('#financial-preview-csv')).to_have_value(text);await expect(page.locator('#method-draft-method')).to_have_value('金融预览及网络失败时必须保留的原手稿B。');assert lost==[True] and await helpers._method_main_pending(page)==pending
        after=await helpers._native_tls_fetch(page,'/api/research/'+rid);assert before['body']['data']['research_version']==after['body']['data']['research_version'];again=await helpers._native_tls_fetch(page,'/api/research/'+rid+'/method-drafts/'+saved[0]['metadata']['draft_ref']);assert again['status']==200 and again['body']['data']==saved[0]
        async with bridge.original_draft_replay(page,pending[0],saved[0]):
            await page.get_by_role('button',name='核对这一笔原保存',exact=True).click()
        await expect(page.locator('#method-draft-status')).to_contain_text('原保存已确认');await expect(page.locator('#method-draft-method')).to_have_value('金融预览及网络失败时必须保留的原手稿B。');assert await helpers._method_main_pending(page)==[]
        facts.update({'same_revision_method_save_invalidates_old_preview':True,'real_nonempty_original_key_body_ref_time_preserved':True,'original_ref':saved[0]['metadata']['draft_ref'],'original_time':saved[0]['metadata']['created_at'],'original_body_digest':saved[0]['metadata']['content_digest'],'actual_preview200_then_network_loss':True,'csv_B_preserved_preview_invalid':True,'preview_did_not_update_root_version':True,'original_key_explicitly_reconciled':True})


def test_fin1_actual_main_network_unknown_preserves_real_original_intent(tmp_path):asyncio.run(real_unknown_and_network(tmp_path))
