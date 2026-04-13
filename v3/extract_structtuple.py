"""
V3 Phase 0: Extract StructTuple for a small sample.
Calls OpenRouter with Kimi (cheap) or Opus (quality) for each phenomenon.
"""
import json
import os
import sys
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

PROJECT = Path(__file__).parent.parent
KB_FILE = PROJECT / "data" / "kb-expanded.jsonl"
PROMPT_FILE = Path(__file__).parent / "extract_prompt.txt"

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    sys.exit("OPENROUTER_API_KEY not set")

MODELS = {
    "kimi": "moonshotai/kimi-k2-0905",
    "opus": "anthropic/claude-opus-4",
    "deepseek": "deepseek/deepseek-r1",
    "minimax": "minimax/minimax-m2",
}


def call_openrouter(model_id: str, prompt: str, timeout: int = 60) -> str:
    req_body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(req_body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://structural.bytedance.city",
            "X-Title": "structural-isomorphism-v3",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def clean_json(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def extract_one(phenomenon: dict, prompt_template: str, model_id: str) -> dict:
    user_input = (
        f"ID: {phenomenon.get('id', '')}\n"
        f"名称: {phenomenon.get('name', '')}\n"
        f"领域: {phenomenon.get('domain', '')}\n"
        f"描述: {phenomenon.get('description', '')}\n"
    )
    prompt = prompt_template + user_input + "\n\n输出（只输出 JSON，不要 markdown）："
    raw = call_openrouter(model_id, prompt)
    cleaned = clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        return {
            "_error": f"json_decode: {e}",
            "_raw": raw[:500],
            "phenomenon_id": phenomenon.get("id", ""),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODELS.keys()), default="kimi")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--random", action="store_true", help="sample randomly")
    ap.add_argument("--input", type=str, default=None, help="custom input jsonl (overrides KB)")
    ap.add_argument("--resume", action="store_true", help="skip IDs already in output")
    args = ap.parse_args()

    import random

    random.seed(args.seed)
    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")

    input_file = Path(args.input) if args.input else KB_FILE
    with open(input_file) as f:
        kb = [json.loads(line) for line in f if line.strip()]

    if args.random:
        samples = random.sample(kb, min(args.n, len(kb)))
    elif args.input:
        samples = kb  # use all from shard
    else:
        samples = kb[: args.n]

    # Resume support: skip IDs already present in output
    done_ids = set()
    if args.resume and args.out and Path(args.out).exists():
        with open(args.out) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    pid = d.get("phenomenon_id")
                    if pid and "_error" not in d:
                        done_ids.add(pid)
                except Exception:
                    pass
        if done_ids:
            before = len(samples)
            samples = [p for p in samples if p.get("id") not in done_ids]
            print(f"Resume: skipping {before - len(samples)} already done, {len(samples)} to go")

    out_path = Path(args.out) if args.out else (
        Path(__file__).parent / f"sample-{args.model}-{args.n}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    model_id = MODELS[args.model]
    print(f"Model: {model_id}  samples: {len(samples)}  out: {out_path}")

    ok = 0
    err = 0
    start = time.time()
    open_mode = "a" if args.resume else "w"
    with open(out_path, open_mode) as f:
        for i, p in enumerate(samples, 1):
            t0 = time.time()
            result = extract_one(p, prompt_template, model_id)
            dt = time.time() - t0
            if "_error" in result:
                err += 1
                print(f"  [{i}/{len(samples)}] ERR  {p['id']}: {result['_error']}")
            else:
                ok += 1
                df = result.get("dynamics_family", "?")
                print(f"  [{i}/{len(samples)}] OK   {p['id']:<10} {dt:.1f}s  {df:<30} {p['name']}")
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()

    elapsed = time.time() - start
    print(f"\nDone. ok={ok} err={err} elapsed={elapsed:.1f}s ({elapsed/len(samples):.1f}s per item)")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
