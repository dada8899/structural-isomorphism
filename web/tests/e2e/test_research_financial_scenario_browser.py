"""FIN3 ordinary form through actual canonicalMain15, owned SMTP/TLS bridge."""
from __future__ import annotations
import asyncio,hashlib,importlib.util,json,sqlite3,time,uuid
from contextlib import closing
from pathlib import Path
import pytest
from playwright.async_api import expect
ROOT=Path(__file__).resolve().parents[3]
_spec=importlib.util.spec_from_file_location('accepted_fin2_scenario_helpers',ROOT/'web/tests/e2e/test_research_financial_registry_browser.py');fin2=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(fin2)
fin1=fin2.fin1;helpers=fin1.helpers


async def pending(page):
    return await page.evaluate('Object.fromEntries(Object.entries(sessionStorage).filter(([k])=>k.startsWith("structure-research-pending:financial-scenario-v2:")))')


async def count(service):
    with closing(sqlite3.connect('file:'+str(service.seed.state_root/'auth.sqlite3')+'?mode=ro',uri=True)) as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
        return conn.execute('SELECT count(*) FROM research_financial_results').fetchone()[0]


async def choose_material(page,service,bridge):
    loaded=await page.evaluate('''async()=>{const names=['financial-scenario.js','research.js','financial-registry.js'];const out={};for(const name of names){const script=[...document.scripts].find(s=>new URL(s.src).pathname==='/assets/'+name);if(!script)throw Error('required script not loaded');const raw=await (await fetch(script.src,{cache:'no-store'})).arrayBuffer();const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(n=>n.toString(16).padStart(2,'0')).join('');out[name]={sha,script_resource:performance.getEntriesByName(script.src).some(e=>e.initiatorType==='script')};}return out;}''')
    for name,value in loaded.items():assert value['script_resource'] and value['sha']==hashlib.sha256((ROOT/'web/frontend/assets'/name).read_bytes()).hexdigest()
    service._fin3_loaded_scripts=loaded
    _,saved=await fin2.save_from_ui(page,service,bridge,fin1.LEGAL_CSV)
    await page.locator('#financial-registry-choose').click()
    await page.locator('#financial-scenario-adopt').click()
    await expect(page.locator('#financial-scenario-status')).to_contain_text('已采用原材料')
    return saved


async def fill_form(page,*,sensitivity=False,recovery=False):
    baseline=page.locator('#financial-scenario-baseline');options=await baseline.locator('option').evaluate_all('(items)=>items.map(n=>n.value).filter(Boolean)');assert len(options)==1
    await baseline.select_option(options[0]);await page.locator('#financial-scenario-cutoff').fill('2026-08-02');await page.locator('#financial-scenario-baseline-reason').fill('合成数据条件基线，非真实预测或原件验证。');await page.locator('#financial-scenario-target').select_option('USD')
    await page.locator('#financial-scenario-categories-confirmed').check();await page.locator('#financial-scenario-s0-label').fill('合成条件一');await page.locator('#financial-scenario-s0-remaining-value').fill('100');await page.locator('#financial-scenario-s0-remaining-reason').fill('独立剩余期合成条件')
    for year in range(2027,2032):
        await page.locator(f'#financial-scenario-s0-growth-{year}-value').fill('10');await page.locator(f'#financial-scenario-s0-growth-{year}-reason').fill('独立增长合成条件')
    if sensitivity:
        toggle=page.locator('#financial-scenario-sensitivity-enabled');await toggle.locator('xpath=ancestor::details[1]').evaluate('(n)=>n.open=true');await toggle.check();await page.locator('#financial-scenario-sensitivity-target').select_option('growth:2027');await page.locator('#financial-scenario-sensitivity-points').fill('0,10,20')
    if recovery:await expect(page.locator('#financial-scenario-calculate')).to_be_disabled()
    else:
        await page.locator('#financial-scenario-consent').check();await expect(page.locator('#financial-scenario-calculate')).to_be_enabled()


