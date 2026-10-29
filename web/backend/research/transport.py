"""Bounded loopback-only fixture transport; real providers are not supported."""
from __future__ import annotations

import http.client
import json
import socket
import threading
import time

from .budget import canonical, require_enabled
from .schemas import FixtureResult


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError("duplicate response key")
        result[key]=value
    return result


def _constant(_):
    raise ValueError("nonfinite response")


def decode(raw):
    return FixtureResult.model_validate(json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,parse_constant=_constant))


class FixtureTransport:
    def __init__(self,port):
        require_enabled()
        if type(port) is not int or not 1<=port<=65535:raise ValueError("fixture port required")
        self.port=port

    def begin(self,operation,dispatch_id,input_digest):
        """Caller holds owner gate. Return only after real local send starts.

        Constructing a connection alone is not send evidence. The synchronous
        request below connects and sends headers/body before returning.
        """
        require_enabled()
        if operation not in {"discover_sources","compose_report"}:raise ValueError("unregistered fixture operation")
        body=canonical({"dispatch_id":dispatch_id,"input_digest":input_digest,"operation":operation}).encode()
        connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=2)
        connection._c0_deadline=time.monotonic()+5
        try:
            connection.request("POST","/"+operation,body=body,headers={"Content-Type":"application/json","Connection":"close"})
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def finish(connection):
        # Socket timeouts alone reset on each read and cannot bound a slow
        # byte stream. Shut down this exact socket at the absolute deadline.
        sock=connection.sock
        def stop_read():
            try:
                if sock is not None:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(max(0,connection._c0_deadline-time.monotonic()),stop_read)
        timer.start()
        try:
            response=connection.getresponse()
            raw=response.read(65537)
            if response.status!=200 or len(raw)>65536:raise ValueError("fixture response unavailable")
            return decode(raw)
        finally:
            timer.cancel();timer.join()
            connection.close()

    def receipt(self,dispatch_id):
        from uuid import UUID
        if str(UUID(dispatch_id,version=4))!=dispatch_id:raise ValueError("dispatch id required")
        connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=2)
        connection._c0_deadline=time.monotonic()+5
        try:
            connection.request("GET","/receipts/"+dispatch_id,headers={"Connection":"close"})
            return self.finish(connection)
        except ValueError:
            return None  # Missing/invalid receipt never proves free.
        finally:
            connection.close()
