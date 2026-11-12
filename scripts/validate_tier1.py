"""
Tier-1 Validation Pipeline — 3-layer funnel for 24 tier-1 discoveries.

Layer 1: LLM literature cross-check (3 heterogeneous models)
Layer 2: Blind multi-model rating (5 models, 3 questions)
Layer 3: Prediction-power generation (Opus)

Usage:
    python validate_tier1.py --layer 1
    python validate_tier1.py --layer 2
    python validate_tier1.py --layer 3
    python validate_tier1.py --layer 1 --smoke    # smoke test: 2 rows only
    python validate_tier1.py --layer 1 --summary  # re-compute survivors from existing results

Outputs:
    validation/layer{1,2,3}-results.jsonl    (append-only, resume-safe)
    validation/layer{1,2}-survivors.jsonl    (post-hoc filtered)
    validation/predictions.md                (Layer 3 human-review doc)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_DIR = Path(__file__).parent.parent
VALIDATION_DIR = PROJECT_DIR / "validation"
INPUT_FILE = VALIDATION_DIR / "tier1-input.jsonl"
ENV_FILE = PROJECT_DIR / "web" / "backend" / ".env"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Layer 1 — literature cross-check (3 heterogeneous, JSON-reliable models)
# Dropped GPT-5 (returns None content due to reasoning tokens eating budget)
# Swapped to Kimi K2.5: different training corpus, broad Chinese+English lit.
LAYER1_MODELS = [
    "anthropic/claude-opus-4.1",     # anthropic family
    "google/gemini-2.5-pro",          # google family (needs reasoning bound)
    "moonshotai/kimi-k2.5",           # chinese flagship, independent view
]

# Layer 2 — blind rating (Layer 1 set + 2 more heterogeneous)
LAYER2_MODELS = LAYER1_MODELS + [
    "deepseek/deepseek-r1",
    "z-ai/glm-5",
]

# Layer 3 — prediction generation (single high-quality model)
LAYER3_MODEL = "anthropic/claude-opus-4.1"


def load_env() -> str:
    if not ENV_FILE.exists():
        print(f"ERROR: .env not found at {ENV_FILE}", file=sys.stderr)
        sys.exit(1)
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    print("ERROR: OPENROUTER_API_KEY not found in .env", file=sys.stderr)
    sys.exit(1)


def load_tier1() -> list[dict]:
    rows = []
    with open(INPUT_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def call_openrouter(
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int = 4000,
    temperature: float = 0.2,
    retries: int = 3,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Synchronous OpenRouter call with retry. Returns {'text', 'tokens', 'model', 'error'}"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://structural.bytedance.city",
        "X-Title": "structural-isomorphism validation",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Bound reasoning tokens for reasoning-heavy models so visible content isn't starved.
    # OpenRouter rejects specifying both effort+max_tokens together — pick one.
    if any(k in model for k in ["gemini-2.5-pro", "deepseek-r1", "o1", "o3"]):
        body["reasoning"] = {"max_tokens": 500}
    elif "gpt-5" in model:
        body["reasoning"] = {"effort": "low"}
    last_err = None
    for attempt in range(retries):
        try:
            # trust_env=False bypasses HTTP_PROXY/HTTPS_PROXY; some local proxies
            # (e.g. Clash on :7890) stall on long LLM responses.
            with httpx.Client(timeout=timeout, trust_env=False) as client:
                resp = client.post(OPENROUTER_URL, headers=headers, json=body)
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
                    time.sleep(2 ** attempt)
                    continue
                data = resp.json()
                msg = data["choices"][0]["message"]
                # Prefer visible content; fall back to reasoning field if content is empty
                text = msg.get("content") or ""
                if not text:
                    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
                    text = reasoning
                usage = data.get("usage", {})
                return {
                    "text": text,
                    "tokens_in": usage.get("prompt_tokens", 0),
                    "tokens_out": usage.get("completion_tokens", 0),
                    "model": model,
                    "error": None,
                }
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2 ** attempt)
    return {"text": "", "tokens_in": 0, "tokens_out": 0, "model": model, "error": last_err}


def _fix_invalid_escapes(s: str) -> str:
    """Escape backslashes that precede non-JSON-escape chars (e.g. LaTeX \\alpha).
    Valid JSON escapes after \\: " \\ / b f n r t u"""
    import re
    return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)


def extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from LLM output. Handles markdown code blocks
    and lenient fallback for invalid escapes (LaTeX, etc.)."""
    if not text:
        return None
    t = text.strip()
    # Strip markdown fences
    if t.startswith("```"):
        lines = t.split("\n")
        t = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # Find first { and last }
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    raw = t[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Lenient: escape invalid backslash sequences
    try:
        return json.loads(_fix_invalid_escapes(raw))
    except json.JSONDecodeError:
        return None


# ========== Layer 1: Literature Cross-Check ==========

LAYER1_PROMPT_TEMPLATE = """你是一位跨学科研究专家，精通物理、生物、经济、信息论、计算机系统、社会学等领域的学术文献。

任务：独立判断下面这个"跨域结构同构"是否已在学术文献中被明确提出过。

现象 A：{a_name}
现象 B：{b_name}
核心方程/机制：{equations}

关键要求：
- 严格判断"跨域类比本身"是否被提出，而不是 A 或 B 各自被研究过
- **不要输出分析过程、不要解释你的推理，直接输出 JSON**
- **不要用 markdown 代码块包裹**
- 所有字段必须用英文引号，不要在字符串里用反斜杠（例如 LaTeX 请改用纯文本）

输出格式（严格遵守，只输出这一个 JSON 对象）：
{{
  "verdict": "KNOWN" 或 "WEAK_KNOWN" 或 "UNKNOWN" 或 "UNCERTAIN",
  "citations": ["作者 年份 - 论点 - 来源类型", "..."],
  "reasoning": "一两句话说明理由"
}}