async def saved_chain(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 actualMain15 ordinary form -> save -> three views/history'
        registry=await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts
        assert (await helpers._native_tls_fetch(page,'/api/health'))['body']['checks']['native_planner']=='FUNDING_CLOSED'
        await page.locator('#method-draft-method').fill('FIN3不替换的人工方法草稿。');old_pending=await helpers._method_main_pending(page)
        await fill_form(page,sensitivity=True)
        url=service.origin+'/api/research/'+service.seed.research_id+'/financial-calculations'
        async with bridge.capture_response(page,'POST',url) as captured:
            async with page.expect_response(url) as saved:await page.locator('#financial-scenario-calculate').click()
            result=await saved.value;assert result.status==200,await result.text();body=await captured.json(result)
        m=body['data']['metadata'];ref=m['result_ref'];at=m['recorded_at']
        await expect(page.locator('#financial-scenario-status')).to_contain_text('条件计算已保存')
        await expect(page.locator('#financial-scenario-result')).to_contain_text('营业利润缺失')
        assert body['data']['public_result']['view']=='summary' and await count(service)==1
        assert m['registry_ref']==registry['metadata']['registry_ref']
        await page.get_by_role('button',name='年度底表',exact=True).click();await expect(page.locator('#financial-scenario-result')).to_contain_text('年度底表');await expect(page.locator('#financial-scenario-result')).to_contain_text('200.000000');await expect(page.locator('#financial-scenario-result')).to_contain_text('缺失／争议')
        await page.get_by_role('button',name='条件曲线与敏感性',exact=True).click();await expect(page.locator('#financial-scenario-result')).to_contain_text('条件曲线');await expect(page.locator('#financial-scenario-result svg')).to_have_count(4)
        await expect(page.locator('#financial-scenario-result')).to_contain_text('growth_2027')
        await page.locator('#financial-scenario-history').click();await expect(page.locator('#financial-scenario-status')).to_contain_text('已读取 1 条条件结果历史')
        await page.get_by_role('button',name='打开条件结果 '+ref[:8],exact=True).click();await expect(page.locator('#financial-scenario-record time')).to_have_attribute('datetime',at)
        await expect(page.locator('#financial-scenario-s0-remaining-value')).to_have_value('100');await expect(page.locator('#method-draft-method')).to_have_value('FIN3不替换的人工方法草稿。');assert await helpers._method_main_pending(page)==old_pending
        assert await pending(page)=={} and await count(service)==1
        assert await page.evaluate('!Object.values(localStorage).some(v=>v.includes("独立增长合成条件"))&&!Object.values(sessionStorage).some(v=>v.includes("独立增长合成条件"))')
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.locator('#financial-scenario-section').screenshot(path=str(tmp_path/'financial-scenario-mobile.png'))
        facts.update({'registry_ref':m['registry_ref']['id'],'result_ref':ref,'recorded_at':at,'actual_result_rows':1,'summary_table_chart_same_ref':True,'costs_missing_OP_null':True,'null_gaps_not_zero':True,'sensitivity_points':3,'original_draft_pending_unchanged':True,'raw_form_not_webstorage':True,'source_retired_funding_closed':True})


def test_fin3_actual_main_ordinary_form_save_three_views_and_history(tmp_path):asyncio.run(saved_chain(tmp_path))


async def lost_calculation(page,service,bridge,*,mutate_structure=False):
    await fill_form(page,sensitivity=True)
    if mutate_structure:
        await page.locator('#financial-scenario-add-scenario').click()
        await page.get_by_role('button',name='移除此情景',exact=True).last.click()
        await page.locator('#financial-scenario-sensitivity-target').select_option('growth:2027')
        await page.locator('#financial-scenario-consent').check()
    saved=[]
    async def lose(route):
        request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200
        saved.append({'data':json.loads(actual.body)['data'],'body':request.post_data,'key':(await request.all_headers())['idempotency-key']});await route.abort('failed')
    await page.route(service.origin+'/api/research/'+service.seed.research_id+'/financial-calculations',lose,times=1)
    await page.locator('#financial-scenario-calculate').click();await expect(page.locator('#financial-scenario-status')).to_contain_text('可能已经保存')
    assert len(saved)==1 and len(await pending(page))==1 and await count(service)==1
    return saved[0]


async def reload_replay(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 original key/body deterministic IDs after reload and historical registry catalog'
        await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts;original=await lost_calculation(page,service,bridge,mutate_structure=True);descriptors=await pending(page)
        assert all(len(v.encode())<=2048 and '独立增长合成条件' not in v and 'request"' not in v for v in descriptors.values())
        await fin2.new_revision(page,service)
        posted=[];page.on('request',lambda request:posted.append({'body':request.post_data,'key':request.headers.get('idempotency-key')}) if request.method=='POST' and request.url.endswith('/financial-calculations') else None)
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload());await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-scenario-pending')).to_contain_text('原表单未保留')
        assert await pending(page)==descriptors and posted==[]
        await page.locator('#financial-scenario-recovery-material').click();await expect(page.locator('#financial-scenario-status')).to_contain_text('仅供原表单重供')
        await expect(page.locator('#financial-scenario-calculate')).to_be_disabled()
        await fill_form(page,sensitivity=True,recovery=True)
        await page.locator('#financial-scenario-s0-remaining-value').fill('101')
        await page.get_by_role('button',name='核对上次保存（可能完成原计算保存）',exact=True).click();await expect(page.locator('#financial-scenario-status')).to_contain_text('完整原表单摘要不同');assert posted==[]
        await page.locator('#financial-scenario-s0-remaining-value').fill('100')
        await page.get_by_role('button',name='核对上次保存（可能完成原计算保存）',exact=True).click();await expect(page.locator('#financial-scenario-status')).to_contain_text('条件计算已保存')
        assert posted==[{'body':original['body'],'key':original['key']}] and await count(service)==1 and await pending(page)=={}
        await expect(page.locator('#financial-scenario-record time')).to_have_attribute('datetime',original['data']['metadata']['recorded_at'])
        await expect(page.locator('#financial-scenario-record')).to_contain_text('历史只读')
        await expect(page.locator('#financial-scenario-calculate')).to_be_disabled()
        facts.update({'exact_body_key_after_fresh_form':True,'prior_add_remove_hidden_ids_rebuilt':True,'wrong_form_no_post':True,'historical_recovery_catalog_never_new_calc':True,'original_result_ref':original['data']['metadata']['result_ref'],'original_recorded_at':original['data']['metadata']['recorded_at'],'one_result_after_replay':True})


def test_fin3_actual_main_reload_rebuild_exact_request_with_historical_catalog(tmp_path):asyncio.run(reload_replay(tmp_path))


async def covered_advanced(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 actual explicit five-cost coverage, three scenarios, 21 discrete points'
        await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts;await fill_form(page)
        await page.locator('#financial-scenario-s0-cost-panel').evaluate('(n)=>n.open=true')
        await page.locator('#financial-scenario-s0-add-cost').click()
        await page.locator('#financial-scenario-s0-cost0-label').fill('五项合并条件成本')
        await page.locator('#financial-scenario-s0-cost0-coverage').fill('本假设金额含五项成本且不重复，不代表原件事实。')
        for tag in ['base_operating_cost','base_operating_expense','shared_cost','depreciation','sbc']:await page.locator('#financial-scenario-s0-cost0-'+tag).check()
        await page.locator('#financial-scenario-s0-cost0-enabled-2026').check();await page.locator('#financial-scenario-s0-cost0-2026-value').fill('50');await page.locator('#financial-scenario-s0-cost0-2026-reason').fill('独立全年成本条件')
        await page.locator('#financial-scenario-s0-cost0-copy-panel').evaluate('(n)=>n.open=true')
        for year in range(2027,2032):await page.locator('#financial-scenario-s0-cost0-copy-'+str(year)).check()
        await page.locator('#financial-scenario-s0-cost0-copy').click()
        for index in (1,2):
            await page.locator('#financial-scenario-add-scenario').click();await page.locator(f'#financial-scenario-s{index}-label').fill('明确缺口情景'+str(index));await page.locator(f'#financial-scenario-s{index}-remaining-reason').fill('剩余收入未知，保持null')
            for year in range(2027,2032):await page.locator(f'#financial-scenario-s{index}-growth-{year}-reason').fill('未来增长未知，保持null')
        await page.locator('#financial-scenario-sensitivity-panel').evaluate('(n)=>n.open=true');await page.locator('#financial-scenario-sensitivity-enabled').check();await page.locator('#financial-scenario-sensitivity-target').select_option('growth:2027');await page.locator('#financial-scenario-sensitivity-points').fill(','.join(str(x) for x in range(21)));await page.locator('#financial-scenario-consent').check()
        url=service.origin+'/api/research/'+service.seed.research_id+'/financial-calculations'
        from web.backend.tests.acceptance.financial_limit_observer import observe_financial_limit
        with observe_financial_limit(service.app) as observation:
            async with bridge.capture_response(page,'POST',url) as captured:
                async with page.expect_response(url) as saved:await page.locator('#financial-scenario-calculate').click()
                response=await saved.value;observation.response(response.status)
                assert response.status==200,await response.text();data=(await captured.json(response))['data']
        await expect(page.locator('#financial-scenario-status')).to_contain_text('条件计算已保存')
        assert len(data['public_result']['value']['scenarios'])==3 and data['public_result']['value']['scenarios'][0]['years'][0]['available']['operating_profit'] is True
        await page.get_by_role('button',name='年度底表',exact=True).click();await expect(page.locator('#financial-scenario-result')).to_contain_text('150.000000')
        await page.get_by_role('button',name='条件曲线与敏感性',exact=True).click();await expect(page.locator('#financial-scenario-result svg')).to_have_count(12)
        actual=await helpers._native_tls_fetch(page,'/api/research/'+service.seed.research_id+'/financial-results/'+data['metadata']['result_ref']+'?view=chart');assert actual['status']==200 and len(actual['body']['data']['public_result']['value']['chart_spec']['sensitivity'])==21
        facts.update({'three_scenarios':True,'twenty_one_points':True,'explicit_copy_to_selected_years':True,'five_tags_covered_once':True,'2026_conditional_OP_150':True,'other_scenarios_null':True,'u2_not_passed':data['metadata']['u2_goal_status']})


def test_fin3_actual_main_coverage_three_scenarios_and_twenty_one_points(tmp_path):asyncio.run(covered_advanced(tmp_path))


async def unknown_delete(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 initial actor no-click cleanup; unknown/bfcache preserve pending'
        await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts;await lost_calculation(page,service,bridge);descriptors=await pending(page)
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload());await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        await expect(page.locator('#financial-scenario-pending')).to_contain_text('原表单未保留')
        async def unknown(route):await route.fulfill(status=503,body='owned observation unavailable')
        await page.route(service.origin+'/api/auth/me',unknown);await page.locator('#research-list-refresh').click();await expect(page.locator('#status')).to_contain_text('账户状态暂时无法核对');assert await pending(page)==descriptors
        await page.unroute(service.origin+'/api/auth/me',unknown);await page.evaluate('dispatchEvent(new PageTransitionEvent("pagehide",{persisted:true}))')
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.evaluate('dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}))'));await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究');assert await pending(page)==descriptors
        deleted=await helpers._native_tls_fetch(page,'/api/me/delete','POST',{'confirmation':'DELETE'});assert deleted['status']==200
        await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden();assert await pending(page)=={} and await count(service)==0
        await expect(page.locator('#financial-scenario-result')).to_have_text('');await expect(page.locator('#financial-scenario-section')).to_be_hidden()
        facts.update({'no_fin3_click_after_reload':True,'initial_pending_visible':True,'auth_unknown_preserved':True,'persisted_handler_preserved':True,'native_cache_hit_not_claimed':True,'real_delete_erased_rows_and_metadata':True})


def test_fin3_actual_main_pending_unknown_bfcache_delete_without_module_click(tmp_path):asyncio.run(unknown_delete(tmp_path))


async def derived_readonly(tmp_path):
    from datetime import date,timedelta
    import hashlib
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 read-only old stored derived evidence; no daily-input widget'
        registry=await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts;await fill_form(page);posted=[]
        page.on('request',lambda request:posted.append(request.post_data) if request.method=='POST' and request.url.endswith('/financial-calculations') else None)
        async with page.expect_response('**/financial-calculations') as saved:await page.locator('#financial-scenario-calculate').click()
        assert (await saved.value).status==200;await expect(page.locator('#financial-scenario-status')).to_contain_text('条件计算已保存');assert len(posted)==1
        # Test-only synthetic supplied daily values, explicitly not official data.
        # This does not add a product daily-series input or fabricate a source.
        operation=json.loads(posted[0]);root=(await helpers._native_tls_fetch(page,'/api/research/'+service.seed.research_id))['body']['data'];operation['data']['expected_research_version']=root['research_version'];request=operation['data']['request'];request['target_currency']='CNY';request['sensitivity']=None
        original=await helpers._native_tls_fetch(page,'/api/research/'+service.seed.research_id+'/financial-registries/'+registry['metadata']['registry_ref']['id']);assert original['status']==200;source=next(r for r in original['body']['data']['projection']['registry']['records'] if r['row_type']=='source')
        points=[];day=date(2026,1,1)
        while day<=date(2026,6,30):
            if day.weekday()<5:points.append({'date':day.isoformat(),'value':None if len(points)%9==0 else '7'})
            day+=timedelta(days=1)
        values=[p['value'] for p in points if p['value'] is not None]
        request['derived_fx_inputs']=[{'id':'synthetic_daily','source_id':source['id'],'claimed_source_version':'synthetic-controlled-test-only','claimed_accessed_on':'2026-08-02','locator':'synthetic supplied series, not an official document','from_currency':'USD','to_currency':'CNY','period':{'start':'2026-01-01','end':'2026-06-30','grain':'interim'},'points':points,'declared_valid_count':len(values),'declared_nd_count':len(points)-len(values),'declared_values_sha256':hashlib.sha256(json.dumps(values,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()}]
        request['historical_fx_choices']=[{'kind':'derived','observation_id':request['interim_revenue_ref'],'derivation_id':'synthetic_daily'}]
        derived=await helpers._method_main_post(page,'/api/research/'+service.seed.research_id+'/financial-calculations',operation,str(uuid.uuid4()));assert derived['status']==200
        m=derived['body']['data']['metadata'];assert await count(service)==2;await fin2.new_revision(page,service)
        await page.locator('#financial-scenario-history').click();await expect(page.locator('#financial-scenario-status')).to_contain_text('已读取 2 条条件结果历史')
        await page.get_by_role('button',name='打开条件结果 '+m['result_ref'][:8],exact=True).click();await expect(page.locator('#financial-scenario-record')).to_contain_text('历史只读')
        await page.get_by_role('button',name='年度底表',exact=True).click();await expect(page.locator('#financial-scenario-result')).to_contain_text('历史派生日均率')
        parent=page.get_by_text('历史派生日均率 · 仅算术重算，来源未核',exact=True).locator('xpath=..');await expect(parent.locator('table tr')).to_have_count(130)
        await expect(page.locator('#financial-scenario-record time')).to_have_attribute('datetime',m['recorded_at'])
        before=len(posted);await page.get_by_role('button',name='条件曲线与敏感性',exact=True).click();await expect(page.locator('#financial-scenario-result')).to_contain_text('历史派生日均率');assert len(posted)==before and await count(service)==2
        facts.update({'read_old_revision':True,'real_stored_daily_points':129,'daily_input_UI_not_implemented':True,'arithmetic_only_unverified_label':True,'switch_views_new_posts':0,'original_ref':m['result_ref'],'original_recorded_at':m['recorded_at']})


def test_fin3_actual_main_old_derived_result_complete_readonly(tmp_path):asyncio.run(derived_readonly(tmp_path))


async def late_recovery_catalog(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 actual late original registry recovery read after confirmed deletion'
        saved_registry=await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts;await lost_calculation(page,service,bridge)
        await helpers._native_tls_completed_read(page,service.origin+'/api/research?limit=20',lambda:page.reload());await expect(page.locator('#research-list-status')).to_contain_text('已读取 1 条研究')
        held=[]
        async def hold(route):
            request=route.request;actual=await asyncio.to_thread(bridge.forward,request.method,request.url,await request.all_headers(),request.post_data_buffer);assert actual.status==200;held.append((route,actual))
        await page.route(service.origin+'/api/research/'+service.seed.research_id+'/financial-registries/'+saved_registry['metadata']['registry_ref']['id'],hold,times=1)
        await page.locator('#financial-scenario-recovery-material').click();deadline=time.monotonic()+8
        while not held and time.monotonic()<deadline:await asyncio.sleep(.02)
        assert len(held)==1
        assert (await helpers._native_tls_fetch(page,'/api/me/delete','POST',{'confirmation':'DELETE'}))['status']==200
        await page.locator('#research-list-refresh').click();await expect(page.locator('#problem-form')).to_be_hidden();assert await pending(page)=={}
        route,actual=held.pop();await route.fulfill(status=actual.status,headers=dict(actual.headers),body=actual.body);await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        await expect(page.locator('#financial-scenario-result')).to_have_text('');await expect(page.locator('#financial-scenario-form')).not_to_contain_text('Example group');await expect(page.locator('#financial-scenario-calculate')).to_be_disabled();assert await count(service)==0
        facts.update({'real_GET_before_delete_late_response':True,'recovery_catalog_not_revived':True,'pending_erased':True,'no_new_calc_permit':True})


def test_fin3_actual_main_late_recovery_catalog_not_revived_after_delete(tmp_path):asyncio.run(late_recovery_catalog(tmp_path))


async def mode_drafts(tmp_path):
    async with fin1.actual_browser(tmp_path) as (page,service,bridge,facts):
        facts['scope']='FIN3 repaired cost/allocation modes, explicit units, isolated drafts and actual save'
        await choose_material(page,service,bridge);facts['loaded_scripts']=service._fin3_loaded_scripts;await fill_form(page)
        posts=[];page.on('request',lambda r:posts.append(r.post_data) if r.method=='POST' and r.url.endswith('/financial-calculations') else None)
        await page.locator('#financial-scenario-s0-cost-panel').evaluate('(n)=>n.open=true');await page.locator('#financial-scenario-s0-add-cost').click()
        await page.locator('#financial-scenario-s0-cost0-label').fill('合成五项成本');await page.locator('#financial-scenario-s0-cost0-coverage').fill('五项均明确包含，无重复，仅合成条件。')
        for tag in ['base_operating_cost','base_operating_expense','shared_cost','depreciation','sbc']:await page.locator('#financial-scenario-s0-cost0-'+tag).check()
        await page.locator('#financial-scenario-s0-cost0-mode').select_option('revenue_ratio')
        for year in [2026,2027]:
            await page.locator(f'#financial-scenario-s0-cost0-enabled-{year}').check();await page.locator(f'#financial-scenario-s0-cost0-{year}-value').fill('25');await page.locator(f'#financial-scenario-s0-cost0-{year}-reason').fill('原25%成本条件')
        await page.locator('#financial-scenario-s0-cost0-mode').select_option('amount')
        for year in [2026,2027]:
            for field in ['value','unit','currency']:await expect(page.locator(f'#financial-scenario-s0-cost0-{year}-{field}')).to_have_value('')
            await page.locator(f'#financial-scenario-s0-cost0-{year}-value').fill('50');await page.locator(f'#financial-scenario-s0-cost0-{year}-reason').fill('重新明确50百万美元成本条件')
        await page.locator('#financial-scenario-consent').check();await page.locator('#financial-scenario-calculate').click();await expect(page.locator('#financial-scenario-status')).to_contain_text('成本金额/比例单位或币种不匹配');assert posts==[] and await pending(page)=={} and await count(service)==0
        for year in [2026,2027]:
            await page.locator(f'#financial-scenario-s0-cost0-{year}-unit').select_option('million');await page.locator(f'#financial-scenario-s0-cost0-{year}-currency').select_option('USD')
        await page.locator('#financial-scenario-s0-cost0-mode').select_option('revenue_ratio')
        for year in [2026,2027]:
            await expect(page.locator(f'#financial-scenario-s0-cost0-{year}-value')).to_have_value('25');await expect(page.locator(f'#financial-scenario-s0-cost0-{year}-unit')).to_have_count(0)
        await page.locator('#financial-scenario-s0-cost0-mode').select_option('amount')
        for year in [2026,2027]:
            await expect(page.locator(f'#financial-scenario-s0-cost0-{year}-value')).to_have_value('50');await expect(page.locator(f'#financial-scenario-s0-cost0-{year}-unit')).to_have_value('million');await expect(page.locator(f'#financial-scenario-s0-cost0-{year}-currency')).to_have_value('USD')
        await page.locator('#financial-scenario-categories-panel').evaluate('(n)=>n.open=true');await page.locator('#financial-scenario-add-category').click();await page.locator('#financial-scenario-category-0-label').fill('合成业务');await page.locator('#financial-scenario-category-0-definition').fill('独立业务部分，其余收入进入未分配。');await page.locator('#financial-scenario-categories-confirmed').check()
        await page.locator('#financial-scenario-s0-allocations-panel').evaluate('(n)=>n.open=true');await page.locator('#financial-scenario-s0-add-allocation').click();await page.locator('#financial-scenario-s0-allocation0-category').select_option('0')
        for year in [2026,2027]:
            await page.locator(f'#financial-scenario-s0-allocation0-enabled-{year}').check();await page.locator(f'#financial-scenario-s0-allocation0-{year}-value').fill('30');await page.locator(f'#financial-scenario-s0-allocation0-{year}-reason').fill('独立30百万美元业务条件')
        await page.locator('#financial-scenario-s0-allocation0-mode').select_option('share')
        for year in [2026,2027]:
            await expect(page.locator(f'#financial-scenario-s0-allocation0-{year}-value')).to_have_value('');await expect(page.locator(f'#financial-scenario-s0-allocation0-{year}-unit')).to_have_count(0);await page.locator(f'#financial-scenario-s0-allocation0-{year}-value').fill('25');await page.locator(f'#financial-scenario-s0-allocation0-{year}-reason').fill('独立25%业务条件')
        await page.locator('#financial-scenario-s0-allocation0-mode').select_option('amount')
        for year in [2026,2027]:
            await expect(page.locator(f'#financial-scenario-s0-allocation0-{year}-value')).to_have_value('30');await expect(page.locator(f'#financial-scenario-s0-allocation0-{year}-unit')).to_have_value('million');await expect(page.locator(f'#financial-scenario-s0-allocation0-{year}-currency')).to_have_value('USD')
        await page.locator('#financial-scenario-s0-allocation0-mode').select_option('share');await expect(page.locator('#financial-scenario-s0-allocation0-2026-value')).to_have_value('25');await page.locator('#financial-scenario-s0-allocation0-mode').select_option('amount');await expect(page.locator('#financial-scenario-consent')).not_to_be_checked()
        await page.locator('#financial-scenario-s0-allocation0-2027-currency').select_option('');await page.locator('#financial-scenario-consent').check();await page.locator('#financial-scenario-calculate').click();await expect(page.locator('#financial-scenario-status')).to_contain_text('分配金额/比例单位或币种不匹配');assert posts==[] and await pending(page)=={} and await count(service)==0
        await page.locator('#financial-scenario-s0-allocation0-2027-currency').select_option('USD');await page.locator('#financial-scenario-consent').check()
        url=service.origin+'/api/research/'+service.seed.research_id+'/financial-calculations'
        async with bridge.capture_response(page,'POST',url) as captured:
            async with page.expect_response(url) as saved:await page.locator('#financial-scenario-calculate').click()
            response=await saved.value;assert response.status==200,await response.text();data=(await captured.json(response))['data']
        await expect(page.locator('#financial-scenario-status')).to_contain_text('条件计算已保存');assert len(posts)==1 and await count(service)==1
        request=json.loads(posts[0])['data']['request']['scenarios'][0]
        assert request['costs'][0]['mode']==request['allocations'][0]['mode']=='amount'
        for name,value in [('costs','50'),('allocations','30')]:
            assert len(request[name][0]['values'])==2
            for item in request[name][0]['values']:assert item['parameter']['value']==value and item['parameter']['unit']=='million' and item['parameter']['currency']=='USD'
        await page.get_by_role('button',name='年度底表',exact=True).click();await expect(page.locator('#financial-scenario-result')).to_contain_text('150.000000');await expect(page.locator('#financial-scenario-result')).to_contain_text('30.000000')
        facts.update({'active_years':[2026,2027],'cost_ratio_amount_roundtrip_preserved':True,'allocation_amount_share_roundtrip_preserved':True,'first_other_mode_clears_numeric_and_monetary_requires_selection':True,'unconfirmed_consent_reset':True,'bad_unit_or_currency_preflight_posts':0,'successful_posts':1,'actual_result_rows':1,'saved_modes_units_currency_correct':True,'result_ref':data['metadata']['result_ref']})


def test_fin3_actual_main_mode_drafts_units_preflight_and_save(tmp_path):asyncio.run(mode_drafts(tmp_path))
