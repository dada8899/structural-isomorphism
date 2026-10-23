"""FIN2 registry UI through actual canonical Main15 HTTP, owned SMTP and TLS."""
from __future__ import annotations
import asyncio,hashlib,importlib.util,json,sqlite3,time,uuid
from pathlib import Path
import pytest
from contextlib import closing
from playwright.async_api import expect
ROOT=Path(__file__).resolve().parents[3]
_spec=importlib.util.spec_from_file_location('accepted_fin1_registry_helpers',ROOT/'web/tests/e2e/test_research_financial_preview_browser.py')
fin1=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(fin1)
helpers=fin1.helpers


async def pending(page):
    return await page.evaluate('Object.fromEntries(Object.entries(sessionStorage).filter(([k])=>k.startsWith("structure-research-pending:financial-registry-v2:")))')


async def ready_preview(page,service,csv=None):
    response,preview=await fin1.submit_csv(page,service,csv or fin1.with_missing())
    assert response.status==200
    await expect(page.locator('#financial-preview-status')).to_contain_text('临时预览已返回')
    await expect(page.locator('#financial-registry-consent')).to_be_enabled()
    await page.locator('#financial-registry-consent').check()
    await expect(page.locator('#financial-registry-confirm')).to_be_enabled()
    return preview


async def save_from_ui(page,service,bridge,csv=None):
    preview=await ready_preview(page,service,csv)
    url=service.origin+'/api/research/'+service.seed.research_id+'/financial-registries'
    async with bridge.capture_response(page,'POST',url) as captured:
        async with page.expect_response(url) as saved:
            await page.locator('#financial-registry-confirm').click()
        response=await saved.value;assert response.status==200
        body=await captured.json(response)
    await expect(page.locator('#financial-registry-status')).to_contain_text('已保存并核对读回')
    return preview,body['data']


async def actual_count(service):
    # The fixture paths are owned synthetic data, not a user database.
    path=service.seed.state_root/'auth.sqlite3'
    with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
        return conn.execute('SELECT count(*) FROM research_financial_registries').fetchone()[0]


