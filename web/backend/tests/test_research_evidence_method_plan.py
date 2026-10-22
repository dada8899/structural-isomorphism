"""Real canonical Main15, old producer Source and dedicated evidence routes.

Historical13->14->15 preparation preserves real acquisition/licence rows; it is
not a Source15 fetch or a live research-maturity claim. The current HTTP surface
uses actual cookie/Origin and Main binding without feature substitutions.
"""
# The original historical producer executes unchanged. This private entry only
# fixes its real loopback server's article argument before its internal import;
# no row/guard/origin/old-code bytes are replaced and no frame is persisted.
import sys
if __name__=='__main__' and len(sys.argv)==8 and sys.argv[1]=='--evidence-credit-child':
    import importlib.util,functools,traceback
    from pathlib import Path
    source=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('owned_evidence_history_producer',source/'acceptance/source_history_fixture.py')
    historical=importlib.util.module_from_spec(spec);sys.modules[spec.name]=historical;spec.loader.exec_module(historical)
    from web.backend.tests import source_http_fixture as http_fixture
    original=http_fixture.source_server
    credit=http_fixture.ARTICLE.replace(('Citation: '+http_fixture.TITLE).encode(),('Citation: Example A, Example B (2026) '+http_fixture.TITLE).encode())
    http_fixture.source_server=functools.partial(original,article=credit)
    try:historical._child(*sys.argv[2:7],sys.argv[7]=='1')
    except Exception as error:
        import json
        frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)[-8:]]
        sys.stderr.write('HISTORY_PREP_SAFE_ERROR:'+json.dumps({'type':type(error).__name__,'frames':frames})+'\n');raise SystemExit(1)
    raise SystemExit(0)

