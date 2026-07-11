#!/usr/bin/env python3
"""Fail-closed production synthetic monitor for all public product surfaces.

The monitor deliberately exercises business invariants, not just HTTP
liveness.  It uses only the Python standard library and never logs response
bodies (which could contain deployment or authentication details).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


STRUCTURAL = "https://structural.bytedance.city"
BETA = "https://beta.structural.bytedance.city"
PHASE = "https://phase.bytedance.city"
DEFAULT_TIMEOUT = 15.0

ZH_QUERIES = (
    "银行挤兑如何形成正反馈级联？",
    "社交网络中的信息级联与传染病传播有什么结构相似性？",
    "供应链中断为什么会跨层级扩散？",
    "生态系统崩溃前有哪些临界减速机制？",
    "组织创新扩散与相变有什么共同结构？",
)
EN_QUERIES = (
    "How do bank runs form a positive feedback cascade?",
    "What structural mechanism links information cascades and epidemics?",
    "Why do supply chain disruptions propagate across layers?",
    "What critical slowing down mechanisms precede ecosystem collapse?",
    "How is organizational innovation diffusion structurally similar to a phase transition?",
)
OOS_QUERIES = (
    "1 + 1 等于几？", "What is 1 + 1?",
    "你好，今天过得怎么样？", "Hello, how are you today?",
    "法国的首都是哪里？", "What is the capital of France?",
    "北京明天天气怎么样？", "What will the weather be in Beijing tomorrow?",
    "把苹果翻译成英文。", "Translate the word apple into Chinese.",
    "特斯拉明天会涨还是会跌？", "Will Tesla stock rise or fall tomorrow?",
    "推荐一个下周一定上涨的加密货币。", "Pick a cryptocurrency guaranteed to rise next week.",
    "西红柿炒鸡蛋怎么做？", "How do I cook scrambled eggs with tomatoes?",
    "   ", "\t", "？？！！", "...?!",
)


class SmokeFailure(RuntimeError):
    """A safe, user-readable production contract failure."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


Transport = Callable[[str, str, bytes | None, float], Response]


