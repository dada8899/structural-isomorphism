"""One scholarly discovery plus at most three matched PLOS document fetches.

No synthesis, price retrieval or semantic evidence approval. Requests must be
authorized and quota-consumed durably by the future C0 integration; this module
does not manufacture a fixture funding account or its own persistent runner.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
from uuid import uuid4

from ..evidence_schemas import DataSnapshot, Licence, AnalysisPlan, canonical, sha256
from ..source_policy import SourceFailure, TEXT_CAP, discovery_target, article_target


def strict_json(data):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise SourceFailure("duplicate metadata key")
            out[k] = v
        return out
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(SourceFailure("nonfinite metadata")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SourceFailure("invalid scholarly metadata") from exc


@dataclass(frozen=True)
class Hit:
    doi: str
    title: str
    cc_by_4: bool


class _ArticleParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    BLOCK = {"address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "tbody", "td", "th", "thead", "tr", "ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.parts, self.size = 0, [], 0
        self.dois, self.titles = [], []
        self.stack, self.article_info = [], []
        self.nodes = 0
        self.permission_size = 0

    def permission_data(self, value):
        if self.skip:
            return
        self.permission_size += len(value)
        if self.permission_size > TEXT_CAP:
            raise SourceFailure("permission text limit")
        for frame in self.stack:
            if "paragraph" in frame:
                frame["paragraph"].append(value)
        for index, frame in enumerate(self.stack):
            if "info" in frame and not any(f["excluded"] for f in self.stack[index + 1:]):
                frame["info"]["scope_parts"].append(value)

    @staticmethod
    def excluded(tag, attrs):
        tokens = attrs.get("id", "") + " " + attrs.get("class", "")
        return (tag in {"blockquote", "q", "aside", "footer", "script", "style", "template", "noscript"}
                or re.search(r"(?:^|[\s_-])(?:comments?|discussion|references?|ref-list|user-content)(?:$|[\s_-])", tokens, re.I) is not None)

    def handle_starttag(self, tag, attributes):
        self.nodes += 1
        if self.nodes > 50000 or len(self.stack) >= 128:
            raise SourceFailure("article structure limit")
        # HTMLParser preserves duplicate attributes; dict() must not erase an
        # earlier comments/id exclusion or create ambiguous article ownership.
        names = [name for name, _ in attributes]
        if len(names) != len(set(names)):
            raise SourceFailure("ambiguous duplicate article attributes")
        if tag in self.BLOCK:
            self.permission_data(" ")
        attrs = dict(attributes)
        excluded = self.excluded(tag, attrs)
        if excluded:
            for frame in self.stack:
                if "paragraph" in frame:
                    frame["tainted"] = True
        frame = {"tag": tag, "attrs": attrs, "excluded": excluded}
        # PLOS's current-article metadata is a specific articleinfo block inside
        # artText/article-body. A matching notice elsewhere is never a grant.
        if (tag == "div" and "articleinfo" in attrs.get("class", "").split()
                and any(f["attrs"].get("id") == "artText" for f in self.stack)
                and any(f["tag"] == "section" and "article-body" in f["attrs"].get("class", "").split() for f in self.stack)
                and not excluded and not any(f["excluded"] for f in self.stack)):
            info = {"copyright": [], "citation": [], "closed": False, "malformed": False, "rights_conflict": False, "scope_parts": []}
            self.article_info.append(info)
            frame["info"] = info
        if tag == "p" and self.stack and "info" in self.stack[-1]:
            frame.update(paragraph=[], tainted=excluded, scope=self.stack[-1]["info"])
        if tag not in self.VOID:
            self.stack.append(frame)
        if tag in {"script", "style", "template", "noscript"}:
            self.skip += 1
        if tag == "meta":
            name, value = attrs.get("name", "").lower(), attrs.get("content", "")
            if name == "citation_doi":
                self.dois.append(value)
            if name == "citation_title":
                self.titles.append(value)

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.permission_data(" ")
        if tag in {"script", "style", "template", "noscript"} and self.skip:
            self.skip -= 1
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                for frame in self.stack[index:]:
                    if "paragraph" in frame:
                        value = re.sub(r"\s+", " ", "".join(frame["paragraph"])).strip()
                        scope = frame["scope"]
                        if frame["tag"] != tag or frame is not self.stack[index]:
                            scope["malformed"] = True
                        if value.casefold().startswith("copyright:"):
                            scope["copyright"].append((value, frame["tainted"]))
                        if value.casefold().startswith("citation:"):
                            scope["citation"].append((value, frame["tainted"]))
                        if not frame["tainted"] and re.search(r"all rights reserved|permission required|no derivatives", value, re.I):
                            scope["rights_conflict"] = True
                    if "info" in frame:
                        frame["info"]["closed"] = frame is self.stack[index]
                del self.stack[index:]
                break

    def handle_data(self, value):
        # Preserve inline continuity for permission/ownership checks. Comments
        # contribute no bytes; only explicit block boundaries insert a space.
        # Normalize whitespace once, after joining the original text nodes.
        self.permission_data(value)
        if not self.skip:
            part = re.sub(r"\s+", " ", value).strip()
            if part:
                self.size += len(part) + 1
                if self.size > TEXT_CAP:
                    raise SourceFailure("extracted text limit")
                self.parts.append(part)

    def current_article_grant(self, doi):
        if len(self.article_info) != 1:
            return False
        info = self.article_info[0]
        scope_text = re.sub(r"\s+", " ", "".join(info["scope_parts"])).casefold()
        # Extra copyright labels anywhere in this ownership region make the
        # grant ambiguous. Restrictive text may be wrapped in arbitrary nested
        # inline/block markup; joining text nodes preserves that boundary check.
        if (len(re.findall(r"\bcopyright\b", scope_text)) != 1
                or re.search(r"all rights reserved|permission required|no derivatives|no reproduction permitted|not permitted|reproduction prohibited|may not reproduce|non[- ]commercial", scope_text)):
            return False
        if (not info["closed"] or info["malformed"] or info["rights_conflict"]
                or len(info["copyright"]) != 1 or len(info["citation"]) != 1):
            return False
        (copyright_text, copyright_quoted), (citation, citation_quoted) = info["copyright"][0], info["citation"][0]
        if copyright_quoted or citation_quoted:
            return False
        if re.findall(r"10\.1371/journal\.[a-z]+\.[0-9]{7}", citation) != [doi]:
            return False
        value = copyright_text.casefold()
        # Deny restrictive/conflicting text in the article's actual copyright
        # paragraph, even if an open grant appears in the same paragraph.
        if re.search(r"all rights reserved|non[- ]commercial|no derivatives|not permitted|permission required|may not|except", value):
            return False
        return ("open-access article distributed under the terms of the creative commons attribution license" in value
                and "permits unrestricted use, distribution, and reproduction in any medium, provided the original author and source are credited" in value)


def parse_article(decoded, hit):
    try:
        article = decoded.decode("utf-8", errors="strict")
        parser = _ArticleParser()
        parser.feed(article)
        parser.close()
    except (UnicodeError, RecursionError) as exc:
        raise SourceFailure("invalid article encoding") from exc
    # Metadata identity is necessary, never proof of the article's claims.
    normalize = lambda s: re.sub(r"\s+", " ", s).strip().casefold()
    if parser.dois != [hit.doi] or parser.titles != [hit.title]:
        raise SourceFailure("publisher identity mismatch")
    extracted = " ".join(parser.parts)
    if not extracted or len(extracted) > TEXT_CAP:
        raise SourceFailure("article text unavailable")
    permitted = bool(hit.cc_by_4 and parser.current_article_grant(hit.doi))
    licence = Licence(status="verified", private_cache=True, display_excerpt=True, export_excerpt=True,
        basis="Work metadata identifies CC BY 4.0. Current articleinfo copyright paragraph, bound by its citation DOI inside artText/article-body, independently grants unrestricted reproduction with author/source credit. That notice is not version-specific.") if permitted else Licence()
    return extracted, licence


class CrossrefPlosChain:
    def __init__(self, plan, transport, *, request_gate, still_authorized, origin="live"):
        if type(plan) is not AnalysisPlan or not callable(request_gate) or not callable(still_authorized):
            raise ValueError("fixed plan and controlled dispatch context required")
        if origin not in {"live", "offline_probe"}:
            raise ValueError("historical import must not issue network requests")
        if getattr(transport, "execution_mode", None) != origin:
            raise ValueError("transport provenance mismatch")
        self.plan, self.transport = plan, transport
        self.request_gate, self.still_authorized = request_gate, still_authorized
        self.origin, self.hits, self.used, self.fetched = origin, None, 0, set()
        self.discovery_body = None

    def _request(self, target):
        if self.still_authorized() is not True:
            raise PermissionError("source access ended")
        if self.used >= self.plan.max_requests:
            raise SourceFailure("task request limit")
        # This local counter is defense in depth, not a durable quota. The
        # caller-owned context must bind plan/task/attempt, charge total quota
        # and consume once under C0's cross-process owner gate. Hold that gate
        # through this bounded request (but NOT a DB transaction) so cancellation
        # cannot commit between permit consumption and the actual child send.
        # C0 may later narrow this interval with a reviewed child-send handshake.
        self.used += 1
        from ..authorization import OwnerGateLease
        with self.request_gate(self.plan, self.used, target) as owner_lease:
            if type(owner_lease) is not OwnerGateLease or self.still_authorized() is not True:
                raise PermissionError("source request permit denied")
            owner_lease.identity  # validate the public capability, not an FD
            result = self.transport.get(target, still_authorized=self.still_authorized,owner_lease=owner_lease)
        if self.still_authorized() is not True:
            raise PermissionError("late source discarded")
        status, content_type, raw, decoded = result
        from ..source_policy import RAW_CAP
        if status != 200 or type(raw) is not bytes or type(decoded) is not bytes or max(len(raw), len(decoded)) > RAW_CAP:
            raise SourceFailure("invalid source response")
        return content_type, raw, decoded

    def discover(self):
        if self.hits is not None:
            raise SourceFailure("discovery already attempted")
        # Mark before any attempt: failed/unknown reads cannot be blindly retried.
        self.hits = {}
        content_type, _, decoded = self._request(discovery_target(self.plan.query))
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise SourceFailure("metadata content type mismatch")
        data = strict_json(decoded)
        if type(data) is not dict or data.get("status") != "ok" or data.get("message-type") != "work-list":
            raise SourceFailure("invalid discovery response")
        message = data.get("message")
        if type(message) is not dict or type(message.get("items")) is not list or len(message["items"]) > 3:
            raise SourceFailure("discovery row limit")
        hits, seen = {}, set()
        for item in message["items"]:
            if type(item) is not dict:
                raise SourceFailure("invalid discovery item")
            if not set(item) <= {"DOI", "title", "license"}:
                raise SourceFailure("unexpected unlicensed metadata fields")
            doi, titles = item.get("DOI"), item.get("title")
            if (type(doi) is not str or re.fullmatch(r"10\.1371/journal\.[a-z][a-z0-9]{1,15}\.[0-9]{7}", doi) is None
                    or type(titles) is not list or len(titles) != 1 or type(titles[0]) is not str
                    or not 1 <= len(titles[0]) <= 300 or doi in seen):
                raise SourceFailure("invalid discovered identity")
            licences = item.get("license", [])
            if type(licences) is not list or len(licences) > 20 or any(type(v) is not dict for v in licences):
                raise SourceFailure("invalid licence metadata")
            seen.add(doi)
            if re.fullmatch(r"10\.1371/journal\.pone\.[0-9]{7}", doi) is None:
                continue  # valid metadata for an unsupported PLOS journal
            cc = any(type(v) is dict and v.get("content-version") in {"vor", "unspecified"}
                     and v.get("URL") in {"http://creativecommons.org/licenses/by/4.0/", "https://creativecommons.org/licenses/by/4.0/"} for v in licences)
            hits[doi] = Hit(doi, titles[0], cc)
        self.hits = hits
        self.discovery_body = decoded
        return tuple(self.hits.values())

    def fetch(self, doi):
        if self.hits is None or doi not in self.hits or doi in self.fetched:
            raise SourceFailure("DOI not discovered in this task or already attempted")
        self.fetched.add(doi)
        hit = self.hits[doi]
        content_type, raw, decoded = self._request(article_target(doi))
        if content_type.split(";", 1)[0].strip().lower() != "text/html":
            raise SourceFailure("article content type mismatch")
        extracted, licence = parse_article(decoded, hit)
        # Unknown permission does not allow caching even a short excerpt.
        if not licence.private_cache:
            raise SourceFailure("article permission unknown")
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        fields = {k: getattr(self.plan, k) for k in ("research_id", "input_revision", "task_id", "attempt", "input_digest")}
        snapshot = DataSnapshot(**fields, id=str(uuid4()), source_id=str(uuid4()), source_revision=1,
            title=hit.title, doi=doi, canonical_url="https://journals.plos.org/plosone/article?id=" + doi,
            query_digest=sha256(self.plan.query.encode()), acquired_at=timestamp,
            discovery_digest=sha256(self.discovery_body),
            information_cutoff=self.plan.created_at, raw_digest=sha256(raw), extracted_digest=sha256(extracted.encode()),
            parser_version="plos-html-text-v1", licence=licence, origin=self.origin)
        return snapshot, raw, extracted