# Native spawn re-executes the main file as __mp_main__; only its original
# worker target is loaded there, never the current A/pytest test imports.
if __name__!='__mp_main__':
    from contextlib import contextmanager
    from pathlib import Path
    import json
    import pytest
    from research import ResearchStore
    from research.authorization import AccountIdentity
    from research import evidence_method_plan_schemas as types
    from research.provider_schemas import canonical,digest
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService


    @contextmanager
    def actual(tmp_path,*,full_credit=True):
        service=FormalMainBrowserService(tmp_path/'evidence-main')
        # Exactly the existing helper's one synthetic child is redirected to the
        # fixed wrapper above; all real Main/HTTP/subprocess behavior stays native.
        import subprocess
        from unittest.mock import patch
        original_popen=subprocess.Popen
        helper=Path(__file__).parent/'acceptance/source_history_fixture.py'
        def fixed_credit_child(command,*args,**kwargs):
            if (full_credit and type(command) is list and len(command)==9 and command[1]==str(helper.resolve()) and command[2]=='--seed-child'):
                command=[command[0],str(Path(__file__).resolve()),'--evidence-credit-child',*command[3:]]
            return original_popen(command,*args,**kwargs)
        with patch.object(subprocess,'Popen',fixed_credit_child),service:
            client=service.client
            assert client.request('POST','/api/auth/request-link',{'email':service.seed.email})[0]==200
            token=service.take_latest_magic_token()
            try:assert client.request('POST','/api/auth/verify',{'token':token})[0]==200
            finally:token=None
            from api import auth
            claims=auth._decode_jwt(next(c.value for c in client.cookies if c.name=='phase_session'))
            actor=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp']);claims=None
            store=ResearchStore(auth._store())
            try:yield service,client,store,actor
            finally:
                from research import evidence_method_plan as core
                assert not core._READERS
        assert not service.root.exists()


    def send(client,rid,suffix,data,key):
        return client.request('POST','/api/research/'+rid+'/'+suffix,{'schema_version':'structure-research-v1','contract_revision':types.CONTRACT,'data':data},key=key)


    def preview(service,client,**changes):
        data=dict(input_revision=1,expected_research_version=service.seed.research_version,
            excerpt_refs=[service.seed.excerpt_refs[0]['excerpt_id']],context_declaration='self_declared')
        data.update(changes)
        return send(client,service.seed.research_id,'evidence-method-plan-previews',data,'evidence-preview')


    def approve(service,client,value,key='evidence-confirm'):
        data={k:value[k] for k in ('preview_ref','preview_digest','request_digest','selection_manifest_digest','approved_upper_units')}
        data.update(expected_research_version=value['research_version'],confirm_outbound=True)
        return send(client,service.seed.research_id,'evidence-method-plan-approvals',data,key),data


    def test_actual_main_closed_preview_exact_selection_and_no_birth(tmp_path):
        with actual(tmp_path) as (service,client,store,actor):
            with store.transaction() as conn:
                before=tuple(conn.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('research_tasks','research_funding_accounts','research_plan_native_runs'))
            status,response=preview(service,client);assert status==200,response
            value=response['data'];assert value['can_confirm'] is False and value['funding_reason']=='FUNDING_CLOSED'
            assert value['exact_input']['handles'][0]['origin']=='offline_probe'
            assert value['exact_input']['handles'][0]['read_scope']=='author_narrative_subset'
            assert value['model_analysis_ran'] is value['real_model_executed'] is False
            assert value['exact_input']['problem_context']['summary']!='仅供受控历史来源准备的合成问题。'
            assert preview(service,client)==(status,response)
            denied,_=approve(service,client,value);assert denied[0]==503 and denied[1]['error']['code']=='FUNDING_CLOSED'
            with store.transaction() as conn:
                assert before==tuple(conn.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('research_tasks','research_funding_accounts','research_plan_native_runs'))
                assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
            assert client.request('GET','/api/research/'+service.seed.research_id+'/evidence-method-plans')[1]['data']['items']==[]


    @pytest.mark.parametrize('change',['extra','fake_scope','old_contract','duplicate','foreign','stale','revision'])
    def test_actual_preview_rejects_ambiguous_selection_or_client_authority(tmp_path,change):
        with actual(tmp_path) as (service,client,store,actor):
            if change=='extra':status,value=preview(service,client,verified=True)
            elif change=='fake_scope':status,value=preview(service,client,provider_outbound=True)
            elif change=='old_contract':
                status,value=client.request('POST','/api/research/'+service.seed.research_id+'/evidence-method-plan-previews',{'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':{}},key='wrong-contract')
            elif change=='duplicate':status,value=preview(service,client,excerpt_refs=[service.seed.excerpt_refs[0]['excerpt_id']]*2)
            elif change=='foreign':status,value=preview(service,client,excerpt_refs=['ffffffff-ffff-4fff-bfff-ffffffffffff'])
            elif change=='stale':status,value=preview(service,client,expected_research_version=service.seed.research_version+1)
            else:status,value=preview(service,client,input_revision=2)
            assert status in (404,409,422),value
            with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_plan_native_previews').fetchone()[0]==0


    def test_actual_main_wire_query_current_acl_and_dto_do_not_install_authority(tmp_path):
        import urllib.request,urllib.error
        with actual(tmp_path) as (service,client,store,actor):
            rid=service.seed.research_id;path='/api/research/'+rid+'/evidence-method-plan-previews'
            cases=[(b'{"schema_version":"structure-research-v1","schema_version":"structure-research-v1"}',422),
                (b'{"data":NaN}',422),(b'{"data":1.0}',422),(b'\xef\xbb\xbf{}',422),(b' '*65537,413),
                (b'{"x":'+b'['*25+b'0'+b']'*25+b'}',413)]
            for raw,expected in cases:
                request=urllib.request.Request(service.origin+path,data=raw,method='POST',headers={'Origin':service.origin,'Content-Type':'application/json','Idempotency-Key':'strict-wire'})
                try:response=client.opener.open(request,timeout=5)
                except urllib.error.HTTPError as error:response=error
                with response:
                    assert response.status==expected
                    body=response.read(4097);assert len(body)<=4096
                    assert set(json.loads(body))=={'error'}
            for query in ('limit=0','limit=01','limit=21','limit=true','limit=1&limit=2','cursor=abc','other=1'):
                status,body=client.request('GET','/api/research/'+rid+'/evidence-method-plans?'+query)
                assert status==422,body
            from research.paid_control import AuthenticatedActionSource
            from research import evidence_method_plan as plan
            with pytest.raises(TypeError):AuthenticatedActionSource(identity=actor,action='evidence-method-preview')
            with pytest.raises(PermissionError):plan.read_evidence_http_in(None,__import__('research',fromlist=['ResearchService']).ResearchService(store),None,actor,{},rid,1,1,(),'preview')
            with store.transaction(write=True) as conn:
                conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')",(rid,))
            status,body=preview(service,client);assert status==404 and body['error']['code']=='NOT_FOUND'
            assert client.request('GET','/api/research/'+rid+'/evidence-method-plans')[0]==404
            with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_plan_native_previews').fetchone()[0]==0


    def test_actual_fixed_credit_child_preserves_source_refs_time_and_data_only_eligibility(tmp_path):
        from research.evidence_repository import EvidenceRepository
        from research.source_integration import authorizer,context_for
        with actual(tmp_path) as (service,client,store,actor):
            rid=service.seed.research_id;tid=service.seed.source_task_id
            status,records=client.request('GET','/api/research/'+rid+'/records?task_id='+tid+'&kind=excerpts')
            assert status==200 and records['data']['items']
            with store.transaction() as conn:
                assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
                repository=EvidenceRepository(conn,authorizer(store,identity=actor));context=context_for(conn,tid)
                ref=service.seed.excerpt_refs[0]['excerpt_id']
                candidate,handle=repository.preview_provider_handle(context,ref,'e1')
                assert candidate.excerpt_id==ref and candidate.acquired_at==service.seed.acquired_at and candidate.origin=='offline_probe'
                assert candidate.read_scope=='author_narrative_subset' and candidate.may_send_to_provider is False
                assert handle.attribution.startswith('Example A, Example B (2026) — ')
                assert conn.execute("SELECT count(*) FROM research_source_requests WHERE task_id=? AND outcome='SUCCEEDED'",(tid,)).fetchone()[0]==2
                assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
            print('A_SOURCE_PREPARATION:actual_original13_HTTP_2GET_to15_same_ref_time_complete_synthetic_credit_data_only')

    def test_actual_missing_complete_credit_never_produces_preview_or_task(tmp_path):
        with actual(tmp_path,full_credit=False) as (service,client,store,actor):
            status,value=preview(service,client)
            assert status==409 and value['error']['code']=='SOURCE_PERMISSION_UNAVAILABLE'
            with store.transaction() as conn:
                assert conn.execute('SELECT count(*) FROM research_plan_native_previews').fetchone()[0]==0
                assert conn.execute('SELECT count(*) FROM research_plan_native_runs').fetchone()[0]==0

    def test_actual_cross_account_and_readonly_current_owner_cannot_preview(tmp_path):
        from .test_formal_main_admission import envelope,problem
        from research.authorization import AuthorizationGate
        with actual(tmp_path) as (service,client,store,actor):
            rid=service.seed.research_id
            assert client.request('POST','/api/auth/request-link',{'email':'other-evidence@example.invalid'})[0]==200
            token=service.take_latest_magic_token()
            try:assert client.request('POST','/api/auth/verify',{'token':token})[0]==200
            finally:token=None
            status,other=client.request('POST','/api/research',envelope({'problem':problem()}),key='other-evidence-root')
            assert status==200,other
            status,denied=preview(service,client);assert status==404 and denied['error']['code']=='NOT_FOUND'
            assert client.request('GET','/api/research/'+rid+'/evidence-method-plans')[0]==404
            # Restore a fresh genuine session for the original current owner.
            assert client.request('POST','/api/auth/request-link',{'email':service.seed.email})[0]==200
            token=service.take_latest_magic_token()
            try:assert client.request('POST','/api/auth/verify',{'token':token})[0]==200
            finally:token=None
            with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
            with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                lease.identity
                conn.execute("UPDATE research_grants SET scopes='[\"read\"]' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='write')",(rid,))
            status,denied=preview(service,client);assert status==404 and denied['error']['code']=='NOT_FOUND'
            assert client.request('GET','/api/research/'+rid+'/evidence-method-plans')[0]==200
            with store.transaction() as conn:
                assert conn.execute('SELECT count(*) FROM research_plan_native_previews').fetchone()[0]==0
                assert conn.execute('SELECT count(*) FROM research_plan_native_runs').fetchone()[0]==0
