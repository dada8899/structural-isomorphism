"""Synthetic rejection/cleanup controls; real Main browser tests prove transport.

These controls neither forward HTTP nor establish a successful product receipt.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from web.backend.tests.acceptance.plan_browser_service import (
    BridgeResponse, CanonicalBrowserBridge, _BrowserResponseCapture, ORIGIN,
)


class Request:
    def __init__(self,page,*,method='POST',url=ORIGIN+'/api/synthetic',body=b'{}'):
        self.frame=SimpleNamespace(page=page)
        self.method,self.url,self.post_data_buffer=method,url,body
    async def all_headers(self):return {'x-owned-synthetic':'one'}


def test_capture_rejects_same_value_other_identity_and_ambiguous_second_request():
    async def run():
        page=object();first=Request(page);other=Request(page)
        captured=_BrowserResponseCapture(page,'POST',first.url,1)
        try:
            assert captured.bind(first,await first.all_headers(),first.post_data_buffer)
            captured.actual=BridgeResponse(409,(),b'{"error":"synthetic refusal"}')
            captured.future.set_result(None)
            response=SimpleNamespace(request=other,url=other.url,status=409)
            with pytest.raises(AssertionError,match='identity differs'):await captured.json(response)
            assert not captured.bind(other,await other.all_headers(),other.post_data_buffer)
            response.request=first
            with pytest.raises(AssertionError,match='identity differs'):await captured.json(response)
        finally:captured.clear()
        assert captured.request is captured.request_body is captured.request_headers is captured.actual is None
    asyncio.run(run())


@pytest.mark.parametrize('difference',['status','body','headers','invalid_json'])
def test_capture_cannot_turn_different_or_invalid_actual_receipt_into_success(difference):
    async def run():
        page=object();request=Request(page);captured=_BrowserResponseCapture(page,'POST',request.url,1)
        try:
            assert captured.bind(request,await request.all_headers(),request.post_data_buffer)
            captured.actual=BridgeResponse(422,(),b'not json' if difference=='invalid_json' else b'{"error":"refused"}')
            captured.future.set_result(None)
            response=SimpleNamespace(request=request,url=request.url,status=200 if difference=='status' else 422)
            if difference=='body':request.post_data_buffer=b'{"changed":true}'
            if difference=='headers':captured.request_headers={'x-owned-synthetic':'other'}
            error=json.JSONDecodeError if difference=='invalid_json' else AssertionError
            with pytest.raises(error):await captured.json(response)
        finally:captured.clear()
    asyncio.run(run())


@pytest.mark.parametrize('end',['timeout','cancel','body_failure'])
def test_capture_scope_removes_private_references_on_every_early_exit(end):
    async def run():
        context=object();page=SimpleNamespace(context=context)
        bridge=CanonicalBrowserBridge.__new__(CanonicalBrowserBridge)
        bridge.active=True;bridge._routed_context=context;bridge._captures=[]
        async def use():
            async with bridge.capture_response(page,'POST',ORIGIN+'/api/synthetic',timeout=.01) as captured:
                saved.append(captured)
                if end=='body_failure':raise RuntimeError('synthetic body failure')
                if end=='cancel':
                    asyncio.current_task().cancel()
                    await asyncio.sleep(0)
                await captured.json(None)
        saved=[]
        expected={'timeout':TimeoutError,'cancel':asyncio.CancelledError,'body_failure':RuntimeError}[end]
        with pytest.raises(expected):await use()
        assert bridge._captures==[] and saved[0].future.done()
        assert saved[0].page is saved[0].request is saved[0].actual is None
    asyncio.run(run())


def test_capture_deadline_drops_received_bytes_even_when_caller_does_not_read():
    async def run():
        page=object();request=Request(page);captured=_BrowserResponseCapture(page,'POST',request.url,.01)
        try:
            assert captured.bind(request,await request.all_headers(),request.post_data_buffer)
            captured.actual=BridgeResponse(409,(),b'{"error":"synthetic refusal"}')
            captured.future.set_result(None)
            await asyncio.sleep(.02)
            assert captured.expired and captured.page is captured.request is captured.actual is None
            with pytest.raises(TimeoutError):await captured.json(None)
        finally:captured.clear()
    asyncio.run(run())


def test_overlapping_capture_is_rejected_without_replacing_original_scope():
    async def run():
        context=object();page=SimpleNamespace(context=context)
        bridge=CanonicalBrowserBridge.__new__(CanonicalBrowserBridge)
        bridge.active=True;bridge._routed_context=context;bridge._captures=[]
        async with bridge.capture_response(page,'POST',ORIGIN+'/api/synthetic') as first:
            with pytest.raises(RuntimeError,match='one response capture'):
                async with bridge.capture_response(page,'POST',ORIGIN+'/api/different'):pass
            assert bridge._captures==[first] and not first.future.done()
        assert bridge._captures==[] and first.future.cancelled()
    asyncio.run(run())
