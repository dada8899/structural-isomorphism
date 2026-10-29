"""Local fixed fixtures only: never call public DNS or external HTTP."""
from dataclasses import replace
from contextlib import contextmanager
import gzip
import hashlib
import http.client
import json
import multiprocessing
import os
import signal
import socket
import threading
import tempfile
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from web.backend.research.evidence_schemas import AnalysisPlan
from web.backend.research.authorization import AuthorizationGate
from web.backend.research.source_adapters.crossref_plos import CrossrefPlosChain, Hit, parse_article
from web.backend.research.source_policy import (
    PinnedPublicTransport, RequestTarget, RAW_CAP, SourceFailure,
    _network_get, article_target, decompress, discovery_target, public_addresses,
)


DOI = "10.1371/journal.pone.0015032"
TITLE = "Method fixture for stock market common factors"
NOTICE = ("permits unrestricted use, distribution, and reproduction in any medium, "
          "provided the original author and source are credited")
ARTICLE = (f'<html><meta name="citation_doi" content="{DOI}"><meta name="citation_title" content="{TITLE}">'
           '<script>never extracted()</script>'
           '<section class="article-body"><div id="artText" class="article-text">'
           '<p>Partial correlation is not a causality measure.</p><div class="articleinfo">'
           f'<p><strong>Citation: </strong>{TITLE}. https://doi.org/{DOI}</p>'
           f'<p><strong>Copyright: </strong>This is an open-access article distributed under the terms of the Creative Commons Attribution License, which {NOTICE}</p>'
           '</div></div></section></html>').encode()


def uid():
    return str(uuid4())


@contextmanager
def held_lease(allowed=True):
    if allowed is not True:
        yield False
        return
    with tempfile.TemporaryDirectory(prefix="source-test-owner-") as directory:
        from pytest import MonkeyPatch
        from web.backend.tests.test_research_source_spawn import development_auth
        with MonkeyPatch.context() as setup:
            backing = development_auth.__wrapped__(Path(directory), setup)
            gate=AuthorizationGate(backing)
            with gate.owner_gate_id(uid()) as lease:
                yield lease


def make_plan():
    return AnalysisPlan(id=uid(), research_id=uid(), input_revision=1, task_id=uid(), attempt=1,
        input_digest="a" * 64, query="stock market partial correlation", external_query_approved=True,
        objective="Examine candidate common factors", competing_explanations=("Common news",),
        required_evidence=("Methods and pilot identity",), stop_rule="Stop on limits", created_at="2026-10-17T00:00:00Z")


def discovery(items=None):
    return json.dumps({"status": "ok", "message-type": "work-list", "message": {"items": items if items is not None else [
        {"DOI": DOI, "title": [TITLE], "license": [{"URL": "http://creativecommons.org/licenses/by/4.0/", "content-version": "vor"}]}]}}).encode()


class FixtureTransport:
    execution_mode = "offline_probe"
    def __init__(self, records=None):
        self.records = records or [(200, "application/json", discovery(), discovery()), (200, "text/html;charset=UTF-8", ARTICLE, ARTICLE)]
        self.calls = []

    def get(self, target, *, still_authorized, owner_lease):
        owner_lease.identity
        self.calls.append(target)
        if not self.records:
            raise AssertionError("unexpected request")
        return self.records.pop(0)


def fast_worker(target):
    return 200, "text/html", b"local fixture", b"local fixture"


def slow_worker(target):
    time.sleep(20)
    return fast_worker(target)


def failed_worker(target):
    raise RuntimeError("private provider body must not leak")


def blocked_worker(target):
    raise SourceFailure("source HTTP status 403", http_status=403)


def exited_worker(target):
    os._exit(1)


