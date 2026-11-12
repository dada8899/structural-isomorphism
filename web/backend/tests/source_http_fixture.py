"""Owned loopback source server and spawn-safe HTTP worker."""
from contextlib import contextmanager
import http.client
import json
import threading
import os
from pathlib import Path
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs,urlsplit

DOI="10.1371/journal.pone.0015032"
TITLE="Synthetic queue methods"
ARTICLE=(f'<html><meta name="citation_doi" content="{DOI}"><meta name="citation_title" content="{TITLE}">'
    '<section class="article-body"><div id="artText">'
    '<p>Waiting time depends on arrivals and service variability.</p><div class="articleinfo">'
    f'<p>Citation: {TITLE}. https://doi.org/{DOI}</p>'
    '<p>Copyright: This is an open-access article distributed under the terms of the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original author and source are credited</p>'
    '</div></div></section></html>').encode()
METADATA=json.dumps({"status":"ok","message-type":"work-list","message":{"items":[{"DOI":DOI,"title":[TITLE],"license":[{"URL":"https://creativecommons.org/licenses/by/4.0/","content-version":"vor"}]}]}}).encode()


def get_local(port,target):
    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=2)
    try:
        connection.request("GET","/discovery" if target.host=="api.crossref.org" else "/article")
        response=connection.getresponse();raw=response.read(2097153)
        return response.status,response.getheader("Content-Type"),raw,raw
    finally:connection.close()


def drop_after_response(port,target):
    get_local(port,target)
    raise OSError("synthetic lost source response")


def get_local_targets(port,target):
    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=2)
    try:
        connection.request("GET",target.path)
        response=connection.getresponse();raw=response.read(2097153)
        return response.status,response.getheader("Content-Type"),raw,raw
    finally:connection.close()


def wait_before_get(port,ready,go,target):
    Path(ready).write_text(json.dumps({"sender_pid":os.getpid()}))
    while not Path(go).exists():time.sleep(.01)
    return get_local(port,target)


def worker_main():
    import sys
    from functools import partial
    from api import auth
    from research import ResearchStore,ResearchRunner
    from research.source_policy import PinnedPublicTransport
    task_id,port,ready,go=sys.argv[1:]
    # -m runs this entry as __main__; the isolated sender imports callbacks by
    # their real module name and deliberately never re-executes the main entry.
    from web.backend.tests.source_http_fixture import wait_before_get as owned_wait_before_get
    transport=PinnedPublicTransport(_worker=partial(owned_wait_before_get,int(port),ready,go))
    ResearchRunner(ResearchStore(auth._store()),source_transport=transport).run_once(task_id)


@contextmanager
def source_server(*,metadata=METADATA,article=ARTICLE):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            calls.append(self.path)
            if self.path=="/discovery" or self.path.startswith("/works?"):body,kind=metadata,"application/json"
            else:
                body=article[parse_qs(urlsplit(self.path).query)["id"][0]] if isinstance(article,dict) else article
                kind="text/html"
            self.send_response(200);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server.server_port,calls
    finally:server.shutdown();server.server_close();thread.join(3)


if __name__=="__main__":worker_main()
