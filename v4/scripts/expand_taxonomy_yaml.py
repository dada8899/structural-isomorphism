#!/usr/bin/env python3
"""Expand v4/taxonomy/classes/*.yaml with LLM-generated negative_examples +
edge_cases for each class.

Motivation: the existing class yamls list positive_examples (members) richly
but negative_examples and edge_cases unevenly. A broader, deliberately-
chosen set of (a) negative examples ("looks like this class but isn't") and
(b) edge cases ("genuinely ambiguous, deserves debate") tightens the class
boundary and helps both human and LLM reviewers in B3/B4 distinguish the
class from neighbours.

For each yaml class, call DeepSeek with the existing class definition
(shared equation, key invariants, positive examples) and ask for:
  - 3-5 negative_examples (with reason)
  - 3-5 edge_cases (with debate description)

The script then re-writes the yaml IN PLACE while preserving all original
fields. Existing negative_examples + edge_cases are MERGED with the new
ones, deduped by phenomenon-name match.

CLI:
  python3 v4/scripts/expand_taxonomy_yaml.py [--dry-run] [--limit N] [class_id...]

  --dry-run        : load + prompt-build only; no API calls
  --limit N        : process first N classes only (defaults to all)
  class_id args    : optional explicit class ids to expand (overrides --limit)

Safety:
  - --dry-run is the default sane mode.
  - Without --dry-run, the script makes API calls billed to DEEPSEEK_API_KEY.
  - Each class costs ~1 API call (~$0.001-0.005 depending on prompt size).
  - 24 classes ~= 24 calls ~= ~$0.05-0.10 total.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
YAML_DIR = REPO / "v4" / "taxonomy" / "classes"
DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"


def _load_dotenv() -> None:
    env_path = REPO / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")

# ---------------------------------------------------------------------------
# Prompt template

EXPAND_PROMPT = """You are an expert in universality classes and cross-domain dynamical systems. You are reviewing the boundary of a candidate universality class for the structural-isomorphism v4 taxonomy project.

Current class definition (excerpted from its yaml):

class_id: {class_id}
display_name: {display_name}
hub_phenomenon: {hub}
shared_equation:
{shared_eq}

key_invariants:
{invariants}

positive_examples (known members):
{positives}

existing_negative_examples (already in yaml):
{existing_negatives}

existing_edge_cases (already in yaml):
{existing_edge_cases}

Your task: propose ADDITIONAL negative examples and edge cases that would sharpen the class boundary. Focus on systems that:
  - LOOK like this class superficially (e.g. similar exponent, similar shape) but have an INCOMPATIBLE mechanism;
  - sit GENUINELY ambiguously on the boundary (deserve a separate debate);
  - are commonly CONFUSED with this class in the literature.

Do NOT repeat the existing entries.

Output JSON only, in this exact schema:
{{
  "negative_examples": [
    {{"phenomenon": "<short name>", "reason": "<1-2 sentences why this looks similar but is NOT a member of {class_id}; cite mechanism or equation form>"}},
    ...  (3-5 entries)
  ],
  "edge_cases": [
    {{"phenomenon": "<short name>", "debate": "<1-2 sentences on why this is genuinely ambiguous; cite the contested mechanism or boundary>"}},
    ...  (3-5 entries)
  ]
}}