verdict 定义：
- KNOWN：A↔B 类比已被学术界明确提出并讨论，业内公认
- WEAK_KNOWN：有零星提及但没有系统化的论文专门讨论
- UNKNOWN：在你的知识范围内未见
- UNCERTAIN：记忆模糊，需要人工核查"""


def run_layer1(api_key: str, smoke: bool = False) -> None:
    rows = load_tier1()
    if smoke:
        rows = rows[:2]
        print(f"[smoke] using {len(rows)} rows")

    out_file = VALIDATION_DIR / ("layer1-results.smoke.jsonl" if smoke else "layer1-results.jsonl")

    # Resume: only skip successful parses (retry errors + parse failures)
    done: set[tuple[int, str]] = set()
    if out_file.exists():
        with open(out_file) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get("parsed") is not None and r.get("error") is None:
                        done.add((r["idx"], r["model"]))
                except Exception:
                    pass
        print(f"Resume: {len(done)} successful results already")

    total = len(rows) * len(LAYER1_MODELS)
    remaining = total - len(done)
    print(f"Layer 1: {len(rows)} rows × {len(LAYER1_MODELS)} models = {total} calls ({remaining} remaining)")

    total_tokens_in = 0
    total_tokens_out = 0
    with open(out_file, "a") as f_out:
        for row in rows:
            idx = row["_idx"]
            prompt = LAYER1_PROMPT_TEMPLATE.format(
                a_name=row["a_name"],
                b_name=row["b_name"],
                equations=row.get("equations", ""),
            )
            for model in LAYER1_MODELS:
                if (idx, model) in done:
                    continue
                t0 = time.time()
                result = call_openrouter(api_key, model, prompt, max_tokens=4000)
                dt = time.time() - t0
                parsed = extract_json(result["text"])
                record = {
                    "idx": idx,
                    "a_name": row["a_name"],
                    "b_name": row["b_name"],
                    "model": model,
                    "raw_text": result["text"],
                    "parsed": parsed,
                    "verdict": parsed.get("verdict") if parsed else None,
                    "tokens_in": result["tokens_in"],
                    "tokens_out": result["tokens_out"],
                    "elapsed": round(dt, 2),
                    "error": result["error"],
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()
                total_tokens_in += result["tokens_in"]
                total_tokens_out += result["tokens_out"]
                status = "✓" if result["error"] is None and parsed else "✗"
                vv = parsed.get("verdict", "?") if parsed else "PARSE_ERR"
                print(
                    f"  {status} [idx={idx:2d}] {model.split('/')[-1]:30s} → {vv:12s} "
                    f"({result['tokens_in']}+{result['tokens_out']} tok, {dt:.1f}s)"
                )
                if result["error"]:
                    print(f"    error: {result['error'][:200]}")

    print(f"\nLayer 1 done. Tokens: in={total_tokens_in}, out={total_tokens_out}")
    if not smoke:
        summarize_layer1(out_file)


def summarize_layer1(results_file: Path) -> None:
    """Compute survivors: rows where <2 models judged KNOWN."""
    per_idx: dict[int, dict] = {}
    with open(results_file) as f:
        for line in f:
            r = json.loads(line)
            idx = r["idx"]
            if idx not in per_idx:
                per_idx[idx] = {
                    "idx": idx,
                    "a_name": r["a_name"],
                    "b_name": r["b_name"],
                    "verdicts": {},
                }
            per_idx[idx]["verdicts"][r["model"]] = r.get("verdict")

    survivors = []
    eliminated = []
    for idx, rec in sorted(per_idx.items()):
        verdicts = list(rec["verdicts"].values())
        known_count = sum(1 for v in verdicts if v == "KNOWN")
        if known_count >= 2:
            eliminated.append(rec)
        else:
            survivors.append(rec)

    survivors_file = VALIDATION_DIR / "layer1-survivors.jsonl"
    with open(survivors_file, "w") as f:
        for s in survivors:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\nLayer 1 summary:")
    print(f"  Total: {len(per_idx)}")
    print(f"  Eliminated (≥2 KNOWN): {len(eliminated)}")
    print(f"  Survivors → Layer 2:   {len(survivors)}")
    for s in survivors:
        print(f"    [{s['idx']:2d}] {s['a_name']} ↔ {s['b_name']}  verdicts={list(s['verdicts'].values())}")
    print(f"  Wrote: {survivors_file}")


# ========== Layer 2: Blind rating ==========

LAYER2_PROMPT_TEMPLATE = """评审下面这个跨域结构同构。不要问这是谁提出的，只看内容本身。

现象 A：{a_name}
现象 B：{b_name}
核心方程/机制：{equations}

回答三个问题，每题 1-5 分 + 一句话理由。

Q1 深层 vs 表面：
  1 = 仅因措辞或表面现象相似而显得同构
  5 = 数学形式或底层机制层面的严格同构

Q2 解释力：
  1 = 只是"看着像"，无助于理解
  5 = 能帮助理解 B 领域中原本难解的现象，或提供新的研究视角

Q3 预测力种子：
  1 = 只能事后解释，无法导出新预测
  5 = 能基于此同构生成至少一个"B 领域尚未验证但可证伪"的具体预测

关键要求：
- **不要输出分析过程，直接输出 JSON**
- **不要 markdown 代码块**
- 字符串内不要用反斜杠，LaTeX 请用纯文本

