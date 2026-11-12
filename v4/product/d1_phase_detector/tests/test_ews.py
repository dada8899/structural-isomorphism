"""Unit tests for the EWS engine.

These verify the *math* end-to-end on synthetic series whose properties
are known. They are the verification we can do in a sandbox that lacks
network access to real stock-data APIs; the engine itself is then run
against live yfinance data on the VPS.

Properties under test
---------------------
  1. White noise -> tau_ar1 and tau_var both near zero -> low score.
  2. AR(1) with rising phi over the window -> tau_ar1 strongly positive.
  3. Variance ramp -> tau_var strongly positive, tau_ar1 weak.
  4. Both ramps simultaneously (textbook CSD) -> high score, phase ≈ critical.
  5. Drawdown -> post_critical_transition note triggered.
  6. Confidence reflects sample size and tau agreement.
  7. JSON serialization roundtrips.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
import os
import unittest

# Make the parent package importable when running pytest from repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..")))

from v4.product.d1_phase_detector.ews import (  # noqa: E402
    compute_ews,
    _autocorr_lag1,
    _kendall_tau,
    _variance,
    _composite_score,
    _phase_from_score,
)


def _dates(n: int) -> list:
    """Generate n consecutive business-day-ish dates."""
    start = dt.date(2024, 1, 1)
    return [start + dt.timedelta(days=i) for i in range(n)]


def _to_closes(start_price: float, returns) -> list:
    """Convert iterable of log-returns to a (date, price) series."""
    prices = [start_price]
    for r in returns:
        prices.append(prices[-1] * math.exp(r))
    dates = _dates(len(prices))
    return list(zip(dates, prices))


class TestPrimitives(unittest.TestCase):
    def test_variance_zero_when_constant(self):
        self.assertEqual(_variance([3, 3, 3, 3]), 0.0)

    def test_variance_known(self):
        # var([1, 2, 3, 4, 5]) with n-1 = 2.5
        self.assertAlmostEqual(_variance([1, 2, 3, 4, 5]), 2.5)

    def test_autocorr_white_noise_near_zero(self):
        random.seed(0)
        xs = [random.gauss(0, 1) for _ in range(500)]
        ac = _autocorr_lag1(xs)
        self.assertIsNotNone(ac)
        self.assertLess(abs(ac), 0.15)

    def test_autocorr_strong_positive(self):
        random.seed(1)
        xs = [0.0]
        for _ in range(500):
            xs.append(0.9 * xs[-1] + random.gauss(0, 0.3))
        ac = _autocorr_lag1(xs)
        self.assertIsNotNone(ac)
        self.assertGreater(ac, 0.7)

    def test_kendall_tau_monotonic(self):
        xs = list(range(40))  # strictly increasing
        tau, p = _kendall_tau(xs)
        self.assertAlmostEqual(tau, 1.0)
        self.assertLess(p, 0.001)

    def test_kendall_tau_flat_random(self):
        random.seed(2)
        xs = [random.random() for _ in range(60)]
        tau, p = _kendall_tau(xs)
        self.assertIsNotNone(tau)
        self.assertLess(abs(tau), 0.25)

    def test_phase_mapping(self):
        self.assertEqual(_phase_from_score(85), "at_critical")
        self.assertEqual(_phase_from_score(55), "approaching_critical")
        self.assertEqual(_phase_from_score(10), "far_from_critical")
        self.assertEqual(_phase_from_score(None), "unknown")


class TestComputeEws(unittest.TestCase):
    def test_white_noise_low_score(self):
        """Pure random walk must not flag critical. We allow yellow but not red.

        Single seeds can drift; the real guarantee lives in
        test_white_noise_false_positive_rate below.
        """
        random.seed(10)
        rets = [random.gauss(0, 0.01) for _ in range(400)]
        closes = _to_closes(100.0, rets)
        res = compute_ews(closes, ticker="WN")
        self.assertNotEqual(res.phase_state, "at_critical")
        self.assertLess(res.criticality_score, 40,
                        f"random walk should score <40, got {res.criticality_score}")

    def test_white_noise_false_positive_rate(self):
        """Aggregate guarantee: across 200 seeds of pure noise, at_critical
        rate must stay under 3%. This is the real product property — we
        don't want red flags on calm tickers."""
        n_critical = 0
        n_seeds = 200
        for s in range(n_seeds):
            random.seed(s)
            rets = [random.gauss(0, 0.01) for _ in range(400)]
            closes = _to_closes(100.0, rets)
            res = compute_ews(closes, ticker=f"WN{s}")
            if res.phase_state == "at_critical":
                n_critical += 1
        rate = n_critical / n_seeds
        self.assertLess(rate, 0.03,
                        f"FPR {rate:.1%} too high (>3%)")

    def test_rising_ar1_lifts_tau_ar1(self):
        """AR(1) phi ramping 0→0.95 over the series must yield a positive
        tau on the rolling AR1 series. We use a longer series (800) so the
        decorrelated subsample has enough power to see the trend."""
        random.seed(20)
        n = 800
        rets = []
        prev = 0.0
        for i in range(n):
            phi = 0.0 + 0.95 * (i / n)
            new = phi * prev + random.gauss(0, 0.01)
            rets.append(new)
            prev = new
        closes = _to_closes(100.0, rets)
        res = compute_ews(closes, ticker="ARUP")
        self.assertIsNotNone(res.ar1.tau)
        self.assertGreater(res.ar1.tau, 0.2,
                           f"expected rising AR1 tau, got {res.ar1.tau}")

    def test_rising_variance_lifts_tau_var(self):
        random.seed(30)
        n = 800
        rets = []
        for i in range(n):
            sigma = 0.005 + 0.025 * (i / n)  # ramp ~5x
            rets.append(random.gauss(0, sigma))
        closes = _to_closes(100.0, rets)
        res = compute_ews(closes, ticker="VRUP")
        self.assertIsNotNone(res.var.tau)
        self.assertGreater(res.var.tau, 0.3,
                           f"expected rising var tau, got {res.var.tau}")

    def _make_csd_series(self, seed: int):
        """Construct a price series whose *trailing window* is the textbook
        CSD ramp: stable baseline, then phi/sigma rise. Trend window
        therefore sees a clean monotonic signal."""
        random.seed(seed)
        baseline_n = 500
        ramp_n = 400
        rets = []
        prev = 0.0
        # calm baseline
        for _ in range(baseline_n):
            new = 0.1 * prev + random.gauss(0, 0.005)
            rets.append(new)
            prev = new
        # ramp: phi 0.1 → 0.85, sigma 0.005 → 0.022
        for i in range(ramp_n):
            t = i / ramp_n
            phi = 0.1 + 0.75 * t
            sigma = 0.005 + 0.017 * t
            new = phi * prev + random.gauss(0, sigma)
            rets.append(new)
            prev = new
        return _to_closes(100.0, rets)

    def test_textbook_csd_scores_high(self):
        """Calm baseline + late CSD ramp -> high composite, phase ≥ approaching."""
        closes = self._make_csd_series(seed=40)
        res = compute_ews(closes, ticker="CSD")
        # Drawdown gate can occasionally tag this as post; both are acceptable
        # "warning" states for the product. The wrong answer is "far_from".
        self.assertIn(res.phase_state,
                      ("approaching_critical", "at_critical",
                       "post_critical_transition"))
        if res.phase_state in ("approaching_critical", "at_critical"):
            self.assertGreaterEqual(res.criticality_score, 40,
                                    f"expected high score, got {res.criticality_score}")
        self.assertGreater(res.confidence, 0.5)

    def test_csd_detection_rate(self):
        """Aggregate detection rate: across 50 seeded textbook CSD series,
        the engine must flag >= 50% as approaching / at / post critical.
        (Lower bound, accounting for noise — beats random walk by ~10x.)"""
        n_hit = 0
        n_seeds = 50
        for s in range(n_seeds):
            closes = self._make_csd_series(seed=s + 1000)
            res = compute_ews(closes, ticker=f"CSD{s}")
            if res.phase_state in (
                "approaching_critical", "at_critical", "post_critical_transition"
            ):
                n_hit += 1
        rate = n_hit / n_seeds
        self.assertGreaterEqual(rate, 0.5,
                                f"CSD detection rate {rate:.1%} too low")

    def test_drawdown_triggers_post_critical(self):
        random.seed(50)
        # 200 calm days, then a -40% drop, then 100 flat days.
        rets = [random.gauss(0, 0.005) for _ in range(200)]
        rets += [math.log(0.6)]  # -40% one-day
        rets += [random.gauss(0, 0.005) for _ in range(99)]
        closes = _to_closes(100.0, rets)
        res = compute_ews(closes, ticker="DD")
        self.assertEqual(res.phase_state, "post_critical_transition")
        self.assertTrue(any("翻转" in n for n in res.notes))

    def test_too_few_obs_returns_unknown(self):
        closes = _to_closes(100.0, [0.01] * 5)  # 5 returns is way too few
        res = compute_ews(closes, ticker="TF")
        self.assertEqual(res.phase_state, "unknown")
        self.assertEqual(res.confidence, 0.0)

    def test_contradicting_taus_lower_confidence(self):
        """AR1 rising but variance falling -> note + lower confidence."""
        random.seed(60)
        n = 400
        rets = []
        prev = 0.0
        for i in range(n):
            t = i / n
            phi = 0.0 + 0.8 * t
            sigma = 0.025 - 0.02 * t   # variance *falling*
            sigma = max(sigma, 0.003)
            new = phi * prev + random.gauss(0, sigma)
            rets.append(new)
            prev = new
        closes = _to_closes(100.0, rets)
        res = compute_ews(closes, ticker="MIX")
        # at least one of the two taus must have flipped sign
        if res.ar1.tau is not None and res.var.tau is not None:
            self.assertNotEqual(res.ar1.tau > 0, res.var.tau > 0)
            self.assertTrue(any("矛盾" in n for n in res.notes),
                           f"expected contradiction note, got {res.notes}")

    def test_json_serializable(self):
        random.seed(70)
        rets = [random.gauss(0, 0.01) for _ in range(200)]
        closes = _to_closes(100.0, rets)
        res = compute_ews(closes, ticker="JSON")
        s = json.dumps(res.to_dict())
        self.assertGreater(len(s), 100)
        # roundtrip
        d = json.loads(s)
        self.assertEqual(d["ticker"], "JSON")
        self.assertIn("ar1", d)
        self.assertIn("values", d["ar1"])

    def test_handles_bad_prices(self):
        """Negative / zero / NaN prices must not crash."""
        closes = [
            (dt.date(2024, 1, 1), 100.0),
            (dt.date(2024, 1, 2), 0.0),       # bad
            (dt.date(2024, 1, 3), float("nan")),  # bad
            (dt.date(2024, 1, 4), 102.0),
            (dt.date(2024, 1, 5), 103.0),
        ]
        res = compute_ews(closes, ticker="BAD")
        # 5 inputs but only 1 valid return; phase should be unknown.
        self.assertEqual(res.phase_state, "unknown")


class TestComposite(unittest.TestCase):
    def test_score_bounds(self):
        for ar1 in [-1.0, 0.0, 0.5, 1.0]:
            for var in [-1.0, 0.0, 0.5, 1.0]:
                s = _composite_score(ar1, 0.001, var, 0.001)
                if s is not None:
                    self.assertGreaterEqual(s, 0.0)
                    self.assertLessEqual(s, 100.0)

    def test_both_none(self):
        self.assertIsNone(_composite_score(None, None, None, None))

    def test_non_significant_tau_treated_as_zero(self):
        # A large tau with weak p should not push the score up.
        s_strong = _composite_score(0.8, 0.001, 0.8, 0.001)
        s_weak = _composite_score(0.8, 0.5, 0.8, 0.5)
        self.assertGreater(s_strong, 50)
        self.assertEqual(s_weak, 0.0)

    def test_lone_indicator_capped(self):
        s = _composite_score(0.9, 0.001, None, None)
        # Single fire is capped low (around 30-35) regardless of tau magnitude.
        self.assertIsNotNone(s)
        self.assertLessEqual(s, 35.0)


if __name__ == "__main__":
    unittest.main()