Output ONLY the JSON object, no preamble or explanation outside the JSON.
"""


# ---------------------------------------------------------------------------
# Yaml read/write (minimal, preserving non-target keys)


def read_yaml_raw(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_yaml_field(text: str, field: str) -> str:
    """Extract a single yaml field's raw value (best-effort, simple regex)."""
    # Match: ^field: value\n
    m = re.search(rf"^{re.escape(field)}:[ \t]*(.*)$", text, flags=re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip()


def extract_yaml_block(text: str, field: str) -> str:
    """Extract a yaml block-scalar (key: | ...) value."""
    lines = text.splitlines()
    out: list[str] = []
    in_block = False
    for ln in lines:
        if not in_block:
            if ln.startswith(f"{field}:"):
                rest = ln.split(":", 1)[1].strip()
                if rest in ("|", ">"):
                    in_block = True
        else:
            if ln.startswith("  ") or ln.strip() == "":
                out.append(ln[2:] if ln.startswith("  ") else ln)
            else:
                break
    return "\n".join(out).strip()


def extract_yaml_list_simple(text: str, field: str) -> list[str]:
    """Extract a simple top-level list (key: \n  - x \n  - y)."""
    lines = text.splitlines()
    out: list[str] = []
    found = False
    for ln in lines:
        if not found:
            if ln.startswith(f"{field}:") and ln.split(":", 1)[1].strip() == "":
                found = True
        else:
            if ln.startswith("  - "):
                out.append(ln[4:].strip().strip('"'))
            elif ln.startswith("  "):
                continue
            else:
                break
    return out


def extract_positives(text: str) -> list[str]:
    """positive_examples is a list of dicts with 'phenomenon' key. Pull those."""
    lines = text.splitlines()
    out: list[str] = []
    found = False
    for ln in lines:
        if not found:
            if ln.startswith("positive_examples:"):
                found = True
        else:
            if ln.startswith("  - phenomenon:"):
                out.append(ln.split(":", 1)[1].strip().strip('"'))
            elif ln.startswith("  - ") or ln.startswith("    "):
                continue
            elif ln.startswith("  "):
                continue
            else:
                break
    return out


def extract_negative_phenomena(text: str, field: str = "negative_examples") -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    found = False
    for ln in lines:
        if not found:
            if ln.startswith(f"{field}:"):
                found = True
        else:
            if ln.startswith("  - phenomenon:"):
                out.append(ln.split(":", 1)[1].strip().strip('"'))
            elif ln.startswith("  - ") or ln.startswith("    "):
                continue
            elif ln.startswith("  "):
                continue
            else:
                break
    return out


# ---------------------------------------------------------------------------
# DeepSeek API


def call_deepseek(prompt: str) -> tuple[str | None, str | None]:
    if not DEEPSEEK_KEY:
        return None, "DEEPSEEK_API_KEY not set"
    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {
                "role": "system",
                "content": "You are an expert in universality classes and dynamical systems. Output JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        # deepseek-v4-pro uses reasoning_tokens internally; budget generously
        # so the visible content message has room after reasoning. Empirically
        # 8000 leaves ~6000 for content even after dense reasoning.
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        DEEPSEEK_BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content", "") or ""
        return content.strip(), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"
    except Exception as e:  # pragma: no cover
        return None, f"{type(e).__name__}: {e}"


def extract_json(raw: str) -> dict | None:
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1]
        if s.endswith("```"):
            s = s[:-3].rstrip()
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j < 0 or j <= i:
        return None
    candidate = s[i : j + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = candidate.replace(",\n}", "\n}").replace(",\n]", "\n]")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Yaml writer (append-only block for negative_examples + edge_cases)


def _escape_yaml_string(s: str) -> str:
    """Wrap in double quotes if special chars; otherwise return as-is."""
    if not s:
        return '""'
    if any(c in s for c in ":#&*?{}[]|,'\"\\"):
        # escape backslash + double quote
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def render_negative_examples_block(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    lines = ["negative_examples:"]
    for it in items:
        ph = it.get("phenomenon", "")
        reason = it.get("reason", "")
        lines.append(f"- phenomenon: {_escape_yaml_string(ph)}")
        lines.append(f"  reason: {_escape_yaml_string(reason)}")
    # 2-space indent for top-level list items per existing yaml convention
    out = lines[0] + "\n" + "\n".join(f"  {l}" if l.startswith("- ") or l.startswith("  ") else l for l in lines[1:])
    return out + "\n"


def render_edge_cases_block(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    lines = ["edge_cases:"]
    for it in items:
        ph = it.get("phenomenon", "")
        debate = it.get("debate", "")
        lines.append(f"- phenomenon: {_escape_yaml_string(ph)}")
        lines.append(f"  debate: {_escape_yaml_string(debate)}")
    out = lines[0] + "\n" + "\n".join(f"  {l}" if l.startswith("- ") or l.startswith("  ") else l for l in lines[1:])
    return out + "\n"


def merge_into_yaml(yaml_text: str, new_negatives: list[dict], new_edges: list[dict]) -> str:
    """Merge new negative_examples + edge_cases into existing yaml text.

    Strategy (conservative, preserves existing block exactly when nothing to
    add): for each block, if it exists and an item with the same
    'phenomenon' key is already present, skip; otherwise append at the end
    of the block. If the block doesn't exist, append a new block before the
    'notes:' field (or at end of file if no notes field).
    """
    existing_neg_names = {x.lower() for x in extract_negative_phenomena(yaml_text, "negative_examples")}
    existing_edge_names = {x.lower() for x in extract_negative_phenomena(yaml_text, "edge_cases")}

    add_negatives = [
        n for n in new_negatives
        if n.get("phenomenon", "").lower() not in existing_neg_names and n.get("phenomenon")
    ]
    add_edges = [
        e for e in new_edges
        if e.get("phenomenon", "").lower() not in existing_edge_names and e.get("phenomenon")
    ]

    if not add_negatives and not add_edges:
        return yaml_text  # nothing to add

    lines = yaml_text.splitlines(keepends=True)
    out_lines: list[str] = []
    handled_neg = not bool(add_negatives)
    handled_edge = not bool(add_edges)

    i = 0
    while i < len(lines):
        ln = lines[i]
        # find end of negative_examples block
        if not handled_neg and ln.startswith("negative_examples:"):
            out_lines.append(ln)
            i += 1
            # passthrough existing block
            while i < len(lines) and (
                lines[i].startswith("- ") or lines[i].startswith("  ") or lines[i].strip() == ""
            ):
                out_lines.append(lines[i])
                i += 1
            # append new entries
            for it in add_negatives:
                out_lines.append(f"- phenomenon: {_escape_yaml_string(it['phenomenon'])}\n")
                out_lines.append(f"  reason: {_escape_yaml_string(it.get('reason', ''))}\n")
            handled_neg = True
            continue
        if not handled_edge and ln.startswith("edge_cases:"):
            out_lines.append(ln)
            i += 1
            while i < len(lines) and (
                lines[i].startswith("- ") or lines[i].startswith("  ") or lines[i].strip() == ""
            ):
                out_lines.append(lines[i])
                i += 1
            for it in add_edges:
                out_lines.append(f"- phenomenon: {_escape_yaml_string(it['phenomenon'])}\n")
                out_lines.append(f"  debate: {_escape_yaml_string(it.get('debate', ''))}\n")
            handled_edge = True
            continue
        out_lines.append(ln)
        i += 1

    text = "".join(out_lines)
    # If negative_examples block did not exist, append a new block.
    if not handled_neg:
        text = _append_block_before_notes(text, render_negative_examples_block(add_negatives))
    if not handled_edge:
        text = _append_block_before_notes(text, render_edge_cases_block(add_edges))
    return text


def _append_block_before_notes(text: str, block: str) -> str:
    if not block.strip():
        return text
    idx = text.find("\nnotes:")
    if idx < 0:
        # append at end
        if not text.endswith("\n"):
            text += "\n"
        return text + block
    return text[: idx + 1] + block + text[idx + 1 :]


# ---------------------------------------------------------------------------
# Per-class processing


def build_prompt_for_class(class_id: str, yaml_text: str) -> str:
    display_name = extract_yaml_field(yaml_text, "display_name") or class_id
    hub = extract_yaml_field(yaml_text, "hub_phenomenon")
    shared_eq = extract_yaml_block(yaml_text, "shared_equation")[:800]
    invariants = extract_yaml_list_simple(yaml_text, "key_invariants")
    positives = extract_positives(yaml_text)
    existing_negs = extract_negative_phenomena(yaml_text, "negative_examples")
    existing_edges = extract_negative_phenomena(yaml_text, "edge_cases")

    inv_block = "\n".join(f"- {x}" for x in invariants[:8]) or "(none)"
    pos_block = "\n".join(f"- {x}" for x in positives[:8]) or "(none)"
    neg_block = "\n".join(f"- {x}" for x in existing_negs) or "(none)"
    edge_block = "\n".join(f"- {x}" for x in existing_edges) or "(none)"

    return EXPAND_PROMPT.format(
        class_id=class_id,
        display_name=display_name[:200],
        hub=hub[:400],
        shared_eq=shared_eq,
        invariants=inv_block,
        positives=pos_block,
        existing_negatives=neg_block,
        existing_edge_cases=edge_block,
    )


def process_class(class_id: str, dry_run: bool) -> dict[str, Any]:
    """Returns summary dict: {class_id, status, added_negatives, added_edges, error}."""
    path = YAML_DIR / f"{class_id}.yaml"
    if not path.exists():
        return {"class_id": class_id, "status": "MISSING_YAML"}
    text = path.read_text(encoding="utf-8")
    prompt = build_prompt_for_class(class_id, text)
    if dry_run:
        return {
            "class_id": class_id,
            "status": "DRY_RUN",
            "prompt_len": len(prompt),
        }
    raw, err = call_deepseek(prompt)
    if raw is None:
        return {"class_id": class_id, "status": "API_ERROR", "error": err}
    parsed = extract_json(raw)
    if parsed is None:
        return {
            "class_id": class_id,
            "status": "PARSE_FAIL",
            "raw_excerpt": raw[:200],
        }
    new_neg = parsed.get("negative_examples", []) or []
    new_edge = parsed.get("edge_cases", []) or []
    if not isinstance(new_neg, list):
        new_neg = []
    if not isinstance(new_edge, list):
        new_edge = []
    merged = merge_into_yaml(text, new_neg, new_edge)
    if merged != text:
        path.write_text(merged, encoding="utf-8")
    return {
        "class_id": class_id,
        "status": "UPDATED" if merged != text else "NO_CHANGE",
        "added_negatives": len(new_neg),
        "added_edges": len(new_edge),
    }


# ---------------------------------------------------------------------------
# Main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Expand taxonomy yamls with LLM-generated negative_examples + edge_cases."
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Build prompts only; no API calls."
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process first N classes only (sorted yaml order).",
    )
    ap.add_argument(
        "classes", nargs="*", help="Explicit class ids (overrides --limit)."
    )
    args = ap.parse_args()

    if args.classes:
        targets = args.classes
    else:
        all_yamls = sorted(p.stem for p in YAML_DIR.glob("*.yaml"))
        targets = all_yamls[: args.limit] if args.limit > 0 else all_yamls

    print(f"[expand] {len(targets)} class(es) to process", file=sys.stderr)
    if args.dry_run:
        print("[expand] DRY_RUN mode (no API calls)", file=sys.stderr)
    if not args.dry_run and not DEEPSEEK_KEY:
        print(
            "[expand] FATAL: DEEPSEEK_API_KEY not set. Export it or place in .env.",
            file=sys.stderr,
        )
        return 1

    results = []
    t_start = time.time()
    for ci, class_id in enumerate(targets, 1):
        print(f"[expand] [{ci}/{len(targets)}] {class_id}", file=sys.stderr)
        t0 = time.time()
        out = process_class(class_id, args.dry_run)
        out["elapsed_s"] = round(time.time() - t0, 1)
        results.append(out)
        status = out.get("status", "?")
        if status in ("UPDATED", "NO_CHANGE"):
            print(
                f"  -> {status}  neg+{out.get('added_negatives', 0)} edge+{out.get('added_edges', 0)}",
                file=sys.stderr,
            )
        elif status == "DRY_RUN":
            print(f"  -> DRY_RUN  prompt_len={out.get('prompt_len', 0)}", file=sys.stderr)
        else:
            print(f"  -> {status}  {out.get('error') or out.get('raw_excerpt', '')}", file=sys.stderr)

    elapsed = time.time() - t_start
    n_updated = sum(1 for r in results if r.get("status") == "UPDATED")
    n_nochange = sum(1 for r in results if r.get("status") == "NO_CHANGE")
    n_error = sum(
        1 for r in results if r.get("status") in ("API_ERROR", "PARSE_FAIL", "MISSING_YAML")
    )
    print(
        f"\n[expand] Done: {n_updated} updated, {n_nochange} no-change, "
        f"{n_error} error in {elapsed / 60:.1f} min",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