def urllib_transport(method: str, url: str, body: bytes | None, timeout: float) -> Response:
    headers = {"User-Agent": "structural-production-smoke/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Response(response.status, response.read())
    except urllib.error.HTTPError as exc:
        # Expected negative-path statuses (503) still need contract checks.
        return Response(exc.code, exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SmokeFailure(f"{method} {url}: network failure ({type(exc).__name__})") from exc


class Monitor:
    def __init__(
        self,
        transport: Transport = urllib_transport,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        search_interval: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.transport = transport
        self.timeout = timeout
        self.search_interval = (
            2.1 if search_interval is None and transport is urllib_transport
            else float(search_interval or 0.0)
        )
        self.sleeper = sleeper
        self.search_requests = 0
        self.checked = 0

    def request(self, label: str, method: str, url: str, *, payload: dict | None = None,
                expected_status: int = 200) -> Response:
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        response = self.transport(method, url, raw, self.timeout)
        self.checked += 1
        if response.status != expected_status:
            raise SmokeFailure(f"{label}: expected HTTP {expected_status}, got {response.status}")
        return response

    def json(self, label: str, method: str, url: str, *, payload: dict | None = None,
             expected_status: int = 200) -> Any:
        response = self.request(label, method, url, payload=payload, expected_status=expected_status)
        try:
            return json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmokeFailure(f"{label}: response is not valid JSON") from exc

    @staticmethod
    def require(condition: bool, label: str, detail: str) -> None:
        if not condition:
            raise SmokeFailure(f"{label}: {detail}")

    def check_page(self, label: str, url: str) -> None:
        response = self.request(label, "GET", url)
        self.require(len(response.body.strip()) >= 100, label, "page body is unexpectedly small")

    def check_structural_docs(self) -> None:
        self.check_page("structural homepage", f"{STRUCTURAL}/")
        # The docs SPA fetches canonical Markdown resources directly.
        self.check_page("structural docs route", f"{STRUCTURAL}/docs/overview.md")

    def check_beta_system(self) -> None:
        version = self.json("beta version", "GET", f"{BETA}/api/version")
        self.require(isinstance(version, dict), "beta version", "expected an object")
        for field in ("semver", "git_sha", "python_version", "env", "model", "deployed_at"):
            self.require(isinstance(version.get(field), str) and bool(version[field].strip()),
                         "beta version", f"missing non-empty {field}")

        health = self.json("beta deep health", "GET", f"{BETA}/api/health?deep=1")
        self.require(isinstance(health, dict), "beta deep health", "expected an object")
        self.require(health.get("status") == "ok", "beta deep health", "status must be ok")
        self.require(health.get("kb_size") == 4443, "beta deep health", "kb_size must equal 4443")
        self.require(health.get("artifact_id") == "structural-v2-kb4443-20260711",
                     "beta deep health", "artifact_id must match canonical production artifact")
        self.require(health.get("embedding_shape") == [4443, 768], "beta deep health",
                     "embedding_shape must equal [4443, 768]")
        checks = health.get("checks")
        self.require(isinstance(checks, dict), "beta deep health", "checks must be an object")
        for field in ("search_service", "knowledge_base", "artifact_manifest"):
            self.require(checks.get(field) == "ok", "beta deep health", f"checks.{field} must be ok")
        self.require(checks.get("history_db") in {"ok", "missing"}, "beta deep health",
                     "checks.history_db must be ok or missing")
        self.require(checks.get("llm_env") in {"ok", "missing"}, "beta deep health",
                     "checks.llm_env must be ok or missing")

    def search(self, query: str, lang: str, label: str) -> dict:
        if self.search_requests:
            self.sleeper(self.search_interval)
        self.search_requests += 1
        result = self.json(label, "POST", f"{BETA}/api/search",
                           payload={"query": query, "top_k": 5, "rewrite": False, "lang": lang})
        self.require(isinstance(result, dict), label, "expected an object")
        return result

    def check_search(self) -> None:
        cross_domain = 0
        for index, query in enumerate(ZH_QUERIES + EN_QUERIES, 1):
            lang = "zh" if index <= len(ZH_QUERIES) else "en"
            label = f"in-scope search {index}/10"
            result = self.search(query, lang, label)
            rows = result.get("results")
            self.require(result.get("out_of_scope") is not True, label, "query was refused")
            self.require(isinstance(rows, list) and len(rows) > 0, label, "results must be non-empty")
            self.require(result.get("count") == len(rows), label, "count does not match results")
            for row in rows:
                self.require(isinstance(row, dict), label, "every result must be an object")
                self.require(all(isinstance(row.get(k), str) and row[k].strip()
                                 for k in ("id", "name", "domain", "type_id")),
                             label, "result is missing identity fields")
            cross_domain += sum(row.get("cross_domain") is True for row in rows)
        self.require(cross_domain > 0, "in-scope searches", "no cross-domain candidate across 10 queries")

        for index, query in enumerate(OOS_QUERIES, 1):
            result = self.search(query, "zh" if index % 2 else "en", f"OOS search {index}/20")
            self.require(result.get("out_of_scope") is True, f"OOS search {index}/20",
                         "must be explicitly refused")
            self.require(result.get("count") == 0 and result.get("results") == [],
                         f"OOS search {index}/20", "refusal must return zero candidates")
            self.require(isinstance(result.get("scope_reason"), str) and bool(result["scope_reason"]),
                         f"OOS search {index}/20", "scope_reason must be non-empty")

    def check_disabled_surfaces(self) -> None:
        checkout = self.json("billing disabled", "POST", f"{BETA}/api/billing/checkout-session",
                             payload={"tier": "pro", "interval": "month", "email": "smoke@example.com"},
                             expected_status=503)
        self.require(isinstance(checkout, dict) and checkout.get("error") == "billing_not_available",
                     "billing disabled", "must fail closed with billing_not_available")
        auth = self.json("auth disabled", "POST", f"{BETA}/api/auth/request-link",
                         payload={"email": "smoke@example.com"}, expected_status=503)
        self.require(
            isinstance(auth, dict)
            and auth.get("error") == "account_features_not_available",
            "auth disabled",
            "must fail closed with account_features_not_available",
        )

    def check_phase(self) -> None:
        health = self.json("phase health", "GET", f"{PHASE}/api/health")
        self.require(isinstance(health, dict) and health.get("status") == "ok",
                     "phase health", "status must be ok")
        meta = self.json("phase EWS metadata", "GET", f"{PHASE}/api/ews/meta")
        self.require(isinstance(meta, dict), "phase EWS metadata", "expected an object")
        self.require(meta.get("n_tickers") == 597, "phase EWS metadata", "n_tickers must equal 597")
        self.require(meta.get("price_provenance") == "demo", "phase EWS metadata",
                     "price_provenance must equal demo")

    def check_route_matrix(self) -> None:
        beta_routes = ("/", "/search", "/classes", "/analyze", "/pricing.html")
        phase_routes = ("/", "/zh", "/companies", "/methodology", "/universality", "/about", "/pricing")
        for route in beta_routes:
            self.check_page(f"beta route {route}", BETA + route)
        for route in phase_routes:
            self.check_page(f"phase route {route}", PHASE + route)

    def run(self) -> int:
        started = time.monotonic()
        self.check_structural_docs()
        self.check_beta_system()
        self.check_search()
        self.check_disabled_surfaces()
        self.check_phase()
        self.check_route_matrix()
        elapsed = time.monotonic() - started
        print(f"PASS production smoke: {self.checked} requests in {elapsed:.1f}s")
        return self.checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="per-request timeout in seconds (default: 15)")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
    try:
        Monitor(timeout=args.timeout).run()
    except SmokeFailure as exc:
        print(f"FAIL production smoke: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