输出格式（严格遵守）：
{{
  "Q1": {{"score": 1-5, "reason": "..."}},
  "Q2": {{"score": 1-5, "reason": "..."}},
  "Q3": {{"score": 1-5, "reason": "..."}},
  "overall_novelty": "真新" 或 "表面新" 或 "疑似已知"
}}"""


def run_layer2(api_key: str, smoke: bool = False) -> None:
    survivors_file = VALIDATION_DIR / "layer1-survivors.jsonl"
    if not survivors_file.exists():
        print(f"ERROR: {survivors_file} not found. Run Layer 1 first.", file=sys.stderr)
        sys.exit(1)

    # Layer 1 survivors have {idx, a_name, b_name, verdicts}. Need to re-join with tier1-input for equations.
    tier1 = {r["_idx"]: r for r in load_tier1()}
    survivors = []
    with open(survivors_file) as f:
        for line in f:
            rec = json.loads(line)
            full = tier1.get(rec["idx"])
            if full:
                survivors.append(full)

    if smoke:
        survivors = survivors[:2]
        print(f"[smoke] using {len(survivors)} survivors")

    out_file = VALIDATION_DIR / ("layer2-results.smoke.jsonl" if smoke else "layer2-results.jsonl")

    done: set[tuple[int, str]] = set()
    if out_file.exists():
        with open(out_file) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    # only resume successful parses
                    if r.get("parsed") is not None:
                        done.add((r["idx"], r["model"]))
                except Exception:
                    pass
        print(f"Resume: {len(done)} existing successful results")

    total = len(survivors) * len(LAYER2_MODELS)
    remaining = total - len(done)
    print(f"Layer 2: {len(survivors)} survivors × {len(LAYER2_MODELS)} models = {total} calls ({remaining} remaining)")

    total_tokens_in = 0
    total_tokens_out = 0
    with open(out_file, "a") as f_out:
        for row in survivors:
            idx = row["_idx"]
            prompt = LAYER2_PROMPT_TEMPLATE.format(
                a_name=row["a_name"],
                b_name=row["b_name"],
                equations=row.get("equations", ""),
            )
            for model in LAYER2_MODELS:
                if (idx, model) in done:
                    continue
                t0 = time.time()
                result = call_openrouter(api_key, model, prompt, max_tokens=4000)
                dt = time.time() - t0
                parsed = extract_json(result["text"])
                scores = {}
                if parsed:
                    for q in ("Q1", "Q2", "Q3"):
                        v = parsed.get(q)
                        if isinstance(v, dict):
                            scores[q] = v.get("score")
                record = {
                    "idx": idx,
                    "a_name": row["a_name"],
                    "b_name": row["b_name"],
                    "model": model,
                    "raw_text": result["text"],
                    "parsed": parsed,
                    "scores": scores,
                    "tokens_in": result["tokens_in"],
                    "tokens_out": result["tokens_out"],
                    "elapsed": round(dt, 2),
                    "error": result["error"],
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()
                total_tokens_in += result["tokens_in"]
                total_tokens_out += result["tokens_out"]
                status = "✓" if result["error"] is None and parsed else "✗"
                scores_str = f"Q1={scores.get('Q1','?')}/Q2={scores.get('Q2','?')}/Q3={scores.get('Q3','?')}" if scores else "PARSE_ERR"
                print(
                    f"  {status} [idx={idx:2d}] {model.split('/')[-1]:30s} → {scores_str:25s} "
                    f"({result['tokens_in']}+{result['tokens_out']} tok, {dt:.1f}s)"
                )
                if result["error"]:
                    print(f"    error: {result['error'][:200]}")

    print(f"\nLayer 2 done. Tokens: in={total_tokens_in}, out={total_tokens_out}")
    if not smoke:
        summarize_layer2(out_file)


def summarize_layer2(results_file: Path) -> None:
    """Compute Layer 2 survivors: avg ≥12/15 and ≥3 models Q3 ≥4."""
    per_idx: dict[int, dict] = {}
    with open(results_file) as f:
        for line in f:
            r = json.loads(line)
            if not r.get("parsed"):
                continue
            idx = r["idx"]
            if idx not in per_idx:
                per_idx[idx] = {
                    "idx": idx,
                    "a_name": r["a_name"],
                    "b_name": r["b_name"],
                    "model_scores": {},
                }
            per_idx[idx]["model_scores"][r["model"]] = r.get("scores", {})

    survivors = []
    eliminated = []
    for idx, rec in sorted(per_idx.items()):
        # Average total score across models (only models with all 3 scores)
        totals = []
        q3_ge4 = 0
        for model, s in rec["model_scores"].items():
            if all(isinstance(s.get(q), (int, float)) for q in ("Q1", "Q2", "Q3")):
                totals.append(s["Q1"] + s["Q2"] + s["Q3"])
                if s["Q3"] >= 4:
                    q3_ge4 += 1
        if not totals:
            eliminated.append({"reason": "no valid scores", **rec})
            continue
        avg = sum(totals) / len(totals)
        rec["avg_total"] = round(avg, 2)
        rec["q3_ge4_count"] = q3_ge4
        rec["n_models"] = len(totals)
        if avg >= 12 and q3_ge4 >= 3:
            survivors.append(rec)
        else:
            eliminated.append(rec)

    out = VALIDATION_DIR / "layer2-survivors.jsonl"
    with open(out, "w") as f:
        for s in survivors:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\nLayer 2 summary:")
    print(f"  Total rated: {len(per_idx)}")
    print(f"  Survivors (avg≥12 & Q3≥4×3): {len(survivors)}")
    print(f"  Eliminated: {len(eliminated)}")
    for s in survivors:
        print(f"    [{s['idx']:2d}] {s['a_name']} ↔ {s['b_name']}  avg={s['avg_total']} q3≥4={s['q3_ge4_count']}/{s['n_models']}")
    print(f"  Wrote: {out}")


# ========== Layer 3: Prediction generation ==========

LAYER3_PROMPT_TEMPLATE = """基于下面这个已通过筛选的跨域结构同构，推理并生成 3 个候选"可证伪的新预测"。

