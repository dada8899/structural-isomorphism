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
