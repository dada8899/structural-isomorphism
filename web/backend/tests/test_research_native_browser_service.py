"""Actual loopback HTTPS component, not a completed browser/UI acceptance."""
import importlib.util
from pathlib import Path
import socket,ssl,threading,urllib.request
import pytest


def component():
    path=Path(__file__).parent/'acceptance'/'plan_browser_service.py'
    spec=importlib.util.spec_from_file_location('controlled_plan_browser_service',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_actual_https_registered_controller_worker_typed_same_ref_and_cleanup():
    result=component().self_test()
    assert result=={'scope':'controlled_fixture_only','schema':13,'financial':9,'actual_https':True,'canonical_origin_preserved':True,'same_process_worker':True,'provider_calls':['GET','POST'],'saved_same_ref_time':True,'real_model_executed':False,'automatically_created_sources':0,'cleanup':'closed'}
    assert not [t for t in threading.enumerate() if t.name.startswith('controlled-plan-')]


def test_https_fixture_validates_hostname_chain_secure_cookie_and_rejects_foreign_hosts():
    module=component()
    with module.PlanBrowserFixture() as service:
        root=service.root
        assert service.client.session()
        assert all(cookie.secure and cookie.has_nonstandard_attr('HttpOnly') for cookie in service.client.cookies if cookie.name=='phase_session')
        handler=module._OwnedHTTPSHandler(service.port,service.certificate)
        with pytest.raises(PermissionError):handler.https_open(urllib.request.Request('https://foreign.example.invalid/api/auth/me'))
        for trusted,hostname in ((False,'beta.structural.bytedance.city'),(True,'foreign.example.invalid')):
            context=ssl.create_default_context(cafile=str(service.certificate)) if trusted else ssl.create_default_context()
            with socket.create_connection(('127.0.0.1',service.port),timeout=2) as raw:
                with pytest.raises(ssl.SSLCertVerificationError):context.wrap_socket(raw,server_hostname=hostname)
        assert service.calls==[]
    assert not root.exists() and service.cleanup_errors==()
    assert not [t for t in threading.enumerate() if t.name.startswith('controlled-plan-')]


def test_repeated_failed_installation_closes_each_real_provider_before_reentry():
    module=component();service=module.PlanBrowserFixture(approved_cap_units=-1);resources=[]
    with service:
        root=service.root
        for _ in range(2):
            with pytest.raises(ValueError,match='native fixed-unit declaration required'):service.install_controlled_funding()
            resources.append((service.provider,service.provider_thread))
            assert service.provider.socket.fileno()==-1 and not service.provider_thread.is_alive()
            assert service.cleanup_errors==() and service.calls==[]
    assert all(server.socket.fileno()==-1 and not thread.is_alive() for server,thread in resources)
    assert not root.exists() and service.cleanup_errors==()


def test_real_authority_birth_failure_can_retry_without_adopting_orphan_resources(monkeypatch):
    import os
    from research import plan_native as native
    module=component();service=module.PlanBrowserFixture();authorities=[];resources=[];issue=native.issue_native_provision
    def failed(store,authority):
        authorities.append(authority)
        raise RuntimeError('synthetic failure after real authority birth')
    with service:
        root=service.root
        with monkeypatch.context() as scope:
            scope.setattr(native,'issue_native_provision',failed)
            for _ in range(2):
                with pytest.raises(RuntimeError,match='after real authority birth'):service.install_controlled_funding()
                resources.append((service.provider,service.provider_thread))
                assert service.provider.socket.fileno()==-1 and not service.provider_thread.is_alive()
                assert not authorities[-1].active and authorities[-1].reference not in native._AUTHORITIES
                with pytest.raises(OSError):os.fstat(authorities[-1].fd)
        assert native.issue_native_provision is issue and service.calls==[]
        with service.store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_plan_native_funding').fetchone()[0]==0
        service.install_controlled_funding()
        assert service.installed and service.worker.is_alive() and service.resource.active
        client=service.client
        problem={'entry':'phenomenon','original_input':module.OBSERVATION,'summary':'合成排队现象与等待时间的结构描述','objective':'理解合成等待','variables':[],'constraints':[],'unknowns':['到达规律尚未确认'],'confirmed':True}
        status,saved=client.request('POST','/api/research',module.envelope({'problem':problem}),key='retry-create');assert status==200
        rid=saved['data']['research']['id'];request={'input_revision':1,'expected_research_version':1,'observation_source':'own_observation','declaration_status':'self_declared'}
        status,preview=client.request('POST','/api/research/'+rid+'/plan-previews',module.envelope(request,'funded-plan-v2'),key='retry-preview');assert status==200
        confirmation={key:preview['data'][key] for key in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};confirmation['confirm_outbound']=True
        status,accepted=client.request('POST','/api/research/'+rid+'/plan-approvals',module.envelope(confirmation,'funded-plan-v2'),key='retry-confirm');assert status==200
        result=service.wait_result(rid,accepted['data']['result_ref'])
        assert result['data']['state']=='saved' and result['data']['content']['proposal']==module.CANDIDATE
        assert service.calls==['GET','POST'] and not service.worker_failures
    assert not root.exists() and service.cleanup_errors==()
    assert all(server.socket.fileno()==-1 and not thread.is_alive() for server,thread in resources)
    assert not [thread for thread in threading.enumerate() if thread.name.startswith('controlled-plan-')]


@pytest.mark.parametrize('failure',['provider_close','native_retirement'])
def test_uncertain_failed_installation_keeps_references_and_private_root(monkeypatch,failure):
    import shutil
    from research import plan_native as native
    module=component();service=module.PlanBrowserFixture(approved_cap_units=-1 if failure=='provider_close' else 41_000_000)
    close=module.ThreadingHTTPServer.server_close;provision_close=native.NativePlanProvision.close
    def failed_close(server):raise OSError('synthetic provider socket close uncertainty')
    def failed_mint(_provision):raise RuntimeError('synthetic failure after actual provision')
    def failed_retirement(provision):provision_close(provision);raise OSError('synthetic actual retirement uncertainty')
    try:
        with pytest.raises(RuntimeError,match='cleanup uncertain'):
            with service:
                root=service.root
                with monkeypatch.context() as scope:
                    if failure=='provider_close':scope.setattr(module.ThreadingHTTPServer,'server_close',failed_close)
                    else:
                        scope.setattr(native,'mint_runtime_permit',failed_mint)
                        scope.setattr(native.NativePlanProvision,'close',failed_retirement)
                    with pytest.raises((ValueError,RuntimeError)):service.install_controlled_funding()
                    provider,thread=service.provider,service.provider_thread
                    assert service.cleanup_errors and service.temp is not None and root.exists()
                    if failure=='provider_close':assert provider.socket.fileno()!=-1
                    else:assert service._failed_native
                    with pytest.raises(RuntimeError,match='cleanup uncertain'):service.install_controlled_funding()
                    assert (service.provider,service.provider_thread)==(provider,thread)
        # Even when later closes succeed, uncertainty is not silently relabelled
        # CLEAN; this test explicitly owns the final manual synthetic cleanup.
        assert service.cleanup_errors and service.temp is not None and root.exists()
        assert not service.provider_thread.is_alive() and service.provider.socket.fileno()==-1
    finally:
        monkeypatch.setattr(module.ThreadingHTTPServer,'server_close',close)
        monkeypatch.setattr(native.NativePlanProvision,'close',provision_close)
        try:service.close()
        except RuntimeError:pass
        if service.provider is not None:close(service.provider)
        if service.provider_thread is not None:service.provider_thread.join(3)
        assert not [thread for thread in threading.enumerate() if thread.name.startswith('controlled-plan-')]
        if service.temp is not None:shutil.rmtree(service.temp);service.temp=None
        assert not service.root.exists()


def test_static_pages_are_actual_repo_bytes_and_canonical_bridge_has_no_owner_cookie():
    import json
    from http.cookies import SimpleCookie
    module=component()
    with module.PlanBrowserFixture() as service,service.browser_bridge() as bridge:
        for path,relative in (('/research','research.html'),('/research/01234567-89ab-4def-8123-456789abcdef','research.html'),('/auth/login','auth-login.html'),('/auth/verify','auth-verify.html'),('/assets/research.js','assets/research.js'),('/assets/research.css','assets/research.css')):
            result=bridge.forward('GET',module.ORIGIN+path,{})
            assert result.status==200 and result.body==(module.ROOT/'web/frontend'/relative).read_bytes()
        assert bridge.forward('HEAD',module.ORIGIN+'/research',{}).body==b''
        redirect=bridge.forward('GET',module.ORIGIN+'/research/',{})
        assert redirect.status==307 and redirect.body==b'' # Actual upstream redirect; never followed.
        for path in ('/assets/','/auth.sqlite3','/tls/private.key','/api/fixture/install','/assets/../../state/auth.sqlite3'):
            assert bridge.forward('GET',module.ORIGIN+path,{}).status==404
        assert bridge.forward('GET',module.ORIGIN+'/api/auth/me',{}).status==401
        # The browser signs in through real HTTP. The controller's already
        # authenticated CookieJar is deliberately never consulted by bridge.
        payload=json.dumps({'email':module.OWNER}).encode()
        requested=bridge.forward('POST',module.ORIGIN+'/api/auth/request-link',{'Origin':module.ORIGIN,'Content-Type':'application/json'},payload)
        assert requested.status==200
        token=service.take_latest_magic_token()
        verified=bridge.forward('POST',module.ORIGIN+'/api/auth/verify',{'Origin':module.ORIGIN,'Content-Type':'application/json'},json.dumps({'token':token}).encode())
        assert verified.status==200
        cookies=SimpleCookie()
        for name,value in verified.headers:
            if name.lower()=='set-cookie':cookies.load(value)
        assert 'phase_session' in cookies
        flags=bool(cookies['phase_session']['secure'] and cookies['phase_session']['httponly']);assert flags
        actual='phase_session='+cookies['phase_session'].value
        assert bridge.forward('GET',module.ORIGIN+'/api/auth/me',{'Cookie':actual}).status==200
        assert bridge.forward('GET',module.ORIGIN+'/api/auth/me',{}).status==401
        denied=bridge.forward('POST',module.ORIGIN+'/api/auth/request-link',{'Origin':'null','Content-Type':'application/json'},payload)
        assert denied.status==403 and service.calls==[]
    assert service.cleanup_errors==() and not service.root.exists()
    assert not [t for t in threading.enumerate() if t.name.startswith('controlled-plan-')]


def test_static_reader_never_follows_symlinks_or_lists_directories(tmp_path,monkeypatch):
    module=component();fake=tmp_path/'public-repo';assets=fake/'web/frontend/assets';assets.mkdir(parents=True)
    outside=tmp_path/'private-synthetic.txt';outside.write_text('private fixture content')
    (assets/'leak.txt').symlink_to(outside)
    (assets/'linked-dir').symlink_to(tmp_path,target_is_directory=True)
    with module.PlanBrowserFixture() as service,service.browser_bridge() as bridge:
        with monkeypatch.context() as scope:
            scope.setattr(module,'ROOT',fake)
            for suffix in ('leak.txt','linked-dir/private-synthetic.txt','../private-synthetic.txt',''):
                assert bridge.forward('GET',module.ORIGIN+'/assets/'+suffix,{}).status==404
        assert outside.read_text()=='private fixture content'
    assert not service.root.exists()


def test_browser_bridge_rejects_foreign_urls_smuggling_and_unroutes_owned_hook():
    import asyncio
    module=component()
    with module.PlanBrowserFixture() as service,service.browser_bridge() as bridge:
        for url in ('http://beta.structural.bytedance.city/research','https://foreign.example.invalid/research','https://beta.structural.bytedance.city:443/research','https://u@beta.structural.bytedance.city/research'):
            with pytest.raises(PermissionError):bridge.forward('GET',url,{})
        for headers in ({'Host':'foreign.example.invalid'},{'Cookie':'bad\r\nHeader: x'},{'Content-Length':'999'},{'Transfer-Encoding':'chunked'}):
            with pytest.raises((ValueError,PermissionError)):bridge.forward('POST',module.ORIGIN+'/api/auth/me',headers,b'{}')
        with pytest.raises(ValueError):bridge.forward('POST',module.ORIGIN+'/api/auth/me',{},b'x'*(module.BRIDGE_LIMIT+1))
        class Context:
            async def set_offline(self,value):self.offline=value
            async def route(self,pattern,handler):self.pattern,self.handler=pattern,handler
            async def unroute(self,pattern,handler):assert (pattern,handler)==(self.pattern,self.handler);self.handler=None
        class Request:
            method='GET';url='https://foreign.example.invalid/research';post_data_buffer=None
            async def all_headers(self):return {}
        class Route:
            async def abort(self,reason):self.reason=reason
            async def fulfill(self,**kwargs):raise AssertionError('foreign request must not be fulfilled')
        async def exercise():
            context=Context();route=Route()
            async with bridge.routed(context):
                await context.handler(route,Request());assert route.reason=='blockedbyclient'
            assert context.handler is None and context.offline is True
        asyncio.run(exercise())
        with pytest.raises(PermissionError):bridge.forward('GET',module.ORIGIN+'/research',{})
        assert service.calls==[]
    assert not service.root.exists()


@pytest.mark.parametrize('failure',['offline','body_and_offline','offline_and_close'])
def test_bridge_offline_failure_retains_blocking_route_and_original_error(monkeypatch,failure):
    """Interface failure control; actual Playwright is verified separately."""
    import asyncio
    module=component()
    with module.PlanBrowserFixture() as service,service.browser_bridge() as bridge:
        close=bridge.close;close_calls=[]
        def close_then_fail_once():
            close_calls.append(True)
            if len(close_calls)==1:raise RuntimeError('synthetic close after retirement')
            close()
        if failure=='offline_and_close':monkeypatch.setattr(bridge,'close',close_then_fail_once)
        class Context:
            offline=False;handler=None;unroute_calls=0
            async def route(self,pattern,handler):self.handler=handler
            async def set_offline(self,value):raise OSError('synthetic offline transition failed')
            async def unroute(self,pattern,handler):self.handler=None;self.unroute_calls+=1
        class Route:
            async def abort(self,reason):self.reason=reason
            async def fulfill(self,**kwargs):raise AssertionError('retired bridge must never fulfill a request')
        async def exercise():
            context=Context();body_error=RuntimeError('synthetic original body failure')
            expected=RuntimeError if failure=='body_and_offline' else OSError
            with pytest.raises(expected) as caught:
                async with bridge.routed(context):
                    if failure=='body_and_offline':raise body_error
            assert context.offline is False and context.handler is not None and context.unroute_calls==0
            assert bridge.active is False
            route=Route()
            # The retained interception rejects before touching a request or
            # attempting upstream IO, including after cleanup has failed.
            await context.handler(route,None)
            assert route.reason=='blockedbyclient'
            if failure=='body_and_offline':
                assert caught.value is body_error
                assert any('OSError' in note for note in caught.value.__notes__)
            else:assert 'offline transition failed' in str(caught.value)
            if failure=='offline_and_close':
                assert close_calls and any('RuntimeError' in note for note in caught.value.__notes__)
            assert service.calls==[] and not bridge.pending
        asyncio.run(exercise())
    assert not service.root.exists() and service.cleanup_errors==()
    assert not [t for t in threading.enumerate() if t.name.startswith('controlled-plan-')]
