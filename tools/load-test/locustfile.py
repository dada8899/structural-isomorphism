"""HN-launch load test — simulate 100 concurrent users on the public surface.

Unblocks HN readiness § 1 "Load test passed — site stays up at 50 RPS for 10 min".

Usage (local dry-run against prod):
    pip install locust==2.32.4
    locust -f tools/load-test/locustfile.py \
        --host=https://beta.structural.bytedance.city \
        --users 100 --spawn-rate 10 --run-time 10m \
        --headless --csv=tools/load-test/results/$(date +%Y%m%d-%H%M)

Usage (with web UI for live dashboard):
    locust -f tools/load-test/locustfile.py \
        --host=https://beta.structural.bytedance.city
    # Then open http://127.0.0.1:8089

Pre-launch test plan:
    1. Ramp to 50 users (50 RPS soft target) for 10 min
       → expect p95 < 800 ms, 0 5xx
    2. Ramp to 100 users (≈100 RPS) for 5 min
       → expect p95 < 1500 ms, 5xx rate < 0.5%
    3. Spike to 200 users for 60 s
       → degradation acceptable but no crash
    4. Phase detector path test:
       LOAD_TEST_HOST=https://phase.bytedance.city locust ...

Read /docs/launch/load-test-plan-2026-05-24.md for full procedure.
"""

from __future__ import annotations

import os
import random
import time

from locust import HttpUser, between, events, task


# ---------------------------------------------------------------------------
# Test data — search queries representative of real HN-launch curiosity.
# ---------------------------------------------------------------------------

SEARCH_QUERIES = [
    # Cross-domain matches we know exist
    "bank runs",
    "neural avalanches",
    "wildfires",
    "DeFi liquidations",
    "GitHub stars",
    "earthquake aftershocks",
    "epidemic spread",
    "social cascades",
    "power grid failure",
    "citation networks",
    # Edge / negative cases
    "asdf123",  # nonsense — should return 0 or near-zero gracefully
    "",  # empty — should be rejected client-side; backend may 422
    "the quick brown fox",  # off-domain noise
    # Real Show HN reader vocabulary
    "phase transition",
    "self-organized criticality",
    "Ising model",
    "Sornette dragon king",
    "Plenz avalanche",
    "Sharpe ratio",
    "alpha estimate",
]

PHASE_DETECTOR_TICKERS = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "TSLA",
    "JPM",
    "BAC",
    "WFC",
    "XOM",
    "CVX",
]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class AnonymousVisitor(HttpUser):
    """The dominant traffic class — HN clicker who lands, browses, leaves.

    Mix: 70% of total traffic.
    Behavior: page reads + read-only API calls. No POSTs to mutating endpoints
    so we don't pollute prod DB.
    """

    weight = 7
    wait_time = between(2, 8)  # human read time

    @task(40)
    def landing(self) -> None:
        self.client.get("/", name="GET /")

    @task(25)
    def search(self) -> None:
        q = random.choice(SEARCH_QUERIES)
        self.client.get(
            f"/api/search?q={q}",
            name="GET /api/search?q=...",
            timeout=10,
        )

    @task(15)
    def discoveries_list(self) -> None:
        self.client.get("/api/discoveries", name="GET /api/discoveries", timeout=10)

    @task(10)
    def methodology_page(self) -> None:
        self.client.get("/methodology", name="GET /methodology")

    @task(5)
    def examples(self) -> None:
        self.client.get("/api/examples", name="GET /api/examples", timeout=10)

    @task(5)
    def static_assets(self) -> None:
        # OG card / favicon load on each landing — verify CDN warm
        self.client.get("/favicon.ico", name="GET /favicon.ico")


class CuriousReader(HttpUser):
    """The 20% who actually click into detail pages. Higher cost queries."""

    weight = 2
    wait_time = between(4, 12)

    @task(30)
    def deep_search(self) -> None:
        # Two-query session — first broad, then narrow
        q1 = random.choice(SEARCH_QUERIES[:6])
        self.client.get(f"/api/search?q={q1}", name="GET /api/search [deep1]")
        time.sleep(random.uniform(1, 3))
        q2 = random.choice(SEARCH_QUERIES[6:12])
        self.client.get(f"/api/search?q={q2}", name="GET /api/search [deep2]")

    @task(20)
    def phenomenon_detail(self) -> None:
        # The detail page is the most expensive read
        pid = random.choice(["bank-runs", "neural-avalanches", "wildfires", "github-stars"])
        self.client.get(f"/api/phenomenon/{pid}", name="GET /api/phenomenon/{id}", timeout=15)

    @task(15)
    def backtest_results(self) -> None:
        self.client.get("/api/backtest/summary", name="GET /api/backtest/summary", timeout=15)

    @task(10)
    def report_pdf(self) -> None:
        # If a report PDF route exists; otherwise it 404s and we record that
        self.client.get(
            "/api/report?system=neural-avalanches&format=summary",
            name="GET /api/report",
            timeout=15,
        )

    @task(5)
    def waitlist_form_view(self) -> None:
        # Just the form page — NOT a POST. Read-only.
        self.client.get("/waitlist", name="GET /waitlist")


class PhaseDetectorUser(HttpUser):
    """Subset of traffic that lands on phase.bytedance.city instead."""

    weight = 1
    wait_time = between(3, 10)
    host = os.environ.get("PHASE_DETECTOR_HOST", "https://phase.bytedance.city")

    @task(40)
    def phase_landing(self) -> None:
        self.client.get("/", name="GET phase /")

    @task(30)
    def phase_grid(self) -> None:
        self.client.get("/api/phase/list", name="GET phase /api/phase/list", timeout=15)

    @task(20)
    def ticker_detail(self) -> None:
        t = random.choice(PHASE_DETECTOR_TICKERS)
        self.client.get(f"/api/phase/{t}", name="GET phase /api/phase/{ticker}", timeout=15)

    @task(10)
    def disclaimer_toast(self) -> None:
        # First-visit caveat — make sure the static fetch is cheap
        self.client.get("/disclaimer", name="GET phase /disclaimer")


# ---------------------------------------------------------------------------
# Event hooks — fail the run if SLOs blown
# ---------------------------------------------------------------------------


SLO_5XX_MAX = float(os.environ.get("SLO_5XX_MAX", "0.5"))  # %
SLO_P95_MS = int(os.environ.get("SLO_P95_MS", "1500"))


@events.test_stop.add_listener
def _enforce_slos(environment, **kwargs) -> None:
    """Print a verdict line + exit non-zero if SLOs blown.

    Locust returns 0 by default even on bad runs. CI must read this output.
    """
    stats = environment.stats.total
    total = stats.num_requests or 1
    pct_5xx = 100.0 * stats.num_failures / total
    p95 = stats.get_response_time_percentile(0.95) or 0
    verdict = "PASS"
    if pct_5xx > SLO_5XX_MAX:
        verdict = "FAIL_5XX"
    elif p95 > SLO_P95_MS:
        verdict = "FAIL_LATENCY"
    line = (
        f"\n[LOAD-TEST VERDICT] {verdict} | total={total} | "
        f"5xx%={pct_5xx:.2f} (SLO {SLO_5XX_MAX}) | "
        f"p95={p95:.0f}ms (SLO {SLO_P95_MS})\n"
    )
    print(line)
    environment.process_exit_code = 0 if verdict == "PASS" else 1
