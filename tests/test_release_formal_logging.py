"""Actual Main rejects a real disk sink while pytest log capture stays active."""
import asyncio
import logging

import pytest

from web.backend.tests.test_formal_main_admission import prepared,smtp


def test_actual_formal_main_still_refuses_application_file_handler(prepared,tmp_path,caplog):
    main,admission,_,_=prepared
    root=logging.getLogger()
    handler=logging.FileHandler(tmp_path/"synthetic-application.log")
    root.addHandler(handler)
    async def check():
        with pytest.raises(RuntimeError,match="formal logging must be stdout only"):
            async with main.lifespan(main.app):
                pytest.fail("disk logging may not reach admitted Main")
    try:
        logging.getLogger("release-proof").warning("public log capture control")
        assert any(record.name=="release-proof" and record.levelno==logging.WARNING for record in caplog.records)
        asyncio.run(check())
    finally:
        root.removeHandler(handler)
        handler.close()
    assert admission._STATE.get(id(main.app)) is None


def test_actual_formal_dev_formal_lifetimes_restore_main_cache_and_saved_owner(prepared,monkeypatch,tmp_path):
    import sys
    import os
    import httpx
    from tests.test_legacy_paid_admission import app_env
    from web.backend.tests.test_formal_main_admission import BETA,envelope,login,problem
    main,admission,_,messages=prepared
    async def verify():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as owner:
            async with main.lifespan(main.app):
                await login(owner,messages)
                saved=await owner.post("/api/research",json=envelope({"problem":problem()}),
                    headers={"Origin":BETA,"Idempotency-Key":"formal-dev-formal"})
                assert saved.status_code==200
                rid=saved.json()["data"]["research"]["id"]
                original=(await owner.get("/api/research/"+rid)).json()
            assert admission._STATE.get(id(main.app)) is None
            assert sys.modules["main"] is main
            dev_root=tmp_path/"legacy-dev"
            dev_root.mkdir()
            with monkeypatch.context() as dev_patch:
                # prepared's formal-only test tripwire also sees pytest's
                # setenv bookkeeping. No formal app is active in this dev
                # interval, and the synthetic provider name is proved absent.
                assert "OPENROUTER_API_KEY" not in os.environ
                dev_patch.setattr(os.environ,"get",type(os.environ).get.__get__(os.environ,type(os.environ)))
                fixture=app_env.__wrapped__(dev_patch,dev_root)
                try:
                    dev,client,_,_=next(fixture)
                    assert dev is not main and sys.modules["main"] is dev and dev._LAUNCH_FORMAL is False
                    rejected=client.post("/api/ask/stream",json={"query":"x"*8001})
                    assert rejected.status_code==422
                finally:
                    fixture.close()
            assert sys.modules["main"] is main and main._LAUNCH_FORMAL is True
            async with main.lifespan(main.app):
                reopened=await owner.get("/api/research/"+rid)
                assert reopened.status_code==200 and reopened.json()==original
            assert admission._STATE.get(id(main.app)) is None
    asyncio.run(verify())
