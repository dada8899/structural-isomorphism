"""Newsletter data source adapters (W9-C).

One function per data source so each can be unit-tested + mocked independently.
This separates *fetching/parsing* from *templating* (which lives in
generate-newsletter.py).

Data sources:
    1. fetch_phase_flips    — recent critical-state flips from D1 phase detector
    2. fetch_arxiv_papers   — cross-domain SOC / universality preprints
    3. fetch_github_activity — stargazers / forks / contributors via gh CLI
    4. methodology_spotlight — rotating topic from a fixed pool

Design choices:
    - **No hard dependency on httpx / requests**: stdlib urllib.request only.
      Keeps the CI lean (no extra pip install) and the script vendor-able.
    - **Network failures degrade to empty**: each source catches its own
      exceptions and returns an empty list, so the newsletter still renders
      even if arxiv / GitHub is down. The generator emits placeholder text in
      the corresponding section.
    - **Idempotency**: same week_start (ISO date) + same upstream data ⇒ same
      output. We always sort by stable keys (ticker / arxiv id / login) before
      returning. Time-of-day-dependent filters use the *week boundary*, never
      `now()`, so re-running on Monday yields the same week's content as
      Sunday.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger("newsletter.data_sources")

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_TIMEOUT_S = 15
USER_AGENT = "structural-isomorphism-newsletter/0.1 (+https://github.com/dada8899/structural-isomorphism)"


# ---------------------------------------------------------------------------
# 1. Phase Detector — recent flips
# ---------------------------------------------------------------------------

# Mirror of send_weekly.py vocabulary — keeping them in sync is a maintenance
# tax we accept for now; could move to a shared constants module later.
TIPPING_STATES = frozenset({"near_critical", "approaching_critical", "at_critical"})
STABLE_STATES = frozenset({"subcritical", "far_from_critical"})


def fetch_phase_flips(
    *,
    structtuples_path: Optional[Path] = None,
    last_week_state_path: Optional[Path] = None,
    api_url: Optional[str] = None,
    min_confidence: float = 0.0,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Return up to `max_results` ticker dicts representing structural flips.

    Resolution order:
        (a) If `structtuples_path` is given → load that file + diff vs
            `last_week_state_path` (defaults to scripts/newsletter/state/...).
        (b) Else if `api_url` is given → fetch live from phase API.
        (c) Else → auto-discover latest structtuples in v4/product/d1_phase_detector/.

    Each returned row:
        {
          "ticker": "NVDA",
          "name": "NVIDIA Corporation",
          "from_state": "far_from_critical",
          "to_state": "near_critical",
          "dynamics_family": "preferential_attachment",
          "confidence": 0.82,
          "tldr": "...",
        }
    """
    # Path (a): explicit file diff against last-week state
    if structtuples_path is not None:
        return _diff_structtuples(
            structtuples_path,
            last_week_state_path
            or (REPO_ROOT / "scripts" / "newsletter" / "state" / "last_week_state.json"),
            min_confidence=min_confidence,
            max_results=max_results,
        )

    # Path (b): live API
    if api_url:
        return _fetch_phase_api(api_url, max_results=max_results)

    # Path (c): auto-discover
    data_dir = REPO_ROOT / "v4" / "product" / "d1_phase_detector"
    candidates = sorted(data_dir.glob("structtuples_*.jsonl"))
    if not candidates:
        logger.warning("no structtuples found under %s", data_dir)
        return []
    return _diff_structtuples(
        candidates[-1],
        REPO_ROOT / "scripts" / "newsletter" / "state" / "last_week_state.json",
        min_confidence=min_confidence,
        max_results=max_results,
    )