现象 A：{a_name}
现象 B：{b_name}
核心方程/机制：{equations}

任务：
  A 领域中已知规律 X → 通过结构同构，应该在 B 领域预测出对应的 Y。
  请给出 3 个候选 Y。

严格要求（每个候选 Y 都必须满足）：
1. **可观测/可实验**：Y 必须是具体命题，能说清如何观测或测量
2. **非平凡**：Y 必须是"如果没有这个跨域同构就不会被预测出来"的（排除平凡预测，例如"B 领域中某物会增加"这种没信息量的命题）
3. **可证伪**：必须能说清"什么情况下 Y 被证伪"

按"新奇度 × 可证伪性"从高到低排序。

要求：
- 不要分析过程，直接输出 JSON
- 不要 markdown 代码块
- 字符串内不要用反斜杠

输出格式：
{{
  "predictions": [
    {{
      "id": "P1",
      "statement": "B 领域中具体的可观测命题...",
      "derivation": "从 A 的哪条规律/机制，通过哪个同构映射，推出 Y 的",
      "observability": "如何观测或测量 Y",
      "falsifier": "什么情况下 Y 被证伪",
      "novelty_score": 1-5,
      "falsifiability_score": 1-5
    }},
    {{...}},
    {{...}}
  ]
}}"""


def run_layer3(api_key: str, smoke: bool = False) -> None:
    survivors_file = VALIDATION_DIR / "layer2-survivors.jsonl"
    if not survivors_file.exists():
        print(f"ERROR: {survivors_file} not found. Run Layer 2 first.", file=sys.stderr)
        sys.exit(1)

    tier1 = {r["_idx"]: r for r in load_tier1()}
    survivors = []
    with open(survivors_file) as f:
        for line in f:
            rec = json.loads(line)
            full = tier1.get(rec["idx"])
            if full:
                survivors.append(full)

    if smoke:
        survivors = survivors[:1]

    out_file = VALIDATION_DIR / ("layer3-predictions.smoke.jsonl" if smoke else "layer3-predictions.jsonl")
    done: set[int] = set()
    if out_file.exists():
        with open(out_file) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get("parsed"):
                        done.add(r["idx"])
                except Exception:
                    pass

    print(f"Layer 3: {len(survivors)} survivors × 1 model (Opus) = {len(survivors) - len(done)} remaining calls")

    with open(out_file, "a") as f_out:
        for row in survivors:
            idx = row["_idx"]
            if idx in done:
                continue
            prompt = LAYER3_PROMPT_TEMPLATE.format(
                a_name=row["a_name"],
                b_name=row["b_name"],
                equations=row.get("equations", ""),
            )
            t0 = time.time()
            result = call_openrouter(api_key, LAYER3_MODEL, prompt, max_tokens=6000)
            dt = time.time() - t0
            parsed = extract_json(result["text"])
            record = {
                "idx": idx,
                "a_name": row["a_name"],
                "b_name": row["b_name"],
                "equations": row.get("equations", ""),
                "model": LAYER3_MODEL,
                "raw_text": result["text"],
                "parsed": parsed,
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "elapsed": round(dt, 2),
                "error": result["error"],
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            f_out.flush()
            n_pred = len(parsed.get("predictions", [])) if parsed else 0
            status = "✓" if parsed else "✗"
            print(f"  {status} [idx={idx:2d}] {row['a_name']} ↔ {row['b_name']}  {n_pred} predictions ({result['tokens_in']}+{result['tokens_out']} tok, {dt:.1f}s)")
            if result["error"]:
                print(f"    error: {result['error'][:200]}")

    if not smoke:
        render_layer3_markdown(out_file)


def render_layer3_markdown(results_file: Path) -> None:
    """Render Layer 3 predictions to human-review markdown."""
    out = VALIDATION_DIR / "predictions.md"
    lines = ["# Layer 3 预测力测试结果", "", "> 对 Layer 2 幸存的发现生成 3 个候选可证伪预测。", "> 用户 + Scholar 搜索逐条审核。", ""]
    with open(results_file) as f:
        for line in f:
            r = json.loads(line)
            lines.append(f"## [idx={r['idx']}] {r['a_name']} ↔ {r['b_name']}")
            lines.append("")
            lines.append(f"**核心机制**：{r.get('equations', '')}")
            lines.append("")
            parsed = r.get("parsed") or {}
            for p in parsed.get("predictions", []):
                lines.append(f"### {p.get('id', '?')}: {p.get('statement', '')}")
                lines.append("")
                lines.append(f"- **推导**：{p.get('derivation', '')}")
                lines.append(f"- **可观测性**：{p.get('observability', '')}")
                lines.append(f"- **证伪条件**：{p.get('falsifier', '')}")
                lines.append(f"- **新奇度**：{p.get('novelty_score', '?')}/5  **可证伪性**：{p.get('falsifiability_score', '?')}/5")
                lines.append("")
                lines.append("**人工评审**（填写）：")
                lines.append("- [ ] 已被验证（附引用）")
                lines.append("- [ ] 部分被验证")
                lines.append("- [ ] 未被验证，值得立项 / 开放预测")
                lines.append("- [ ] 评审备注：")
                lines.append("")
            lines.append("---")
            lines.append("")
    out.write_text("\n".join(lines))
    print(f"  Wrote: {out}")


# ========== Main ==========

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", type=int, required=True, choices=[1, 2, 3])
    parser.add_argument("--smoke", action="store_true", help="smoke test with 2 rows")
    parser.add_argument("--summary", action="store_true", help="re-run summary only")
    args = parser.parse_args()

    VALIDATION_DIR.mkdir(exist_ok=True)
    api_key = load_env()
    if not INPUT_FILE.exists():
        print(f"ERROR: input file not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    if args.summary and args.layer == 1:
        summarize_layer1(VALIDATION_DIR / "layer1-results.jsonl")
        return

    if args.layer == 1:
        run_layer1(api_key, smoke=args.smoke)
    elif args.layer == 2:
        run_layer2(api_key, smoke=args.smoke)
    elif args.layer == 3:
        run_layer3(api_key, smoke=args.smoke)


if __name__ == "__main__":
    main()