async def minimum_chain(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 actualMain15 save/read/select/reopen'
        rid=service.seed.research_id;url=service.origin+'/api/research/'+rid
        before=await helpers._native_tls_fetch(page,'/api/research/'+rid)
        assert before['status']==200 and before['body']['data']['capabilities']['source_evidence'] is False
        assert (await helpers._native_tls_fetch(page,'/api/health'))['body']['checks']['native_planner']=='FUNDING_CLOSED'
        # Preserve unrelated manual work and its existing original intent.
        await page.locator('#method-draft-method').fill('保存财务材料不得覆盖的人工手稿。')
        original_pending=await helpers._method_main_pending(page)
        preview,saved=await save_from_ui(page,service,bridge)
        ref=saved['metadata']['registry_ref']['id'];at=saved['metadata']['received_at']
        assert saved['metadata']['preview_digest']==preview['data']['preview_digest']
        assert saved['metadata']['research_version_after']==saved['metadata']['research_version_before']+1
        await expect(page.locator('#financial-registry-selection')).to_contain_text('尚未选择')
        await expect(page.locator('#financial-registry-detail')).to_contain_text('1e+02')
        await expect(page.locator('#financial-registry-detail')).to_contain_text('USD · 百万（million）')
        await expect(page.locator('#financial-registry-detail')).to_contain_text('缺失／争议，未按0处理')
        await expect(page.locator('#financial-registry-detail')).to_contain_text('é reported')
        await expect(page.locator('#financial-registry-detail img,#financial-registry-detail a')).to_have_count(0)
        assert await actual_count(service)==1
        assert await pending(page)=={}
        assert await page.evaluate('!Object.values(localStorage).some(v=>v.includes("owner supplied only"))&&!Object.values(sessionStorage).some(v=>v.includes("owner supplied only"))')
        await page.locator('#financial-registry-history').click()
        await expect(page.locator('#financial-registry-status')).to_contain_text('已读取 1 份')
        await page.get_by_role('button',name='打开材料 '+ref[:8],exact=True).click()
        await expect(page.locator('#financial-registry-detail time')).to_have_attribute('datetime',at)
        await expect(page.locator('#financial-registry-choose')).to_be_enabled()
        await page.locator('#financial-registry-choose').focus();await page.keyboard.press('Enter')
        await expect(page.locator('#financial-registry-selection')).to_contain_text('已手动选择材料 '+ref)
        await page.locator('#financial-registry-reopen').focus();await page.keyboard.press('Enter')
        await expect(page.locator('#financial-registry-status')).to_contain_text('已读取原保存材料')
        await expect(page.locator('#financial-registry-detail time')).to_have_attribute('datetime',at)
        # A second ref at the same problem revision preserves the original row.
        _,second=await save_from_ui(page,service,bridge,fin1.LEGAL_CSV)
        assert second['metadata']['registry_ref']['id']!=ref and second['metadata']['input_revision']==saved['metadata']['input_revision']
        assert await actual_count(service)==2
        original=await helpers._native_tls_fetch(page,'/api/research/'+rid+'/financial-registries/'+ref)
        assert original['status']==200 and original['body']['data']['metadata']==saved['metadata']
        await expect(page.locator('#method-draft-method')).to_have_value('保存财务材料不得覆盖的人工手稿。')
        assert await helpers._method_main_pending(page)==original_pending
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.locator('#financial-registry-section').screenshot(path=str(tmp_path/'fin2-registry-mobile.png'))
        facts.update({'actual_schema':15,'funding_closed':True,'source_retired':True,'first_ref':ref,'first_received_at':at,'second_ref':second['metadata']['registry_ref']['id'],'real_row_count':2,'same_revision_refs_preserved':True,'keyboard_choose_reopen':True,'viewport_width':390,'csv_not_in_webstorage':True,'manual_text_and_original_pending_unchanged':True})


def test_fin2_actual_main_save_read_select_original_ref_and_mobile(tmp_path):
    asyncio.run(minimum_chain(tmp_path))


async def lose_ack(page,service,bridge):
    saved=[]
    async def lost(route):
        request=route.request
        actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer)
        assert actual.status==200
        saved.append({'data':json.loads(actual.body)['data'],'body':request.post_data,'key':(await request.all_headers())['idempotency-key']})
        await route.abort('failed')
    await page.route(service.origin+'/api/research/'+service.seed.research_id+'/financial-registries',lost,times=1)
    await ready_preview(page,service)
    await page.locator('#financial-registry-confirm').click()
    await expect(page.locator('#financial-registry-status')).to_contain_text('可能已经保存')
    assert len(saved)==1
    return saved[0]