def _diff_structtuples(
    current_path: Path,
    last_state_path: Path,
    *,
    min_confidence: float,
    max_results: int,
) -> list[dict[str, Any]]:
    """Diff current vs last-week structtuples; return flip rows."""
    current = _load_structtuples(current_path)
    last_week = _load_last_week(last_state_path)

    flips: list[dict[str, Any]] = []
    for ticker, cur in current.items():
        cur_state = (cur.get("critical_point_state") or "").lower()
        prev = last_week.get(ticker) or {}
        prev_state = (prev.get("critical_point_state") or "").lower()

        # entered tipping
        entered = cur_state in TIPPING_STATES and prev_state not in TIPPING_STATES
        # returned to stable
        returned = prev_state in TIPPING_STATES and cur_state in STABLE_STATES

        if not (entered or returned):
            continue
        if (cur.get("confidence") or 0) < min_confidence:
            continue

        flips.append(
            {
                "ticker": ticker,
                "name": cur.get("name") or ticker,
                "from_state": prev_state or "unknown",
                "to_state": cur_state,
                "dynamics_family": cur.get("dynamics_family") or "—",
                "confidence": cur.get("confidence") or 0.0,
                "tldr": (cur.get("tldr") or "").strip().replace("\n", " "),
            }
        )

    flips.sort(key=lambda r: r["ticker"])
    return flips[:max_results]


def _load_structtuples(p: Path) -> dict[str, dict[str, Any]]:
    """Light copy of send_weekly.load_current_state to avoid the import dance."""
    out: dict[str, dict[str, Any]] = {}
    if not p.exists():
        return out
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                st = rec.get("struct_tuple") or {}
                if not rec.get("ok") or not st:
                    continue
                ticker = st.get("ticker") or rec.get("ticker")
                if not ticker:
                    continue
                confidence = st.get("confidence_overall")
                if confidence is None and isinstance(st.get("confidence"), dict):
                    confidence = st["confidence"].get("overall")
                elif confidence is None:
                    confidence = st.get("confidence")
                tldr = st.get("tldr") or st.get("structural_summary") or ""
                out[ticker] = {
                    "ticker": ticker,
                    "name": st.get("company_name"),
                    "sector": st.get("sector"),
                    "dynamics_family": st.get("dynamics_family"),
                    "critical_point_state": st.get("critical_point_state"),
                    "confidence": confidence,
                    "tldr": tldr,
                }
    except OSError as e:
        logger.warning("failed to load structtuples %s: %s", p, e)
    return out


def _load_last_week(p: Path) -> dict[str, dict[str, Any]]:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _fetch_phase_api(api_url: str, *, max_results: int) -> list[dict[str, Any]]:
    """GET /api/phases and convert to flip rows.

    The live API doesn't currently expose week-over-week diffs (it's a snapshot
    of the *current* state), so we synthesise a "flip" by treating every
    near_critical entry as `from_state=unknown → to_state=near_critical`. This
    is a degraded view; the file-based diff is canonical.
    """
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning("phase API fetch failed: %s", e)
        return []

    rows: list[dict[str, Any]] = []
    items = data if isinstance(data, list) else data.get("phases") or data.get("companies") or []
    for it in items:
        state = (it.get("critical_point_state") or "").lower()
        if state not in TIPPING_STATES:
            continue
        rows.append(
            {
                "ticker": it.get("ticker"),
                "name": it.get("name") or it.get("company_name") or it.get("ticker"),
                "from_state": "unknown",
                "to_state": state,
                "dynamics_family": it.get("dynamics_family") or "—",
                "confidence": it.get("confidence") or 0.0,
                "tldr": (it.get("tldr") or it.get("summary") or "").strip().replace("\n", " "),
            }
        )
    rows.sort(key=lambda r: r["ticker"] or "")
    return rows[:max_results]


