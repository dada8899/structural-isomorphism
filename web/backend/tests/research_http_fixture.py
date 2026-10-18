"""Persistent, loopback-only external fixture; never a real provider."""
from __future__ import annotations

import json
from contextlib import closing
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ResearchHTTPFixture:
    def __init__(self,path):
        self.path=path
        self.costs={"discover_sources":4000,"compose_report":3000}
        self.final=True
        self.currency="USD"
        self.scale=6
        self.notes=True
        self.note_override=None
        self.drip_delay=0
        self.closed=threading.Event()
        self.drop=set()
        self.received=threading.Event()
        self.release=threading.Event();self.release.set()
        with closing(sqlite3.connect(path)) as conn,conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("CREATE TABLE IF NOT EXISTS calls(dispatch_id TEXT PRIMARY KEY,operation TEXT,receipt TEXT,posts INTEGER); CREATE TABLE IF NOT EXISTS observations(seq INTEGER PRIMARY KEY AUTOINCREMENT,method TEXT,dispatch_id TEXT);")
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,status,value):
                raw=json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers()
                try:
                    if fixture.drip_delay:
                        for byte in raw:
                            if fixture.closed.is_set():break
                            self.wfile.write(bytes([byte]));self.wfile.flush();time.sleep(fixture.drip_delay)
                    else:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_POST(self):
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=4096:return self.send(400,{})
                body=json.loads(self.rfile.read(length))
                operation=self.path.lstrip("/")
                if operation not in fixture.costs or set(body)!={"dispatch_id","input_digest","operation"} or body["operation"]!=operation:return self.send(400,{})
                dispatch=body["dispatch_id"]
                cost=fixture.costs[operation]
                result={"dispatch_id":dispatch,"receipt_ref":("final-" if fixture.final else "usage-")+dispatch,"final":fixture.final,
                        "cost":{"currency":fixture.currency,"scale":fixture.scale,"amount_units":cost} if cost is not None else None,
                        "note":("合成本机来源笔记；未检索真实资料。" if operation=="discover_sources" else "合成本机整理笔记；没有真实研究结论。") if fixture.notes else None}
                if fixture.note_override is not None:result["note"]=fixture.note_override
                with closing(sqlite3.connect(fixture.path,timeout=5)) as conn,conn:
                    old=conn.execute("SELECT receipt FROM calls WHERE dispatch_id=?",(dispatch,)).fetchone()
                    if old:
                        result=json.loads(old[0]);conn.execute("UPDATE calls SET posts=posts+1 WHERE dispatch_id=?",(dispatch,))
                    else:conn.execute("INSERT INTO calls VALUES(?,?,?,1)",(dispatch,operation,json.dumps(result,ensure_ascii=False)))
                    conn.execute("INSERT INTO observations(method,dispatch_id) VALUES('POST',?)",(dispatch,))
                fixture.received.set()
                if not fixture.release.wait(10):return self.send(503,{})
                if operation in fixture.drop:
                    self.close_connection=True
                    return
                self.send(200,result)
            def do_GET(self):
                if not self.path.startswith("/receipts/"):return self.send(404,{})
                dispatch=self.path.split("/")[-1]
                with closing(sqlite3.connect(fixture.path,timeout=5)) as conn,conn:
                    conn.execute("INSERT INTO observations(method,dispatch_id) VALUES('GET',?)",(dispatch,))
                    row=conn.execute("SELECT receipt FROM calls WHERE dispatch_id=?",(dispatch,)).fetchone()
                self.send(200,json.loads(row[0])) if row else self.send(404,{})
        self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.server.daemon_threads=False
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def count(self):
        with closing(sqlite3.connect(self.path)) as conn,conn:
            return conn.execute("SELECT COALESCE(SUM(posts),0) FROM calls").fetchone()[0]

    def receipt(self,dispatch):
        with closing(sqlite3.connect(self.path)) as conn,conn:
            return json.loads(conn.execute("SELECT receipt FROM calls WHERE dispatch_id=?",(dispatch,)).fetchone()[0])

    def change_receipt(self,dispatch,**changes):
        result=self.receipt(dispatch);result.update(changes)
        with closing(sqlite3.connect(self.path)) as conn,conn:conn.execute("UPDATE calls SET receipt=? WHERE dispatch_id=?",(json.dumps(result,ensure_ascii=False),dispatch))

    def close(self):
        self.closed.set();self.release.set();self.server.shutdown();self.server.server_close();self.thread.join(5)