async def new_revision(page,service):
    rid=service.seed.research_id;root=await helpers._native_tls_fetch(page,'/api/research/'+rid);assert root['status']==200
    old=root['body']['data']['current_problem'];problem={k:old[k] for k in ('entry','original_input','objective','summary','variables','constraints','unknowns','confirmed')}
    problem.update(original_input='另一真实HTTP明确保存的问题修订，不得覆盖原财务记录。',summary='新修订只用于检验原操作与历史材料边界。')
    changed=await helpers._method_main_post(page,'/api/research/'+rid+'/revisions',{'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{'expected_revision':old['revision'],'problem':problem}},str(uuid.uuid4()))
    assert changed['status']==200
    return changed['body']['data']


async def lost_reload_history(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 lost actual ACK and original-key replay after reload/new revision/dirty'
        original=await lose_ack(page,service,bridge);saved=original['data'];ref=saved['metadata']['registry_ref']['id'];at=saved['metadata']['received_at'];descriptors=await pending(page)
        assert len(descriptors)==1 and max(len(v.encode()) for v in descriptors.values())<=2048
        assert all('owner supplied only' not in v and 'csv_text' not in v and service.seed.email not in v for v in descriptors.values())
        assert await actual_count(service)==1
        changed=await new_revision(page,service);assert changed['current_problem']['revision']==2
        writes=[];page.on('request',lambda request:writes.append({'body':request.post_data,'key':request.headers.get('idempotency-key')}) if request.method=='POST' and request.url==service.origin+'/api/research/'+service.seed.research_id+'/financial-registries' else None)
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload())
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-preview-csv')).to_have_value('')
        assert await pending(page)==descriptors and writes==[]
        await page.locator('#financial-registry-history').click()
        await expect(page.locator('#financial-registry-pending')).to_contain_text('原 CSV 未保留')
        await expect(page.locator('#financial-registry-list')).to_contain_text('历史，只读')
        await page.locator('#original-input').fill('本页未保存新草稿，核对原财务操作不能替换。')
        await page.locator('#financial-preview-csv').fill(fin1.LEGAL_CSV)
        await page.get_by_role('button',name='核对上次保存（可能完成原保存）',exact=True).click()
        await expect(page.locator('#financial-registry-status')).to_contain_text('完全相同的原 CSV')
        assert writes==[] and await pending(page)==descriptors
        await page.locator('#financial-preview-csv').fill(fin1.with_missing())
        await page.get_by_role('button',name='核对上次保存（可能完成原保存）',exact=True).click()
        await expect(page.locator('#financial-registry-status')).to_contain_text('已保存并核对读回')
        assert writes==[{'body':original['body'],'key':original['key']}]
        assert await actual_count(service)==1 and await pending(page)=={}
        await expect(page.locator('#financial-registry-detail')).to_contain_text('历史财务材料 · 只读')
        await expect(page.locator('#financial-registry-detail time')).to_have_attribute('datetime',at)
        await expect(page.locator('#original-input')).to_have_value('本页未保存新草稿，核对原财务操作不能替换。')
        facts.update({'ref':ref,'received_at':at,'new_revision':2,'actual_row_count_after_replay':1,'exact_original_key_body':True,'wrong_csv_no_post':True,'reload_kept_metadata_not_csv':True,'dirty_original_problem_unchanged':True})


def test_fin2_actual_main_lost_ack_reload_old_revision_exact_replay(tmp_path):
    asyncio.run(lost_reload_history(tmp_path))


async def real_refusal(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 real revision conflict, no automatic new intent'
        await ready_preview(page,service);rid=service.seed.research_id;held=[]
        async def hold(route):held.append(route)
        await page.route(service.origin+'/api/research/'+rid+'/financial-registries',hold,times=1)
        await page.locator('#financial-registry-confirm').click();deadline=time.monotonic()+8
        while not held and time.monotonic()<deadline:await asyncio.sleep(.02)
        assert len(held)==1
        await new_revision(page,service)
        route=held.pop();request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer)
        assert actual.status==409 and json.loads(actual.body)['error']['code']=='REVISION_CONFLICT'
        await route.fulfill(status=actual.status,headers=dict(actual.headers),body=actual.body)
        await expect(page.locator('#financial-registry-status')).to_contain_text('原保存已明确拒绝')
        await expect(page.locator('#financial-preview-csv')).to_have_value(fin1.with_missing())
        await expect(page.locator('#financial-registry-confirm')).to_be_disabled()
        assert await pending(page)=={} and await actual_count(service)==0
        facts.update({'actual_refusal':'REVISION_CONFLICT409','no_rows_saved':True,'no_automatic_preview_or_new_key':True,'original_csv_preserved':True})


def test_fin2_actual_main_real_conflict_preserves_csv_without_new_key(tmp_path):
    asyncio.run(real_refusal(tmp_path))


async def unknown_navigation_logout(tmp_path,delete):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 auth unknown/navigation and confirmed account loss'
        _,first=await save_from_ui(page,service,bridge);ref=first['metadata']['registry_ref']['id'];await lose_ack(page,service,bridge);descriptors=await pending(page);assert len(descriptors)==1
        await page.locator('#financial-registry-history').click();await expect(page.locator('#financial-registry-status')).to_contain_text('已读取 2 份')
        await page.get_by_role('button',name='打开材料 '+ref[:8],exact=True).click();await expect(page.locator('#financial-registry-detail')).to_contain_text('owner supplied only')
        async def unknown(route):await route.fulfill(status=503,body='owned transient observation failure')
        await page.route(service.origin+'/api/auth/me',unknown)
        await page.locator('#financial-registry-history').click()
        await expect(page.locator('#financial-registry-detail')).to_have_text('')
        assert await pending(page)==descriptors
        await page.unroute(service.origin+'/api/auth/me',unknown)
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.goto(service.origin+'/research'))
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.go_back())
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-registry-detail')).to_have_text('')
        assert await pending(page)==descriptors
        await page.locator('#financial-registry-history').click();await expect(page.locator('#financial-registry-status')).to_contain_text('已读取 2 份')
        held=[]
        async def hold_read(route):
            request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200;held.append((route,actual))
        await page.route(service.origin+'/api/research/'+service.seed.research_id+'/financial-registries/'+ref,hold_read,times=1)
        await page.get_by_role('button',name='打开材料 '+ref[:8],exact=True).click();deadline=time.monotonic()+8
        while not held and time.monotonic()<deadline:await asyncio.sleep(.02)
        assert len(held)==1
        if delete:
            lost=await helpers._native_tls_fetch(page,'/api/me/delete','POST',{'confirmation':'DELETE'});assert lost['status']==200
            assert await actual_count(service)==0
        else:
            assert (await helpers._native_tls_fetch(page,'/api/auth/logout','POST',{}))['status']==200
        await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden()
        assert await pending(page)=={}
        route,actual=held.pop();await route.fulfill(status=actual.status,headers=dict(actual.headers),body=actual.body)
        await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        await expect(page.locator('#financial-registry-detail')).to_have_text('');await expect(page.locator('#financial-registry-section')).to_be_hidden()
        facts.update({'auth_unknown_kept_descriptor':True,'actual_navigation_kept_descriptor':True,'actual_bfcache_cache_hit_not_asserted':True,'confirmed_loss':'delete' if delete else 'logout','descriptor_cleared':True,'late_actual_get_not_rendered':True})