# ---------------------------------------------------------------------------
# 2. arXiv — recent cross-domain SOC / universality preprints
# ---------------------------------------------------------------------------

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_DEFAULT_QUERY = (
    'abs:"self-organized criticality" AND '
    '(abs:"universality" OR abs:"cross-domain" OR abs:"power law")'
)
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_arxiv_papers(
    *,
    week_start: dt.date,
    max_results: int = 5,
    query: str = ARXIV_DEFAULT_QUERY,
    _http: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Return recent preprints published in the week starting `week_start`.

    `_http` is a test seam: pass a callable taking `url` and returning bytes to
    mock the network. Default uses urllib.
    """
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max(max_results * 4, 20)),  # over-fetch then date-filter
    }
    url = ARXIV_API_URL + "?" + urllib.parse.urlencode(params)
    try:
        body = (_http or _http_get)(url)
    except Exception as e:
        logger.warning("arxiv fetch failed: %s", e)
        return []

    try:
        return _parse_arxiv(body, week_start=week_start, max_results=max_results)
    except ET.ParseError as e:
        logger.warning("arxiv XML parse failed: %s", e)
        return []


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
        return r.read()


def _parse_arxiv(body: bytes, *, week_start: dt.date, max_results: int) -> list[dict[str, Any]]:
    """Pure parser for arXiv atom feed — separated for unit-testing."""
    root = ET.fromstring(body)
    entries = root.findall("atom:entry", _ARXIV_NS)
    if not entries:
        return []

    week_end = week_start + dt.timedelta(days=7)
    out: list[dict[str, Any]] = []
    for e in entries:
        title_el = e.find("atom:title", _ARXIV_NS)
        summary_el = e.find("atom:summary", _ARXIV_NS)
        link_el = e.find("atom:id", _ARXIV_NS)
        published_el = e.find("atom:published", _ARXIV_NS)
        if title_el is None or link_el is None or published_el is None:
            continue
        title = " ".join((title_el.text or "").split())
        summary = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
        link = (link_el.text or "").strip()
        try:
            published = dt.datetime.fromisoformat(
                (published_el.text or "").replace("Z", "+00:00")
            ).date()
        except ValueError:
            continue

        # Date filter — last 7 days from week_start. Newsletter shouldn't show
        # papers from 6 months ago even if they match the query.
        if not (week_start <= published < week_end):
            continue

        authors = [
            (a.findtext("atom:name", default="", namespaces=_ARXIV_NS) or "").strip()
            for a in e.findall("atom:author", _ARXIV_NS)
        ]
        authors = [a for a in authors if a]

        one_liner = summary
        if len(one_liner) > 240:
            one_liner = one_liner[:237] + "…"

        out.append(
            {
                "id": link.split("/")[-1],  # e.g. "2405.01234v1"
                "title": title,
                "authors": authors[:3],  # at most 3, "et al." in template
                "url": link,
                "abstract_one_liner": one_liner,
                "published": published.isoformat(),
            }
        )
    # Deterministic order: newest first, ties broken by arxiv id ascending.
    out.sort(key=lambda r: (r["published"], r["id"]), reverse=True)
    return out[:max_results]


# ---------------------------------------------------------------------------
# 3. GitHub — repo activity
# ---------------------------------------------------------------------------

DEFAULT_REPO = "dada8899/structural-isomorphism"


def fetch_github_activity(
    *,
    repo: str = DEFAULT_REPO,
    week_start: dt.date,
    _runner: Optional[Any] = None,
) -> dict[str, int]:
    """Return repo activity numbers for the week starting `week_start`.

    Uses `gh api` (must be installed + authenticated). Falls back to zeros if
    gh is missing or rate-limited. `_runner` is a test seam — pass a callable
    `(argv: list[str]) -> str` returning stdout.

    Returns:
        {
          "new_stars": int,
          "total_stars": int,
          "new_forks": int,
          "total_forks": int,
          "new_contributors": int,
          "new_issues": int,
          "new_prs_external": int,  # external (non-owner) PRs only
        }
    """
    runner = _runner or _run_gh

    def safe_call(argv: list[str], default: Any = None) -> Any:
        try:
            return runner(argv)
        except Exception as e:
            logger.warning("gh %s failed: %s", " ".join(argv), e)
            return default

    if _runner is None and shutil.which("gh") is None:
        logger.warning("gh CLI not installed; returning zeros")
        return _zero_activity()

    week_end = week_start + dt.timedelta(days=7)
    iso_start = week_start.isoformat()
    iso_end = week_end.isoformat()

    # Repo overview (stargazers_count / forks_count)
    repo_blob = safe_call(["repo", "view", repo, "--json", "stargazerCount,forkCount"])
    try:
        repo_json = json.loads(repo_blob) if repo_blob else {}
    except json.JSONDecodeError:
        repo_json = {}

    # New issues + PRs in the week (search API caps at 1000; fine for our scale)
    issues_blob = safe_call(
        [
            "api",
            "-X",
            "GET",
            "/search/issues",
            "-f",
            f"q=repo:{repo} created:{iso_start}..{iso_end} is:issue",
            "--jq",
            ".total_count",
        ],
        default="0",
    )
    prs_blob = safe_call(
        [
            "api",
            "-X",
            "GET",
            "/search/issues",
            "-f",
            f"q=repo:{repo} created:{iso_start}..{iso_end} is:pr -author:dada8899",
            "--jq",
            ".total_count",
        ],
        default="0",
    )

    return {
        "new_stars": 0,  # GitHub API doesn't expose per-week stargazer count
                        # without paginating /stargazers; we leave 0 and report
                        # total instead.
        "total_stars": int(repo_json.get("stargazerCount", 0) or 0),
        "new_forks": 0,
        "total_forks": int(repo_json.get("forkCount", 0) or 0),
        "new_contributors": 0,  # would require diffing contributor lists week-over-week
        "new_issues": _safe_int(issues_blob),
        "new_prs_external": _safe_int(prs_blob),
    }


def _zero_activity() -> dict[str, int]:
    return {
        "new_stars": 0,
        "total_stars": 0,
        "new_forks": 0,
        "total_forks": 0,
        "new_contributors": 0,
        "new_issues": 0,
        "new_prs_external": 0,
    }


def _run_gh(argv: list[str]) -> str:
    proc = subprocess.run(
        ["gh", *argv],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    return proc.stdout


def _safe_int(s: Any) -> int:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 4. Methodology spotlight — rotating topic
# ---------------------------------------------------------------------------

# Pool of methodology micro-essays. One gets rotated in per ISO week.
# Each is ~2 short paragraphs; written once, reused on a slow loop.
# Add new entries here; ID = stable slug, body = pre-rendered markdown.
SPOTLIGHT_POOL: list[dict[str, str]] = [
    {
        "id": "soc-universality-class",
        "title": "What is a SOC universality class?",
        "body": (
            "Self-organized criticality (SOC) groups disparate systems into a "
            "small number of *universality classes* — sets of systems whose "
            "large-scale behaviour (avalanche size distribution, scaling "
            "exponents) collapses onto the same curves regardless of "
            "microscopic detail. Earthquakes, neural avalanches, and forest "
            "fires don't share mechanisms, but the *statistics* of their "
            "cascades obey the same power laws.\n\n"
            "This is why we feel safe applying the same StructTuple schema "
            "to a tech company and a bank — the relevant prediction signal "
            "isn't the industry, it's which universality class the system "
            "belongs to."
        ),
    },
    {
        "id": "early-warning-signals",
        "title": "Early-warning signals: variance + autocorrelation",
        "body": (
            "Near a critical transition, two statistical observables rise: "
            "**variance** and **lag-1 autocorrelation**. The intuition is "
            "*critical slowing down*: as a system approaches a tipping point, "
            "the basin of attraction flattens, and perturbations decay more "
            "slowly. The slower decay shows up as higher autocorrelation; the "
            "shallower basin shows up as larger variance.\n\n"
            "We compute both on rolling 90-day windows of quarterly business "
            "metrics. EWS is not deterministic — bull runs also look noisy — "
            "but combined with structural classification it's a useful prior."
        ),
    },
    {
        "id": "p-hacking-caveats",
        "title": "Why we publish backtests with confidence intervals, not point estimates",
        "body": (
            "It is easy to find a parameter setting where any predictor "
            "*looks* alpha-generating on historical data. We guard against "
            "this by: (a) preregistering the EWS thresholds before running "
            "the next-quarter holdout; (b) reporting confidence intervals "
            "from block-bootstrap, not naive resampling; (c) publishing the "
            "null-hypothesis benchmark alongside the headline number.\n\n"
            "If the CI overlaps the null, we say so. If it doesn't, we still "
            "warn that out-of-sample regime change is the dominant risk."
        ),
    },
    {
        "id": "hysteresis-vs-fold",
        "title": "Hysteresis vs. fold catastrophes",
        "body": (
            "Both describe regime change, but the *recovery path* differs. "
            "A **fold** (saddle-node bifurcation) tips at parameter value λ₁ "
            "and recovers at the same λ₁ — it's reversible. **Hysteresis** "
            "tips at λ₁ but only recovers at λ₂ < λ₁ — it's path-dependent.\n\n"
            "For companies, fold-like dynamics mean a temporary stress event "
            "can recover when conditions normalise; hysteresis means the "
            "*same* favorable conditions that existed before the crisis won't "
            "be enough to restore the prior state. Distinguishing the two is "
            "the single highest-value structural classification we make."
        ),
    },
    {
        "id": "preferential-attachment",
        "title": "Preferential attachment & the winner-take-most regime",
        "body": (
            "When the rate at which a node gains connections is proportional "
            "to its current degree, the system produces a heavy-tailed degree "
            "distribution — the *rich-get-richer* phenomenon. In markets, "
            "this maps to network effects: platforms with the most users "
            "attract the most developers, attracting more users.\n\n"
            "The structural signature is power-law share distribution + low "
            "switching elasticity. The risk signature is *winner concentration*: "
            "the system is brittle to events that disrupt the dominant node, "
            "because no substitute has been allowed to scale."
        ),
    },
    {
        "id": "reflexivity-soros",
        "title": "Reflexive fixed points (Soros revisited)",
        "body": (
            "Soros's *reflexivity* — where perceptions of fundamentals change "
            "the fundamentals themselves — is, statistically, a fixed-point "
            "equation x = f(x, beliefs(x)). When beliefs(x) is amplifying, the "
            "fixed point can become unstable, producing self-fulfilling "
            "bubbles or crashes.\n\n"
            "We classify a company as reflexive when ≥30% of its revenue or "
            "valuation moves with sentiment toward the underlying asset class. "
            "Coinbase, MicroStrategy, and meme stocks all fit; most utilities "
            "don't."
        ),
    },
    {
        "id": "block-bootstrap",
        "title": "Block bootstrap for time-series CIs",
        "body": (
            "Naive bootstrap (resample-with-replacement of individual "
            "observations) is wrong for autocorrelated data — it understates "
            "the true variance. **Block bootstrap** samples *contiguous blocks* "
            "of length ℓ, preserving local correlation structure.\n\n"
            "We default to ℓ = 12 (quarters) for company-level metrics and "
            "report both 95% block-bootstrap CIs and the naive CI for comparison. "
            "When they diverge, autocorrelation is doing real work in the "
            "predictive signal."
        ),
    },
    {
        "id": "structural-tuple",
        "title": "The StructTuple schema",
        "body": (
            "Every company in our coverage gets a tuple of: (dynamics_family, "
            "critical_point_state, confidence, evidence_summary). The first "
            "two are categorical; the third is a [0, 1] calibrated probability; "
            "the fourth is a paragraph linking to public sources.\n\n"
            "The schema's purpose is *reproducible classification*: two "
            "analysts looking at the same 10-K should produce nearly identical "
            "tuples. We measure inter-annotator agreement on a stratified "
            "sample monthly and recalibrate the LLM prompt when κ < 0.7."
        ),
    },
]


def methodology_spotlight(
    *,
    week_start: dt.date,
    override_slug: Optional[str] = None,
) -> dict[str, str]:
    """Pick a methodology entry. Auto-rotation = ISO-week-number mod len(pool).

    `override_slug` lets the CLI force a specific topic (e.g. for hand-curated
    issues). If the slug doesn't exist, we fall back to auto-rotation.
    """
    if override_slug:
        for s in SPOTLIGHT_POOL:
            if s["id"] == override_slug:
                return s
        logger.warning("spotlight slug %r not found; falling back to auto", override_slug)

    iso_year, iso_week, _ = week_start.isocalendar()
    idx = iso_week % len(SPOTLIGHT_POOL)
    return SPOTLIGHT_POOL[idx]


def all_spotlight_slugs() -> list[str]:
    """For CLI --list-spotlights and tests."""
    return [s["id"] for s in SPOTLIGHT_POOL]


# ---------------------------------------------------------------------------
# 5. /api/ask top queries — placeholder
# ---------------------------------------------------------------------------

def fetch_top_ask_queries(*, week_start: dt.date) -> list[dict[str, Any]]:
    """Return top /api/ask queries for the week.

    TODO(W10): wire to live ask analytics. Currently the ask backend logs to a
    server-side JSONL that's not exposed via the public API; pulling it
    requires either an internal endpoint or VPS-side log access. Until that
    plumbing exists, we return an empty list and the generator will emit a
    placeholder paragraph in the newsletter.
    """
    logger.info("fetch_top_ask_queries: placeholder (W10 TODO), returning []")
    return []
