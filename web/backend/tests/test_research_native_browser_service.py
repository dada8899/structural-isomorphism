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