@pytest.mark.parametrize('delete',[False,True])
def test_fin2_actual_main_unknown_navigation_and_loss_hide_late_private_body(tmp_path,delete):
    asyncio.run(unknown_navigation_logout(tmp_path,delete))


async def pagination(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 real 21-record pagination, original cursor and private owner'
        rid=service.seed.research_id;root=(await helpers._native_tls_fetch(page,'/api/research/'+rid))['body']['data'];version=root['research_version'];saved=[]
        for index in range(21):
            request={'schema_version':'structure-research-v1','contract_revision':'financial-input-v2','data':{'input_revision':1,'expected_research_version':version,'csv_text':fin1.LEGAL_CSV}}
            preview=await helpers._method_main_post(page,'/api/research/'+rid+'/financial-import-preview',request,str(uuid.uuid4()));assert preview['status']==200
            request['data'].update(preview_digest=preview['body']['data']['preview_digest'],confirmed=True)
            result=await helpers._method_main_post(page,'/api/research/'+rid+'/financial-registries',request,str(uuid.uuid4()));assert result['status']==200
            saved.append(result['body']['data']['metadata']);version=result['body']['data']['current']['research_version']
        await page.locator('#original-input').fill('有未保存草稿时仍可读取财务材料历史。')
        pages=[];page.on('response',lambda response:pages.append(response.url) if '/financial-registries?limit=20' in response.url else None)
        await page.locator('#financial-registry-history').click();await expect(page.locator('#financial-registry-status')).to_contain_text('已读取 20 份')
        await expect(page.locator('#financial-registry-list button')).to_have_count(20);await expect(page.locator('#financial-registry-more')).to_be_visible()
        await page.locator('#financial-registry-more').click();await expect(page.locator('#financial-registry-status')).to_contain_text('已读取 21 份')
        await expect(page.locator('#financial-registry-list button')).to_have_count(21);await expect(page.locator('#financial-registry-more')).to_be_hidden()
        assert len(set(m['registry_ref']['id'] for m in saved))==21 and await actual_count(service)==21
        cursor=pages[-1].split('&cursor=')[1];assert cursor==saved[1]['registry_ref']['id']
        await expect(page.locator('#original-input')).to_have_value('有未保存草稿时仍可读取财务材料历史。')
        facts.update({'real_saved_refs':21,'page_sizes':[20,1],'cursor_original_ref':cursor,'dirty_read_allowed':True,'no_duplicates':True})


def test_fin2_actual_main_twenty_one_registry_pagination_while_dirty(tmp_path):
    asyncio.run(pagination(tmp_path))


async def restored_pending_without_fin2_click(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 actor repair: lost successful ACK / reload / no FIN2 action / real logout'
        original=await lose_ack(page,service,bridge);before=await pending(page);assert len(before)==1
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload())
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        # No history, preview, choose or recovery action after this reload.
        banner=await page.locator('#financial-registry-pending').inner_text()
        assert (await helpers._native_tls_fetch(page,'/api/auth/logout','POST',{}))['status']==200
        await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden()
        after=await pending(page)
        facts.update({'original_ref':original['data']['metadata']['registry_ref']['id'],'pending_before':len(before),'pending_after':len(after),'pending_unchanged':before==after,'initial_banner_has_pending':'原 CSV 未保留' in banner,'no_fin2_action_after_reload':True})
        (tmp_path/'actor-repair-counter.json').write_text(json.dumps({'before':len(before),'after':len(after),'unchanged':before==after,'banner':banner},ensure_ascii=False,indent=2))
        assert after=={},'confirmed logout must erase own restored descriptors without a FIN2 action'
        assert '原 CSV 未保留' in banner,'verified initial activation must expose its unresolved original intent'


def test_fin2_actual_main_restored_pending_logout_without_fin2_click(tmp_path):
    asyncio.run(restored_pending_without_fin2_click(tmp_path))


async def restored_unknown_bfcache_delete(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 actor repair: unknown and bfcache preserve, real deletion clears without FIN2 click'
        await lose_ack(page,service,bridge);before=await pending(page);assert len(before)==1
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload())
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-registry-pending')).to_contain_text('原 CSV 未保留')
        posted=[];page.on('request',lambda request:posted.append(request.url) if request.method=='POST' and request.url.endswith('/financial-registries') else None)
        async def unknown(route):await route.fulfill(status=503,body='owned unavailable observation')
        await page.route(service.origin+'/api/auth/me',unknown)
        await page.locator('#research-list-refresh').click();await expect(page.locator('#status')).to_contain_text('账户状态暂时无法核对')
        assert await pending(page)==before
        await expect(page.locator('#financial-registry-detail')).to_have_text('')
        await page.unroute(service.origin+'/api/auth/me',unknown)
        # Exercise the actual page lifecycle handlers with an explicit persisted
        # event. A real browser cache hit is not asserted by this event control.
        await page.evaluate('dispatchEvent(new PageTransitionEvent("pagehide",{persisted:true}))')
        assert await pending(page)==before
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.evaluate('dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}))'))
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-registry-pending')).to_contain_text('上次保存尚待核对')
        assert await pending(page)==before
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.goto(service.origin+'/research'))
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.go_back())
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        assert await pending(page)==before and posted==[]
        deleted=await helpers._native_tls_fetch(page,'/api/me/delete','POST',{'confirmation':'DELETE'});assert deleted['status']==200
        await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden()
        assert await pending(page)=={} and await actual_count(service)==0
        facts.update({'no_fin2_action_after_reload':True,'auth_unknown_preserved':True,'persisted_event_handler_preserved':True,'native_bfcache_cache_hit_not_claimed':True,'navigation_preserved':True,'real_delete_cleared_metadata':True,'automatic_financial_posts':len(posted)})


