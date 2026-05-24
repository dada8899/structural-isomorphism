"""
Extract StructTuple for a list of companies using LLM general knowledge.

Input:  phase/data/tickers_80.jsonl (one ticker per line with name/industry/marketcap)
Output: phase/data/companies_struct.jsonl (one StructTuple per line)

Uses OpenRouter (Kimi K2-0905 as default — cheap + fast + good at structured output).
Safe to resume: if output already exists, skipped already-done tickers.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    sys.exit("OPENROUTER_API_KEY not set")

PHASE_DIR = Path(__file__).resolve().parent.parent
TICKERS_FILE = PHASE_DIR / "data" / "tickers_80.jsonl"
OUT_FILE = PHASE_DIR / "data" / "companies_struct.jsonl"

DEFAULT_MODEL = os.environ.get("PHASE_EXTRACT_MODEL", "moonshotai/kimi-k2-0905")

PROMPT_TEMPLATE = """You extract structural signatures for public companies. The user is building a tool
that filters companies by their mathematical dynamics rather than financial ratios.

Given a company, output a JSON object describing its **current** structural state as a
dynamical system. Use your general knowledge — do not fetch real-time data, assume the
market_cap and industry context given.

Required schema (output ONLY a JSON object, no prose, no markdown fences):

{{
  "ticker": "<exact ticker as input>",
  "name": "<company name>",
  "exchange": "<exchange>",
  "country": "<country>",
  "industry": "<industry>",
  "market_cap_usd": <number>,

  "state_vars": [
    {{"symbol": "N", "meaning": "订阅用户数 / 年销量 / 月活 / etc.", "type": "count|volume|price|other"}}
  ],

  "dynamics_family": "<one of: ODE1_linear | ODE1_exponential_growth | ODE1_exponential_decay | ODE1_logistic | ODE1_saturating | ODE2_damped_oscillation | ODE2_undamped_oscillation | DDE_delayed_feedback | PDE_reaction_diffusion | PDE_wave | PDE_diffusion | Markov_chain | Markov_decision | Percolation_threshold | Phase_transition_1st | Phase_transition_2nd | Game_theoretic_equilibrium | Self_fulfilling_prophecy | Power_law_distribution | Heavy_tail_extremal | Network_cascade | Percolation_network | Hysteresis_loop | Bistable_switch | Fold_bifurcation | Hopf_bifurcation | Stochastic_process | Random_walk | Unknown>",

  "feedback_topology": "<one of: positive_loop | negative_loop | delayed_positive | delayed_negative | bistable | multistable | none | unknown>",

  "boundary_behavior": "<one of: runaway | saturation | limit_cycle | fixed_point | decay_to_zero | fold_bifurcation | hopf_bifurcation | phase_transition | power_law_tail | unknown>",

  "timescale_log10_s": <integer 5-10, default 7 if ambiguous. 5 = days, 6 = weeks, 7 = months, 8 = years, 9 = decades>,

  "phase_state": "<one of: stable | approaching_critical | post_transition | unstable | growth_phase | saturated | contracting>",

  "canonical_equation": "<LaTeX-style equation that best approximates the company's dynamics, e.g. 'dN/dt = r N (1 - N/K)' — or empty string if none fits>",

  "key_parameters": [
    {{"symbol": "K", "meaning": "effective carrying capacity (users)", "estimate": "3.48e8"}}
  ],

  "critical_points": ["specific conditions that would trigger phase shifts, in Chinese or English"],

  "confidence": <float 0-1>,
  "note": "<short Chinese note describing the single most important structural fact about this company>"
}}

Rules:
1. Pick ONE primary dynamics_family. If the company shows two overlapping dynamics, pick the dominant one and mention the second in "note".
2. `phase_state` should reflect the CURRENT business state. "growth_phase" for early-stage, "saturated" for mature, "approaching_critical" when a visible transition is near.
3. `canonical_equation` should be specific. "Verhulst-Pearl logistic" → `dN/dt = r N (1 - N/K)`. "SIR" → `dI/dt = beta S I - gamma I`. Don't invent equations.
4. `critical_points` should be specific, measurable conditions (e.g., "ARPU 跌破 $10", "监管 de minimis 降到 $100 以下"). Not vague ("if things get bad").
5. `confidence` should be lower when the company has multiple overlapping business models.

Input:

ticker: {ticker}
name: {name}
exchange: {exchange}
country: {country}
industry: {industry}
market_cap_usd: {market_cap_usd}
"""


def load_tickers() -> list:
    out = []
    with open(TICKERS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def load_done() -> set:
    if not OUT_FILE.exists():
        return set()
    done = set()
    with open(OUT_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                if d.get("ticker") and "_error" not in d:
                    done.add(d["ticker"])
            except Exception:
                pass
    return done


def call_openrouter(model_id: str, prompt: str, timeout: int = 90) -> str:
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1500,
        }).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://beta.structural.bytedance.city",
            "X-Title": "phase-detector-extract",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def main():
    tickers = load_tickers()
    done = load_done()
    todo = [t for t in tickers if t["ticker"] not in done]
    print(f"Total: {len(tickers)}, done: {len(done)}, todo: {len(todo)}")
    print(f"Model: {DEFAULT_MODEL}")
    print(f"Output: {OUT_FILE}")

    start = time.time()
    ok = 0
    err = 0
    with open(OUT_FILE, "a", encoding="utf-8") as f:
        for i, t in enumerate(todo, 1):
            t0 = time.time()
            prompt = PROMPT_TEMPLATE.format(**t)
            try:
                raw = call_openrouter(DEFAULT_MODEL, prompt)
                parsed = parse_json(raw)
                # Ensure ticker is set correctly
                parsed["ticker"] = t["ticker"]
                parsed["_source"] = DEFAULT_MODEL
                f.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                f.flush()
                ok += 1
                dt = time.time() - t0
                print(f"  [{i}/{len(todo)}] {t['ticker']:<12} {dt:5.1f}s  {parsed.get('dynamics_family', '?')}")
            except Exception as e:
                err += 1
                f.write(json.dumps({"ticker": t["ticker"], "_error": str(e)[:200]}) + "\n")
                f.flush()
                print(f"  [{i}/{len(todo)}] {t['ticker']:<12} ERR: {str(e)[:100]}")

    elapsed = time.time() - start
    print(f"\nDone. ok={ok} err={err} elapsed={elapsed:.1f}s")


if __name__ == "__main__":
    main()
