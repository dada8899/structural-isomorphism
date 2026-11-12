"""
V3 variant-type coverage regression test.

Take the 9 Layer 2 survivors as test set.
For each, ask Opus to annotate which of the 7 variant types (from v4-variant-types.yaml)
are used in mapping A's mechanism to B. Flag any discovery whose variant path
cannot be covered by the 7 primitives.

If <80% of survivors can be covered → expand the primitive set.

Usage:
    python v4_coverage_check.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yaml
import httpx

PROJECT_DIR = Path(__file__).parent.parent
VALIDATION_DIR = PROJECT_DIR / "validation"
PLANS_DIR = PROJECT_DIR / "plans"
ENV_FILE = PROJECT_DIR / "web" / "backend" / ".env"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-opus-4.1"


def load_api_key() -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("OPENROUTER_API_KEY not found")


def load_variant_types() -> list[dict]:
    with open(PLANS_DIR / "v4-variant-types.yaml") as f:
        data = yaml.safe_load(f)
    return data["types"]


def load_survivors() -> list[dict]:
    tier1 = {r["_idx"]: r for r in (json.loads(l) for l in open(VALIDATION_DIR / "tier1-input.jsonl"))}
    out = []
    with open(VALIDATION_DIR / "layer2-survivors.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            full = tier1.get(rec["idx"])
            if full:
                out.append(full)
    return out


def call_opus(api_key: str, prompt: str) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 3000,
    }
    with httpx.Client(timeout=120.0, trust_env=False) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()


def extract_json(text: str) -> dict | None:
    import re
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        t = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1:
        return None
    raw = t[s : e + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # relaxed escape fix
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
        try:
            return json.loads(fixed)
        except Exception:
            return None


PROMPT = """你正在为"跨域结构同构求解器"标注变形基元。

我会给你一个发现：A 领域的机制 X 与 B 领域的机制 Y 在结构上同构。
任务：判断把 A 的机制/解法搬到 B 领域，需要用到哪些"变形基元"。

可用的 7 种变形基元：

{variant_catalog}

发现：
A 领域：{a_name}
B 领域：{b_name}
核心方程/机制：{equations}

输出严格 JSON（不要 markdown，不要解释过程，字符串里不要用反斜杠）：

{{
  "required_variants": ["id1", "id2", ...],
  "covered_by_7": true 或 false,
  "uncovered_aspects": "如果 covered_by_7=false，说明 7 种基元里没有但必需的变形类型（用简短短语）",
  "rationale": "一句话说明变形路径"
}}

注意：
- required_variants 用基元的 id（如 "dim_subst"）
- 如果所有必需变形都能被 7 种之一覆盖，covered_by_7=true
- 如果存在必需但不在 7 种里的变形，covered_by_7=false 并在 uncovered_aspects 里描述
"""


def main():
    api_key = load_api_key()
    variants = load_variant_types()
    survivors = load_survivors()

    catalog = "\n".join(f"- `{v['id']}` ({v['name']}): {v['description']}" for v in variants)

    out_file = VALIDATION_DIR / "v3-coverage-check.jsonl"
    print(f"V3 Coverage: {len(survivors)} survivors × 1 model (Opus)")

    results = []
    with open(out_file, "w") as f_out:
        for row in survivors:
            prompt = PROMPT.format(
                variant_catalog=catalog,
                a_name=row["a_name"],
                b_name=row["b_name"],
                equations=row.get("equations", ""),
            )
            t0 = time.time()
            try:
                data = call_opus(api_key, prompt)
                text = data["choices"][0]["message"].get("content") or ""
                parsed = extract_json(text)
            except Exception as e:
                text, parsed = "", None
                print(f"  ✗ [idx={row['_idx']:2d}] error: {e}")
                continue
            dt = time.time() - t0

            rec = {
                "idx": row["_idx"],
                "a_name": row["a_name"],
                "b_name": row["b_name"],
                "parsed": parsed,
                "raw_text": text,
                "elapsed": round(dt, 2),
            }
            results.append(rec)
            f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f_out.flush()

            if parsed:
                v_used = ",".join(parsed.get("required_variants", []))
                cov = "✓" if parsed.get("covered_by_7") else "✗"
                print(f"  {cov} [idx={row['_idx']:2d}] {row['a_name'][:20]:20s} ↔ {row['b_name'][:20]:20s}  variants=[{v_used}]  ({dt:.1f}s)")
                if not parsed.get("covered_by_7"):
                    print(f"       uncovered: {parsed.get('uncovered_aspects', '')}")
            else:
                print(f"  ? [idx={row['_idx']:2d}] parse error")

    # Summary
    covered = sum(1 for r in results if r["parsed"] and r["parsed"].get("covered_by_7"))
    total = len(results)
    pct = (covered / total * 100) if total else 0
    print(f"\nCoverage: {covered}/{total} = {pct:.0f}%")

    if pct < 80:
        print("⚠️  Coverage below 80% threshold — expand primitive set.")
        print("Missing aspects:")
        for r in results:
            if r["parsed"] and not r["parsed"].get("covered_by_7"):
                print(f"  [{r['idx']}] {r['parsed'].get('uncovered_aspects', '')}")
    else:
        print("✓ 7 primitives cover ≥80% of survivors. Proceed with training data construction.")

    # Count primitive usage
    from collections import Counter
    usage = Counter()
    for r in results:
        if r["parsed"]:
            for v in r["parsed"].get("required_variants", []):
                usage[v] += 1
    print(f"\nPrimitive usage frequency:")
    for v, n in usage.most_common():
        print(f"  {v:20s} {n}")


if __name__ == "__main__":
    main()