def test_fin2_actual_main_restored_unknown_bfcache_and_delete_without_fin2_click(tmp_path):
    asyncio.run(restored_unknown_bfcache_delete(tmp_path))


async def restored_actor_change(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN2 actor repair: verified actor change clears without FIN2 click'
        await lose_ack(page,service,bridge);before=await pending(page);assert len(before)==1
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload())
        await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-registry-pending')).to_contain_text('原 CSV 未保留')
        await page.evaluate('sessionStorage.setItem("structure-research-pending:actor-repair-sentinel","unrelated")')
        # Change the actual account cookie before any UI revalidation. The next
        # actual /auth/me proves actor_changed rather than a synthetic flag.
        assert (await helpers._native_tls_fetch(page,'/api/auth/logout','POST',{}))['status']==200
        requested=await helpers._native_tls_fetch(page,'/api/auth/request-link','POST',{'email':'actor-repair-other@example.invalid'});assert requested['status']==200
        token=service.take_latest_magic_token()
        try:verified=await helpers._native_tls_fetch(page,'/api/auth/verify','POST',{'token':token})
        finally:token=None
        assert verified['status']==200
        await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden()
        await expect(page.locator('#status')).to_contain_text('账户已变化')
        assert await pending(page)=={}
        assert await page.evaluate('sessionStorage.getItem("structure-research-pending:actor-repair-sentinel")')=='unrelated'
        await page.evaluate('sessionStorage.removeItem("structure-research-pending:actor-repair-sentinel")')
        facts.update({'no_fin2_action_after_reload':True,'real_smtp_verified_actor_change':True,'old_actor_descriptor_cleared':True,'other_module_sentinel_preserved':True})


def test_fin2_actual_main_restored_actor_change_without_fin2_click(tmp_path):
    asyncio.run(restored_actor_change(tmp_path))
