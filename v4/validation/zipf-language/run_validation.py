#!/usr/bin/env python3
"""Zipf's law multi-language validation.

Pipeline
--------
1. Tokenize per language (Brown English, Wikipedia 5 languages).
   - Latin-script (en, es): regex word boundaries, lowercased.
   - Arabic (ar): regex unicode word boundaries; strip diacritics.
   - Hindi (hi): regex unicode word boundaries (Devanagari).
   - Chinese (zh): jieba word segmentation (no whitespace boundaries).
2. Build rank-frequency distribution.
3. Fit Zipf exponent s via:
   (a) Linear regression of log(freq) on log(rank) on the head (top-K).
   (b) Clauset 2009 power-law via soc_pipeline.fit_clauset_powerlaw on
       the upper tail of the frequency distribution.
   Note: Zipf's classical exponent s and Clauset's alpha are related but
   measured on different objects. For P(rank) propto 1/rank^s, the
   probability distribution P(f) propto f^{-(1 + 1/s)}, so alpha = 1 + 1/s.
   We report both s_rank (the natural Zipf exponent) and alpha_clauset.

Outputs
-------
zipf_results.json     per-language fits + summary statistics
zipf_loglog.png       rank-frequency overlay plot (if matplotlib available)
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RAW = ROOT / "raw"

sys.path.insert(0, str(REPO / "packages" / "soc-pipeline" / "src"))
try:
    from soc_pipeline import fit_clauset_powerlaw
    HAS_SOC = True
except Exception as e:
    print(f"[warn] soc-pipeline import failed: {e}")
    HAS_SOC = False


# ------------------------------------------------------------------
# Tokenization
# ------------------------------------------------------------------

_LATIN_RE = re.compile(r"[A-Za-zÁ-ÿÀ-ſ]+", re.UNICODE)
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]+")
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]+")


def strip_arabic_diacritics(text: str) -> str:
    """Remove tashkeel diacritics that artificially fragment tokens."""
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def tokenize(text: str, lang: str) -> List[str]:
    if lang in {"en", "es"}:
        return [t.lower() for t in _LATIN_RE.findall(text)]
    if lang == "ar":
        text = strip_arabic_diacritics(text)
        return _ARABIC_RE.findall(text)
    if lang == "hi":
        return _DEVANAGARI_RE.findall(text)
    if lang == "zh":
        import jieba
        # Strip non-CJK chars before segmenting; jieba is robust either way
        toks = [t.strip() for t in jieba.cut(text) if t.strip()]
        # Keep tokens with at least one CJK char, drop punctuation-only
        keep = []
        for t in toks:
            if any("一" <= c <= "鿿" for c in t):
                keep.append(t)
        return keep
    raise ValueError(f"unsupported lang {lang}")


# ------------------------------------------------------------------
# Zipf fit
# ------------------------------------------------------------------

def rank_freq(tokens: List[str]) -> Tuple[np.ndarray, np.ndarray, int]:
    """Return (ranks, freqs_sorted_desc, vocab_size)."""
    counts = Counter(tokens)
    freqs = np.array(sorted(counts.values(), reverse=True), dtype=float)
    ranks = np.arange(1, len(freqs) + 1, dtype=float)
    return ranks, freqs, len(counts)


def fit_zipf_loglog(ranks: np.ndarray, freqs: np.ndarray,
                    rank_lo: int = 10, rank_hi: int = 1000) -> Dict:
    """OLS fit log(freq) = log(C) - s * log(rank) on the head excluding the
    very top (which deviates per Mandelbrot) and excluding the long tail.

    Returns slope s, intercept logC, r^2, residual std.
    """
    mask = (ranks >= rank_lo) & (ranks <= min(rank_hi, len(ranks)))
    if mask.sum() < 20:
        return {"error": f"only {int(mask.sum())} ranks in fit window"}

    lr = np.log(ranks[mask])
    lf = np.log(freqs[mask])
    s_neg, log_c = np.polyfit(lr, lf, 1)
    s = -s_neg
    pred = log_c + s_neg * lr
    ss_res = np.sum((lf - pred) ** 2)
    ss_tot = np.sum((lf - lf.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    resid_std = float(np.std(lf - pred))
    return {
        "s_rank": float(s),
        "log_c": float(log_c),
        "r2": float(r2),
        "resid_std": resid_std,
        "rank_lo": rank_lo,
        "rank_hi_used": int(min(rank_hi, len(ranks))),
        "n_points": int(mask.sum()),
    }


def fit_alpha_clauset(freqs: np.ndarray) -> Dict:
    """Run Clauset fit on the empirical frequency distribution.

    For Zipf P(rank) propto rank^-s, the freq distribution has alpha = 1 + 1/s.
    """
    if not HAS_SOC:
        return {"error": "soc_pipeline unavailable"}
    if len(freqs) < 100:
        return {"error": f"only {len(freqs)} samples"}
    try:
        result = fit_clauset_powerlaw(freqs.astype(float), discrete=True,
                                      min_samples=100)
        return {
            "alpha_clauset": float(result.alpha) if result.alpha is not None else None,
            "alpha_se": float(result.sigma) if result.sigma is not None else None,
            "xmin": float(result.xmin) if result.xmin is not None else None,
            "n_tail": int(result.n_tail) if result.n_tail is not None else None,
            "ks": float(result.ks_statistic) if result.ks_statistic is not None else None,
        }
    except Exception as e:
        return {"error": str(e)}


# ------------------------------------------------------------------
# Cross-language statistics
# ------------------------------------------------------------------

def chi_square_homogeneity(s_values: List[float], s_errors: List[float],
                           s_expected: float = 1.0) -> Dict:
    """One-sample chi-square test for whether all s values are jointly
    consistent with s_expected, using per-language SE (resid_std as proxy).
    """
    s_arr = np.asarray(s_values)
    e_arr = np.asarray(s_errors)
    # Guard divide-by-zero
    e_arr = np.where(e_arr > 1e-6, e_arr, 0.05)
    chi2 = float(np.sum(((s_arr - s_expected) / e_arr) ** 2))
    dof = len(s_arr)  # one-sample, n constraints
    return {"chi2": chi2, "dof": dof,
            "chi2_per_dof": chi2 / dof if dof else float("nan")}


def isomorphism_distance(s_obs: float, s_ref: float, se_obs: float,
                         se_ref: float) -> float:
    """Distance in pooled-SE units; |s_obs - s_ref| / sqrt(se_obs^2 + se_ref^2)."""
    pooled = float(np.sqrt(se_obs ** 2 + se_ref ** 2))
    return float(abs(s_obs - s_ref) / pooled) if pooled > 0 else float("inf")


# ------------------------------------------------------------------
# Plot
# ------------------------------------------------------------------

def make_plot(per_lang: Dict, out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [plot] matplotlib unavailable: {e}")
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    colors = {"brown_en": "#1f77b4", "wiki_en": "#ff7f0e", "wiki_zh": "#d62728",
              "wiki_ar": "#2ca02c", "wiki_hi": "#9467bd", "wiki_es": "#8c564b"}
    for label, d in per_lang.items():
        if "ranks" not in d:
            continue
        r = np.asarray(d["ranks"])
        f = np.asarray(d["freqs"])
        keep = (r <= 5000)
        ax.loglog(r[keep], f[keep], ".", ms=2, alpha=0.5,
                  color=colors.get(label, "gray"),
                  label=f"{label} s={d['fit'].get('s_rank', float('nan')):.2f}")
    ax.set_xlabel("Rank")
    ax.set_ylabel("Frequency")
    ax.set_title("Zipf rank-frequency, 6 corpora (multi-language)")
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

CORPORA = [
    ("brown_en", "en", RAW / "brown_en.txt"),
    ("wiki_en", "en", RAW / "wiki_en.txt"),
    ("wiki_zh", "zh", RAW / "wiki_zh.txt"),
    ("wiki_ar", "ar", RAW / "wiki_ar.txt"),
    ("wiki_hi", "hi", RAW / "wiki_hi.txt"),
    ("wiki_es", "es", RAW / "wiki_es.txt"),
]


def main() -> None:
    per_lang: Dict[str, Dict] = {}

    for label, lang, path in CORPORA:
        if not path.exists():
            print(f"  [skip] {label}: {path} missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        tokens = tokenize(text, lang)
        if len(tokens) < 1000:
            print(f"  [skip] {label}: only {len(tokens)} tokens after tokenization")
            continue
        ranks, freqs, vocab = rank_freq(tokens)
        fit_ll = fit_zipf_loglog(ranks, freqs, rank_lo=10, rank_hi=1000)
        fit_cl = fit_alpha_clauset(freqs)
        per_lang[label] = {
            "language": lang,
            "n_tokens": int(len(tokens)),
            "vocab_size": int(vocab),
            "fit": fit_ll,
            "clauset": fit_cl,
            "ranks": ranks[:5000].tolist(),
            "freqs": freqs[:5000].tolist(),
        }
        print(f"  [{label}] n={len(tokens):>8d} V={vocab:>6d}  "
              f"s_rank={fit_ll.get('s_rank', float('nan')):.3f}  "
              f"r2={fit_ll.get('r2', 0):.3f}  "
              f"alpha_clauset={fit_cl.get('alpha_clauset', float('nan'))}")

    # Cross-language chi-square (5 languages: wiki_en/zh/ar/hi/es; Brown reported separately)
    cross_keys = ["wiki_en", "wiki_zh", "wiki_ar", "wiki_hi", "wiki_es"]
    s_vals, s_errs = [], []
    for k in cross_keys:
        if k in per_lang and "s_rank" in per_lang[k]["fit"]:
            s_vals.append(per_lang[k]["fit"]["s_rank"])
            s_errs.append(per_lang[k]["fit"]["resid_std"])
    chi2 = chi_square_homogeneity(s_vals, s_errs, s_expected=1.0) if s_vals else {}

    # Reference (preferential_attachment sibling Zipf exponents)
    references = {
        # P(rank) propto rank^-s
        # Pareto wealth: Pareto alpha ~ 1.5-3 on income/wealth tail; in rank
        # representation s_pareto = 1 / (alpha - 1) ~ 0.5-2.  Use 1.0 as
        # canonical (Pareto 80/20 = alpha ln(5)/ln(4) ~ 1.16).
        "pareto_wealth_rank_s": {"s": 1.0, "se": 0.15, "source": "Pareto 1896 income; WID world avg"},
        # City size Zipf-Gibrat (Gabaix 1999, Auerbach 1913): s ~ 1.0
        "city_size_zipf": {"s": 1.0, "se": 0.10, "source": "Gabaix 1999; Zipf 1949"},
        # Classic linguistic Zipf
        "zipf_classical": {"s": 1.0, "se": 0.10, "source": "Zipf 1949"},
    }

    # Isomorphism distance for each language vs city + pareto
    iso_distances = {}
    for k in per_lang:
        s = per_lang[k]["fit"].get("s_rank")
        se = per_lang[k]["fit"].get("resid_std")
        if s is None or se is None:
            continue
        iso_distances[k] = {
            ref: isomorphism_distance(s, refdata["s"], se, refdata["se"])
            for ref, refdata in references.items()
        }

    out_path = ROOT / "zipf_results.json"
    out = {
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "per_language": {
            k: {kk: vv for kk, vv in v.items() if kk not in {"ranks", "freqs"}}
            for k, v in per_lang.items()
        },
        "cross_language_chi2": chi2,
        "references": references,
        "isomorphism_distances": iso_distances,
        "expected_band": [0.9, 1.2],
        "verdict_per_lang": {
            k: ("PASS" if (0.9 <= v["fit"].get("s_rank", 0) <= 1.2)
                else ("INCONCLUSIVE" if 0.5 <= v["fit"].get("s_rank", 0) <= 2.0
                      else "FAIL"))
            for k, v in per_lang.items()
        },
    }
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nResults: {out_path}")

    plot_path = ROOT / "zipf_loglog.png"
    make_plot(per_lang, plot_path)
    print(f"Plot:    {plot_path}")


if __name__ == "__main__":
    main()
