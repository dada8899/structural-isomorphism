"""Q2 labeling script — call OpenRouter models to label 20 classic cases."""
import json
import os
import sys
import time
import urllib.request

CASES_FILE = "/Users/wanqh/Projects/structural-isomorphism/v4-feasibility/q2-classic-cases.jsonl"
PRIMITIVES_FILE = "/Users/wanqh/Projects/structural-isomorphism/v4-feasibility/transformation-primitives.md"

API_KEY = os.environ["OPENROUTER_API_KEY"]

PROMPT_TMPL = """You are labeling transformation primitives for a cross-domain analogy study.

# 8 Transformation Primitives

1. **variable_rename** — Same math, only symbols/units change. E.g., thermodynamic entropy (J/K) → Shannon entropy (bits). Apply only when literally nothing but naming changes.
2. **concept_transfer** — Replace a physical quantity with a structurally analogous one. E.g., mass → inductance when mapping mechanics to LC circuits. Reinterpretation, not renaming.
3. **causal_inversion** — Swap cause/effect direction or flip what's driving what.
4. **continuity_toggle** — Continuous ↔ discrete formulation switch (ODE → cellular automaton, wave → particle).
5. **boundary_rewrite** — Change boundary conditions, topology, domain. Open → closed, infinite → finite.
6. **dim_shift** — Change effective dimensionality (2D → 3D, add Kaluza-Klein dim, point → field).
7. **stochastic_toggle** — Add or remove randomness (deterministic ODE → Gillespie stochastic sim).
8. **time_scaling** — Change time scale or regime (equilibrium → non-equilibrium, fast → slow variables).

# Your task

Label the following historical transfer with the MINIMAL set of primitives that captures what transformation happened between the source and target. Apply each only when it genuinely fits. Empty list is OK.

Strict rules:
- `variable_rename` ONLY if literally just symbols/units change (no conceptual reinterpretation)
- If a reinterpretation happens, prefer `concept_transfer`
- `dim_shift` only if effective dimensionality changed
- Return ONLY a valid JSON object, no markdown, no explanation outside JSON

# Input

ID: {id}
Source: {source_name} ({source_domain})
Target: {target_name} ({target_domain})
Description: {description}

# Output schema

{{"id": "{id}", "primitives": ["list", "of", "primitive", "ids"], "primitive_reasons": {{"primitive_id": "brief why"}}, "confidence": 0.0-1.0, "notes": "optional"}}

Return the JSON now:"""


def call_model(model_id: str, prompt: str, max_retries: int = 3) -> str:
    req_body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 800,
    }
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(req_body).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://structural.bytedance.city",
                    "X-Title": "v4-feasibility",
                },
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return ""


def clean_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text.strip())


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 q2_annotate.py <model_id> <output_file>")
        sys.exit(1)
    model_id = sys.argv[1]
    out_path = sys.argv[2]

    cases = []
    with open(CASES_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    print(f"Model: {model_id}  cases: {len(cases)}  out: {out_path}")

    results = []
    for i, c in enumerate(cases, 1):
        prompt = PROMPT_TMPL.format(**c)
        t0 = time.time()
        try:
            raw = call_model(model_id, prompt)
            parsed = clean_json(raw)
            parsed["_model"] = model_id
            dt = time.time() - t0
            prims = parsed.get("primitives", [])
            print(f"  [{i}/{len(cases)}] {c['id']} {dt:4.1f}s  {prims}")
            results.append(parsed)
        except Exception as e:
            print(f"  [{i}/{len(cases)}] ERR {c['id']}: {e}")
            results.append({"id": c["id"], "_error": str(e), "_model": model_id})

    with open(out_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