class SourceTests(unittest.TestCase):
    def chain(self, transport=None, quota=None, authorized=None):
        @contextmanager
        def gate(*args):
            with held_lease((quota or (lambda *_: True))(*args)) as lease:
                yield lease
        return CrossrefPlosChain(make_plan(), transport or FixtureTransport(),
            request_gate=gate, still_authorized=authorized or (lambda: True), origin="offline_probe")

    def pinned(self,worker,seconds=3,authorized=None):
        with held_lease() as lease:
            return PinnedPublicTransport(wall_seconds=seconds,_worker=worker).get(article_target(DOI),still_authorized=authorized or (lambda:True),owner_lease=lease)

    def test_discovery_to_matched_licensed_original_is_not_model_research(self):
        chain = self.chain()
        self.assertEqual(chain.discover()[0].doi, DOI)
        snapshot, raw, extracted = chain.fetch(DOI)
        self.assertEqual(snapshot.origin, "offline_probe")
        self.assertEqual(raw, ARTICLE)
        self.assertNotIn("never extracted", extracted)
        self.assertIn("Partial correlation", extracted)
        self.assertTrue(snapshot.licence.private_cache)
        self.assertEqual(len(chain.transport.calls), 2)

    def test_fetch_requires_this_tasks_discovered_identity(self):
        chain = self.chain()
        with self.assertRaises(SourceFailure):
            chain.fetch(DOI)
        chain.discover()
        with self.assertRaises(SourceFailure):
            chain.fetch("10.1371/journal.pone.9999999")
        self.assertEqual(len(chain.transport.calls), 1)

    def test_no_retry_on_failed_discovery_or_article(self):
        chain = self.chain(FixtureTransport([(403, "text/html", b"blocked", b"blocked")]))
        with self.assertRaises(SourceFailure):
            chain.discover()
        with self.assertRaises(SourceFailure):
            chain.discover()
        self.assertEqual(len(chain.transport.calls), 1)
        chain = self.chain(FixtureTransport([(200, "application/json", discovery(), discovery()), (403, "text/html", b"blocked", b"blocked")]))
        chain.discover()
        with self.assertRaises(SourceFailure):
            chain.fetch(DOI)
        with self.assertRaises(SourceFailure):
            chain.fetch(DOI)
        self.assertEqual(len(chain.transport.calls), 2)

    def test_unknown_licence_does_not_allow_short_excerpt_or_cache(self):
        for article, hit in ((ARTICLE.replace(NOTICE.encode(), b"Unknown rights"), Hit(DOI, TITLE, True)),
                             (ARTICLE, Hit(DOI, TITLE, False))):
            _, licence = parse_article(article, hit)
            self.assertFalse(licence.private_cache)
            self.assertFalse(licence.display_excerpt)
            self.assertFalse(licence.export_excerpt)

    def test_quoted_or_comment_licence_cannot_override_article_copyright(self):
        grant = f'This is an open-access article distributed under the terms of the Creative Commons Attribution License, which {NOTICE}'
        copyright_p = f'<p><strong>Copyright: </strong>{grant}</p>'.encode()
        restricted = ARTICLE.replace(copyright_p, b'<p><strong>Copyright: </strong>All rights reserved.</p>')
        for foreign in (f'<blockquote>{grant}</blockquote>', f'<div class="comments"><p>{grant}</p></div>',
                        f'<section id="reader-comments"><p>{grant}</p></section>'):
            article = restricted + foreign.encode()
            _, licence = parse_article(article, Hit(DOI, TITLE, True))
            self.assertEqual(licence.status, "unknown")
            self.assertEqual((licence.private_cache, licence.display_excerpt, licence.export_excerpt), (False, False, False))
            transport = FixtureTransport([(200, 'application/json', discovery(), discovery()), (200, 'text/html', article, article)])
            chain = self.chain(transport)
            chain.discover()
            with self.assertRaisesRegex(SourceFailure, 'permission unknown'):
                chain.fetch(DOI)

    def test_grant_requires_single_bound_article_copyright_region(self):
        variants = (
            ARTICLE.replace(b'<strong>Copyright: </strong>', b'<strong>Unbound note: </strong>'),
            ARTICLE.replace(b'id="artText"', b'id="unrelated"'),
            ARTICLE.replace(b'<div class="articleinfo">', b'<blockquote><div class="articleinfo">').replace(b'</section>', b'</blockquote></section>'),
            ARTICLE.replace(b'<div class="articleinfo">', b'<div class="comments"><div class="articleinfo">').replace(b'</section>', b'</div></section>'),
            ARTICLE.replace((f'https://doi.org/{DOI}').encode(), b'https://doi.org/10.1371/journal.pone.9999999'),
            ARTICLE.replace(b'</div></div></section>', b'<p><strong>Copyright:</strong> All rights reserved.</p></div></div></section>'),
            ARTICLE.replace(b'</div></div></section>', b'<p>All rights reserved.</p></div></div></section>'),
            ARTICLE.replace(NOTICE.encode(), (NOTICE + '. All rights reserved.').encode()),
            ARTICLE.replace(NOTICE.encode(), ('<blockquote>' + NOTICE + '</blockquote>').encode()),
            ARTICLE.replace(b'</div></div></section>', b''),
        )
        for article in variants:
            with self.subTest(article=article[-160:]):
                _, licence = parse_article(article, Hit(DOI, TITLE, True))
                self.assertEqual(licence.status, 'unknown')
                self.assertEqual((licence.private_cache, licence.display_excerpt, licence.export_excerpt), (False, False, False))

    def test_supported_hit_survives_valid_unsupported_journal(self):
        supported = {"DOI": DOI, "title": [TITLE]}
        unsupported = {"DOI": "10.1371/journal.pcbi.0012345", "title": ["Unsupported but valid scholarly work"]}
        for items in ([supported, unsupported], [unsupported, supported]):
            body = discovery(items)
            chain = self.chain(FixtureTransport([(200, "application/json", body, body)]))
            self.assertEqual([h.doi for h in chain.discover()], [DOI])
            with self.assertRaises(SourceFailure):
                chain.fetch(unsupported['DOI'])
            self.assertEqual(len(chain.transport.calls), 1)
        body = discovery([unsupported])
        chain = self.chain(FixtureTransport([(200, "application/json", body, body)]))
        self.assertEqual(chain.discover(), ())
        self.assertEqual(chain.hits, {})

    def test_nested_current_article_restrictions_block_full_fetch(self):
        variants = (
            '<div class="rights"><p>Copyright: All rights reserved. No reproduction permitted.</p></div>',
            '<div class="rights"><section><p>All <span>rights</span> reserved.</p></section></div>',
            '<div class="rights"><p>Copyright: another owner.</p></div>',
            '<div class="rights"><p>Copyright another owner.</p></div>',
        )
        for nested in variants:
            article = ARTICLE.replace(b'</div></div></section>', nested.encode() + b'</div></div></section>')
            _, licence = parse_article(article, Hit(DOI, TITLE, True))
            self.assertEqual((licence.status, licence.private_cache, licence.display_excerpt, licence.export_excerpt), ('unknown', False, False, False))
            chain = self.chain(FixtureTransport([(200, 'application/json', discovery(), discovery()), (200, 'text/html', article, article)]))
            chain.discover()
            with self.assertRaisesRegex(SourceFailure, 'permission unknown'):
                chain.fetch(DOI)

    def test_duplicate_ownership_attributes_reject_complete_fetch(self):
        variants = (
            ARTICLE.replace(b'<div class="articleinfo">', b'<div class="comments" class="articleinfo">'),
            ARTICLE.replace(b'<div class="articleinfo">', b'<div class="articleinfo" CLASS="comments">'),
            ARTICLE.replace(b'id="artText"', b'id="reader-comments" id="artText"'),
            ARTICLE.replace(b'id="artText"', b'id="artText" id="reader-comments"'),
        )
        for article in variants:
            chain = self.chain(FixtureTransport([(200, 'application/json', discovery(), discovery()), (200, 'text/html', article, article)]))
            chain.discover()
            with self.assertRaisesRegex(SourceFailure, 'duplicate article attributes'):
                chain.fetch(DOI)

    def test_inline_split_restrictions_and_ownership_reject_complete_fetch(self):
        for text in ('All ri<span>ghts</span> reserved.', 'No repro<!-- formatting -->duction permitted.',
                     'Copy<span>right</span>: another owner.'):
            article = ARTICLE.replace(b'</div></div></section>', ('<div class="rights"><p>' + text + '</p></div></div></div></section>').encode())
            _, licence = parse_article(article, Hit(DOI, TITLE, True))
            self.assertEqual((licence.status, licence.private_cache, licence.display_excerpt, licence.export_excerpt), ('unknown', False, False, False))
            chain = self.chain(FixtureTransport([(200, 'application/json', discovery(), discovery()), (200, 'text/html', article, article)]))
            chain.discover()
            with self.assertRaisesRegex(SourceFailure, 'permission unknown'):
                chain.fetch(DOI)

    def test_normal_multiline_and_inline_grant_remains_allowed(self):
        article = ARTICLE.replace(b'Creative Commons Attribution License', b'Creative\n Commons\tAttribution License')
        article = article.replace(b'Copyright:', b'Copy<span>right</span>:')
        article = article.replace(b'permits unrestricted', b'per<span>mits</span> unrestricted')
        article = article.replace(b'reproduction', b'repro<!-- formatting -->duction')
        chain = self.chain(FixtureTransport([(200, 'application/json', discovery(), discovery()), (200, 'text/html', article, article)]))
        chain.discover()
        snapshot, _, _ = chain.fetch(DOI)
        self.assertEqual((snapshot.licence.status, snapshot.licence.private_cache, snapshot.licence.display_excerpt, snapshot.licence.export_excerpt), ('verified', True, True, True))

    def test_unsupported_hits_still_require_sound_metadata(self):
        bad_items = (
            {"DOI": "10.1371/journal.pcbi.0012345", "title": "not an array"},
            {"DOI": "10.1371/journal.pcbi.0012345", "title": [TITLE], "license": ["invalid"]},
            {"DOI": "https://elsewhere/paper", "title": [TITLE]},
            {"DOI": "10.1371/journal.pcbi.0012345/../../", "title": [TITLE]},
        )
        for item in bad_items:
            body = discovery([{"DOI": DOI, "title": [TITLE]}, item])
            chain = self.chain(FixtureTransport([(200, "application/json", body, body)]))
            with self.assertRaises(SourceFailure):
                chain.discover()
            self.assertEqual(chain.hits, {})

    def test_publisher_identity_and_mime_must_match(self):
        for article in (ARTICLE.replace(DOI.encode(), b"10.1371/journal.pone.9999999"), ARTICLE.replace(TITLE.encode(), b"Different title")):
            with self.assertRaises(SourceFailure):
                parse_article(article, Hit(DOI, TITLE, True))
        chain = self.chain(FixtureTransport([(200, "text/html", discovery(), discovery())]))
        with self.assertRaises(SourceFailure):
            chain.discover()

    def test_rows_duplicates_and_metadata_json_fail_closed(self):
        item = {"DOI": DOI, "title": [TITLE]}
        for data in (discovery([item] * 4), discovery([item] * 2), b'{"status":"ok","status":"bad"}', b'{"x":NaN}'):
            with self.subTest(data=data[:40]), self.assertRaises(SourceFailure):
                self.chain(FixtureTransport([(200, "application/json", data, data)])).discover()

    def test_invalid_last_hit_does_not_publish_partial_discovery(self):
        body = discovery([{"DOI": DOI, "title": [TITLE]}, {"DOI": "invalid", "title": [TITLE]}])
        chain = self.chain(FixtureTransport([(200, "application/json", body, body)]))
        with self.assertRaises(SourceFailure):
            chain.discover()
        with self.assertRaises(SourceFailure):
            chain.fetch(DOI)
        self.assertEqual(len(chain.transport.calls), 1)

    def test_provider_cannot_return_copyrighted_abstract_in_selected_metadata(self):
        body = discovery([{"DOI": DOI, "title": [TITLE], "abstract": "not part of permitted metadata projection"}])
        with self.assertRaises(SourceFailure):
            self.chain(FixtureTransport([(200, "application/json", body, body)])).discover()

    def test_fixture_transport_cannot_be_mislabelled_live(self):
        with self.assertRaises(ValueError):
            CrossrefPlosChain(make_plan(), FixtureTransport(), request_gate=lambda *_: None,
                             still_authorized=lambda: True, origin="live")

    def test_dispatch_context_is_held_through_actual_request(self):
        held = [False]
        @contextmanager
        def gate(*_):
            held[0] = True
            try:
                with held_lease() as lease:
                    yield lease
            finally:
                held[0] = False
        class Guarded(FixtureTransport):
            def get(self, target, *, still_authorized, owner_lease):
                if not held[0]:
                    raise AssertionError("send escaped owner gate")
                return super().get(target, still_authorized=still_authorized,owner_lease=owner_lease)
        chain = CrossrefPlosChain(make_plan(), Guarded(), request_gate=gate, still_authorized=lambda: True, origin="offline_probe")
        chain.discover()
        self.assertFalse(held[0])

    def test_total_quota_shared_by_caller_across_new_instances(self):
        consumed = set()
        def quota(plan, position, target):
            key = plan.task_id, position
            if key in consumed:
                return False
            consumed.add(key)
            return True
        first = self.chain(quota=quota)
        first.discover()
        @contextmanager
        def gate(*args):
            with held_lease(quota(*args)) as lease:
                yield lease
        second = CrossrefPlosChain(first.plan, FixtureTransport(), request_gate=gate, still_authorized=lambda: True, origin="offline_probe")
        with self.assertRaises(PermissionError):
            second.discover()
        self.assertEqual(second.transport.calls, [])

    def test_four_request_limit_and_no_fifth_network_action(self):
        hits = [{"DOI": "10.1371/journal.pone." + n, "title": [TITLE]} for n in ("0015032", "0015033", "0015034")]
        body = discovery(hits)
        records = [(200, "application/json", body, body)] + [(200, "text/html", ARTICLE, ARTICLE)] * 3
        chain = self.chain(FixtureTransport(records))
        chain.discover()
        for hit in hits:
            try:
                chain.fetch(hit["DOI"])
            except SourceFailure:  # the last two publisher identity mismatches
                pass
        with self.assertRaises(SourceFailure):
            chain._request(discovery_target(chain.plan.query))
        self.assertEqual(len(chain.transport.calls), 4)

    def test_revoke_between_response_and_use_discards_source(self):
        active = [True]
        class Late(FixtureTransport):
            def get(self, target, *, still_authorized, owner_lease):
                result = super().get(target, still_authorized=still_authorized,owner_lease=owner_lease)
                active[0] = False
                return result
        chain = self.chain(Late(), authorized=lambda: active[0])
        with self.assertRaises(PermissionError):
            chain.discover()

    def test_request_target_is_fixed_and_no_redirect_or_userinfo(self):
        for host, path in (("127.0.0.1", "/"), ("api.crossref.org", "/works?query=x&rows=100"),
                           ("journals.plos.org", "/plosone/article?id=http://127.0.0.1/"),
                           ("journals.plos.org", "https://journals.plos.org/plosone/article?id=" + DOI),
                           ("journals.plos.org", "/plosone/article?id=" + DOI + "&next=evil")):
            with self.subTest(host=host, path=path), self.assertRaises((SourceFailure, ValueError)):
                RequestTarget(host, path)

    def test_dns_all_answers_and_mapped_ipv6_are_checked(self):
        for ip, family in (("127.0.0.1", socket.AF_INET), ("169.254.169.254", socket.AF_INET),
                           ("10.0.0.2", socket.AF_INET), ("::1", socket.AF_INET6),
                           ("::ffff:8.8.8.8", socket.AF_INET6), ("ff02::1", socket.AF_INET6)):
            def resolver(*args, **kwargs):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)), (family, socket.SOCK_STREAM, 6, "", (ip, 443))]
            with self.subTest(ip=ip), self.assertRaises(SourceFailure):
                public_addresses("api.crossref.org", resolver)

    def test_compressed_bomb_and_incomplete_raw_body_rejected(self):
        with self.assertRaises(SourceFailure):
            decompress(gzip.compress(b"x" * (RAW_CAP + 1)), "gzip")
        with self.assertRaises(SourceFailure):
            decompress(b"x" * (RAW_CAP + 1), "identity")
        for data in (gzip.compress(b"small")[:-3], gzip.compress(b"a") + gzip.compress(b"b")):
            with self.assertRaises(SourceFailure):
                decompress(data, "gzip")
        self.assertEqual(decompress(gzip.compress(b"small"), "gzip"), b"small")

    def test_extraction_cap_not_silently_truncated(self):
        with self.assertRaises(SourceFailure):
            parse_article(ARTICLE + b"<p>" + b"x" * 200001, Hit(DOI, TITLE, True))

    def test_owned_process_success_failure_and_hard_timeout_are_reaped(self):
        before = {p.pid for p in multiprocessing.active_children()}
        result = self.pinned(fast_worker)
        self.assertEqual(result[2], b"local fixture")
        with self.assertRaises(SourceFailure):
            self.pinned(failed_worker)
        started = time.monotonic()
        with self.assertRaisesRegex(SourceFailure, "hard deadline"):
            self.pinned(slow_worker,seconds=0.3)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_eof_and_exit_deadline_classification_uses_observed_expiry_only(self):
        for eof in (True,False):
            for observed_at,exitcode,expired in (
                (100.301,None,True),
                (100.1,-signal.SIGALRM,True),
                (100.1,1,False),
                (100.1,None,False),
                (100.1,-signal.SIGTERM,False),
            ):
                with self.subTest(eof=eof,observed_at=observed_at,exitcode=exitcode):
                    receiver=Mock()
                    receiver.poll.return_value=eof
                    receiver.recv_bytes.side_effect=EOFError
                    sender=Mock()
                    process=Mock(pid=12345,exitcode=exitcode)
                    process.is_alive.return_value=False
                    context=Mock()
                    context.Pipe.return_value=(receiver,sender)
                    context.RawArray.return_value=bytearray(1)
                    context.Process.return_value=process
                    # Acquire the real lease before clock instrumentation;
                    # these deterministic supervisor branch probes add no
                    # waiting and do not replace the actual 0.3-second test.
                    with held_lease() as lease:
                        with patch("web.backend.research.source_policy.multiprocessing.get_context",return_value=context),patch("web.backend.research.source_policy.time.monotonic",side_effect=[100.0,100.1,observed_at]):
                            with self.assertRaises(SourceFailure) as result:
                                PinnedPublicTransport(wall_seconds=0.3,_worker=slow_worker).get(article_target(DOI),still_authorized=lambda:True,owner_lease=lease)
                    expected="source hard deadline" if expired else "source worker result unavailable" if eof else "source worker exited without result"
                    self.assertEqual(str(result.exception),expected)
                    process.join.assert_called_once_with(timeout=0.25)
                    process.close.assert_called_once_with()

    def test_owned_process_stops_when_authorization_is_revoked(self):
        start = time.monotonic()
        with self.assertRaises(PermissionError):
            self.pinned(slow_worker,authorized=lambda: time.monotonic() - start < 0.2)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_worker_failure_preserves_only_safe_http_observation(self):
        with self.assertRaises(SourceFailure) as result:
            self.pinned(blocked_worker)
        self.assertEqual(result.exception.http_status, 403)
        with self.assertRaises(SourceFailure) as result:
            self.pinned(failed_worker)
        self.assertNotIn("private provider body", str(result.exception))
        with self.assertRaises(SourceFailure):
            self.pinned(exited_worker)

    def local_http(self, response, *, peer="8.8.8.8"):
        """Real local socket bytes; patched public dial/TLS, never real DNS/TLS.

        This verifies HTTP framing, pinned numeric dialing, SNI argument and
        peer check, not a live public TLS certificate or VPS networking.
        """
        client, server = socket.socketpair()
        sent = []
        class Wrapped:
            def getpeername(self): return peer, 443
            def close(self): client.close()
        class TLS:
            def __enter__(self): return client
            def __exit__(self, *args): pass
        def serve():
            try:
                server.settimeout(1)
                sent.append(server.recv(4096))
                server.sendall(response)
            except (OSError, TimeoutError):
                pass
            finally:
                server.close()
        thread = threading.Thread(target=serve)
        thread.start()
        try:
            with patch("web.backend.research.source_policy.public_addresses", return_value=["8.8.8.8"]), \
                 patch("web.backend.research.source_policy.socket.create_connection", return_value=Wrapped()) as dial, \
                 patch("web.backend.research.source_policy.ssl.create_default_context") as context:
                context.return_value.wrap_socket.return_value = TLS()
                result = _network_get(article_target(DOI))
                dial.assert_called_once_with(("8.8.8.8", 443), timeout=5)
                self.assertEqual(context.return_value.wrap_socket.call_args.kwargs, {"server_hostname": "journals.plos.org"})
                return result
        finally:
            client.close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())

    def test_pinned_numeric_dial_and_original_tls_hostname(self):
        body = gzip.compress(ARTICLE)
        result = self.local_http(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Encoding: gzip\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        self.assertEqual(result[2], body)
        self.assertEqual(result[3], ARTICLE)

    def test_redirect_peer_change_truncation_and_ambiguous_framing_rejected(self):
        responses = (b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\n\r\n",
                     b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\nshort",
                     b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
                     b"HTTP/1.1 200 OK\r\nX-Long: " + b"x" * 17000 + b"\r\n\r\n")
        for response in responses:
            with self.subTest(response=response[:45]), self.assertRaises((SourceFailure, http.client.IncompleteRead)):
                self.local_http(response)
        with self.assertRaisesRegex(SourceFailure, "peer mismatch"):
            self.local_http(b"", peer="127.0.0.1")


class SourceAcceptanceTests(unittest.TestCase):
    def fetch(self, article):
        chain = SourceTests().chain(FixtureTransport([
            (200, "application/json", discovery(), discovery()), (200, "text/html", article, article)]))
        chain.discover()
        return chain.fetch(DOI)

    def test_both_complete_fixed_boilerplates_keep_all_permission_conditions(self):
        for spelling in (b"open-access", b"open access"):
            article = ARTICLE.replace(b"open-access", spelling)
            snapshot, raw, extracted = self.fetch(article)
            self.assertEqual(snapshot.parser_version, "plos-author-narrative-subset-v2")
            self.assertEqual(extracted, "Partial correlation is not a causality measure.")
            self.assertEqual(raw, article)
            self.assertEqual(snapshot.raw_digest, hashlib.sha256(raw).hexdigest())
            self.assertEqual((snapshot.licence.private_cache, snapshot.licence.display_excerpt, snapshot.licence.export_excerpt), (True, True, True))
            for denied in (article.replace(NOTICE.encode(), b"Unknown credit"),
                           article.replace(b"Attribution License", b"Attribution"),
                           article.replace(b"open access", b"open  accessx") if spelling == b"open access" else article.replace(b"open-access", b"open--access")):
                _, licence = parse_article(denied, Hit(DOI, TITLE, True))
                self.assertFalse(licence.private_cache)
            copyright_p = (b'<p><strong>Copyright: </strong>This is an ' + spelling +
                b' article distributed under the terms of the Creative Commons Attribution License, which ' + NOTICE.encode() + b'</p>')
            quoted = article.replace(copyright_p, b'<p><span class="quoted-other">' + copyright_p[3:-4] + b'</span></p>')
            self.assertNotEqual(quoted, article)
            _, licence = parse_article(quoted, Hit(DOI, TITLE, True))
            self.assertFalse(licence.private_cache)

    def test_narrative_is_scoped_and_keeps_inline_citations_not_foreign_statements(self):
        paragraph = ("<p>反馈 f<span>eed</span>back links <a class=\"reference\" href=\"#ref1\">[1]</a> to 作者叙述。</p>"
                     "<p>Second <em>author</em> paragraph.</p>").encode()
        outside = b'<nav>FOREIGN_NAV</nav><p>OUTSIDE_PARAGRAPH</p>'
        excluded = (b'<div class="comments">FOREIGN_COMMENT</div>'
                    b'<blockquote>FOREIGN_BLOCKQUOTE</blockquote><q>FOREIGN_Q</q>'
                    b'<span class="quoted-other">FOREIGN_EXPLICIT_QUOTE</span>'
                    b'<ol class="references"><li>FOREIGN_REFERENCE</li></ol>'
                    b'<div class="metadata">FOREIGN_METADATA</div>')
        article = ARTICLE.replace(b'<script>', outside+b'<script>', 1)
        article = article.replace(b'<p>Partial correlation is not a causality measure.</p>', paragraph+excluded)
        snapshot, raw, extracted = self.fetch(article)
        self.assertEqual(extracted, "反馈 feedback links [1] to 作者叙述。 Second author paragraph.")
        self.assertNotIn("Copyright", extracted)
        for word in (b'FOREIGN_NAV', b'OUTSIDE_PARAGRAPH', b'FOREIGN_COMMENT', b'FOREIGN_BLOCKQUOTE',
                     b'FOREIGN_Q', b'FOREIGN_EXPLICIT_QUOTE', b'FOREIGN_REFERENCE', b'FOREIGN_METADATA'):
            self.assertIn(word, raw)
            self.assertNotIn(word.decode(), extracted)
        quote = " ".join(extracted.split()[:20])
        self.assertEqual(extracted[:len(quote)], quote)
        self.assertEqual(snapshot.extracted_digest, hashlib.sha256(extracted.encode()).hexdigest())

    def test_current_container_intersection_accepts_either_nesting_order(self):
        article = ARTICLE.replace(b'<section class="article-body"><div id="artText" class="article-text">',
                                  b'<div id="artText" class="article-text"><section class="article-body">')
        article = article.replace(b'</div></div></section>', b'</div></section></div>')
        _, _, extracted = self.fetch(article)
        self.assertEqual(extracted, "Partial correlation is not a causality measure.")

    def test_empty_multiple_and_malformed_bodies_never_become_snapshots(self):
        sentence = b'<p>Partial correlation is not a causality measure.</p>'
        variants = (
            ARTICLE.replace(sentence, b''),
            ARTICLE.replace(sentence, b'').replace(b'<section class="article-body">', sentence+b'<section class="article-body">'),
            ARTICLE.replace(b'</html>', b'<section class="article-body"><div id="artText"><p>Other work.</p></div></section></html>'),
            ARTICLE.replace(sentence, b'<p>Malformed <em>inline narrative.</p>'),
            ARTICLE.replace(b'</div></div></section>', b'</div></section>'),
        )
        for article in variants:
            with self.subTest(article=article[-80:]), self.assertRaises(SourceFailure):
                self.fetch(article)

    def test_omitted_explicit_quote_leaves_a_boundary_not_a_fabricated_word(self):
        article = ARTICLE.replace(b'Partial correlation is not a causality measure.',
            b'Author<span class="quoted-other">NOT_AUTHOR</span>narrative f<span>eed</span>back.')
        _, _, extracted = self.fetch(article)
        self.assertEqual(extracted, "Author narrative feedback.")

    def test_owned_scientific_discussion_is_not_reader_comments(self):
        article = ARTICLE.replace(b'<p>Partial correlation is not a causality measure.</p>',
            b'<section id="discussion"><p>Author discussion cites <a class="reference" href="#r1">[1]</a> with limits.</p></section>')
        _, _, extracted = self.fetch(article)
        self.assertEqual(extracted, "Author discussion cites [1] with limits.")

    def test_omitted_image_boundary_reaches_actual_save_snapshot_default_excerpt(self):
        import sqlite3
        from tests.test_research_evidence import EvidenceTests
        from web.backend.research import source_workflow

        prefix = " ".join(f"word{number}" for number in range(1, 20))
        cases = (
            ('<p>Alpha<img src="formula.png" alt="is greater than">Beta.</p>', 'Alpha Beta.'),
            ('<p>Alpha<img src="formula.png" alt="UNTRUSTED_ALT"/>Beta.</p>', 'Alpha Beta.'),
            ('<p>前<span>后</span><img alt="UNTRUSTED_ALT">终。</p>', '前后 终。'),
            ('<p>Al<span>pha</span>Beta.</p>', 'AlphaBeta.'),
            ('<p>Alpha<q><img alt="UNTRUSTED_ALT">FOREIGN</q>Beta.</p>', 'Alpha Beta.'),
            (f'<p>{prefix} Alpha<img alt="UNTRUSTED_ALT">Beta after.</p>', f'{prefix} Alpha Beta after.'),
        )
        for body, expected in cases:
            with self.subTest(body=body):
                article = ARTICLE.replace(b'<p>Partial correlation is not a causality measure.</p>', body.encode())
                snapshot, raw, extracted = self.fetch(article)
                self.assertEqual(extracted, expected)
                self.assertNotIn('UNTRUSTED_ALT', extracted)
                self.assertNotIn('is greater than', extracted)
                self.assertNotIn('FOREIGN', extracted)
                fixture = EvidenceTests()
                fixture.setUp()
                try:
                    fixture.conn.row_factory = sqlite3.Row
                    fixture.repo.put(fixture.context, fixture.plan)
                    fixture.conn.execute('CREATE TABLE research_source_requests(id TEXT,outcome TEXT,dispatch_id TEXT,started_at TEXT,ended_at TEXT,http_status INTEGER)')
                    request_id = uid()
                    fixture.conn.execute('INSERT INTO research_source_requests VALUES(?,?,?,?,?,200)',
                        (request_id, 'SUCCEEDED', uid(), '2026-10-17T00:00:00Z', '2026-10-17T00:00:01Z'))
                    @contextmanager
                    def transaction(*, write=False):
                        self.assertTrue(write)
                        yield fixture.conn
                    # Isolated transaction/authorization fixture, not a C0
                    # acceptance claim; save_snapshot and repository are real.
                    session = source_workflow.SourceSession.__new__(source_workflow.SourceSession)
                    session.store = SimpleNamespace(transaction=transaction)
                    session.checked = lambda conn: None
                    session.task_id, session.step_id = fixture.context.task_id, fixture.context.step_id
                    session.binding, session.plan = fixture.binding, fixture.plan
                    session.last_request, session.mode = request_id, 'offline_probe'
                    snapshot = replace(snapshot, **fixture.binding)
                    with patch.object(source_workflow, 'context_for', return_value=fixture.context), patch.object(source_workflow, 'authorizer', return_value=fixture.authorize):
                        saved, _, _ = session.save_snapshot(snapshot, raw, extracted, discovery())
                    row = fixture.conn.execute("SELECT id FROM research_evidence_objects WHERE kind='excerpts'").fetchone()
                    excerpt = fixture.repo.get(fixture.context, 'excerpts', row[0])
                    expected_quote = f'{prefix} Alpha' if len(expected.split()) > 20 else expected
                    self.assertEqual(excerpt.quote, expected_quote)
                    self.assertEqual((excerpt.start, excerpt.end), (0, len(expected_quote)))
                    self.assertEqual(excerpt.extracted_digest, hashlib.sha256(extracted.encode()).hexdigest())
                    stored_raw, stored_text = fixture.conn.execute('SELECT raw,extracted FROM research_evidence_objects WHERE id=?', (saved,)).fetchone()
                    self.assertEqual((stored_raw, stored_text), (article, expected))
                finally:
                    fixture.tearDown()

    def test_images_do_not_relax_existing_text_or_structure_limits(self):
        from web.backend.research.source_policy import TEXT_CAP
        for body in (b'<p>' + b'x' * (TEXT_CAP + 1) + b'<img>y</p>',
                     b'<p>' + b'<span>' * 128 + b'x<img>' + b'</span>' * 128 + b'</p>'):
            article = ARTICLE.replace(b'<p>Partial correlation is not a causality measure.</p>', body)
            with self.assertRaises(SourceFailure):
                self.fetch(article)


if __name__ == "__main__":
    unittest.main()
