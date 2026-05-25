#!/usr/bin/env python3
"""Rewrite Wave 3 C long-tail boilerplate suffixes via DeepSeek.

Background
----------
`docs/audit/2026-05-25-kb-data-audit.md` §D.6 identified ~117/300 entries
in `data/kb-additions-2026-05-25-long-tail-batch.jsonl` whose descriptions
end with one of 6 fixed padding templates (50+ chars) shared across many
entries in the same domain. These pollute embedding retrieval because
co-occurring padding inflates intra-domain similarity.

Fix path (a) per audit: LLM-rewrite the padded tail with concrete
mechanism-relevant content (measurement quantities, validation
references). Keep the original head (the substantive lead-in).

Pipeline
--------
1. Load .env (DEEPSEEK_API_KEY)
2. Load 117 flagged IDs from /tmp/wave3c_flagged_ids.json
3. Load long-tail batch additions
4. For each flagged entry:
   a. Identify boilerplate region (substring match)
   b. Split description: head (substantive) + tail (padding)
   c. Prompt DeepSeek to rewrite the tail with domain-specific content
   d. 3-layer validation: length, no boilerplate, has author+year ref
5. Write back additions file (.bak preserved)
6. Cascade update master KB 5333 (with .archive backup)

Usage
-----
    .venv/bin/python scripts/rewrite_wave3c_boilerplate.py --smoke    # 1 call
    .venv/bin/python scripts/rewrite_wave3c_boilerplate.py --batch 5  # first 5
    .venv/bin/python scripts/rewrite_wave3c_boilerplate.py --all      # 117
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
load_dotenv(REPO / ".env")

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
if not API_KEY:
    sys.exit("ERROR: DEEPSEEK_API_KEY not set in .env or env")

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

ADDITIONS_FILE = REPO / "data" / "kb-additions-2026-05-25-long-tail-batch.jsonl"
MASTER_KB = REPO / "data" / "kb-5000-merged.jsonl"

def identify_flagged_ids() -> set[str]:
    """Scan additions file for entries with boilerplate suffix patterns.
    Inline replacement for /tmp/wave3c_flagged_ids.json — keeps script
    self-contained and reproducible across machines.

    NOTE: we deliberately check only the structural boilerplate suffixes,
    not the loose substring markers (which may also appear in legitimate
    mechanism content in the head). This makes the script idempotent:
    after --apply, flagged_ids returns empty.
    """
    rows = [json.loads(l) for l in open(ADDITIONS_FILE)]
    flagged: set[str] = set()
    for r in rows:
        d = r.get("description", "")
        for pattern in BOILERPLATE_PATTERNS:
            if pattern in d or pattern[-40:] in d:
                flagged.add(r["id"])
                break
    return flagged

# 6 boilerplate suffix templates from audit §D.6
BOILERPLATE_PATTERNS = [
    "NICE等机构定期更新指南。低中收入国(LMIC)与高收入国(HIC)实施挑战不同，需上下文化策略。",
    "学(MRI/CT/超声)综合判断。治疗策略涵盖激素替代、受体调节、外科切除与靶向药物，需个体化方案。",
    "array等手段，DNS/LES数值模拟提供精细结构。工业应用涵盖航空、声学、能源、环境等多领域。",
    "、应变工程综合调控。代工厂(TSMC/Samsung/Intel)的工艺节点演进直接映射该参数空间。",
    "与作物育种、抗逆性改良工程紧密关联。结构上跨植物-动物-微生物呈现保守性，是发育生物学跨界范式之一。",
    "rail of Bits)与formal verification (Certora)是核心防御层。",
    "有相应实验工具。理论模型常用统计力学、随机过程、连续介质力学融合描述。是分子机器与活物质研究的核心。",
]

# Substring forbidden words in rewrite output (any occurrence = reject)
FORBIDDEN_SUBSTRINGS = [
    "成本效益(QALY/DALY)",
    "低中收入国(LMIC)",
    "审计公司(OpenZeppelin/Trail of Bits)",
    "需上下文化策略",
    "需个体化方案",
    "工业应用涵盖航空、声学、能源、环境等多领域",
    "工艺节点演进直接映射该参数空间",
    "是发育生物学跨界范式之一",
    "formal verification (Certora)",
    "是分子机器与活物质研究的核心",
    # Looser substrings added after dry-run failures revealed LLM still
    # emitting near-paraphrases of the boilerplate hooks.
    "QALY/DALY",
    "(QALY",
    "DALY)",
    "LMIC",
    "OpenZeppelin",
    "Trail of Bits",
    "Certora",
    "跨学科保守性",
    "广泛实验验证",
]

REF_PATTERN = re.compile(
    r"(?:18|19|20)\d{2}"            # any year 18xx-20xx (catches "(2017)" etc.)
    r"|arXiv:\d{4}\.\d{4,5}"        # arXiv ID
    r"|《[^》]+》"                   # Chinese book/journal brackets
    r"|J\.\s*[A-Z]"                 # J. X (journal abbrev)
    r"|Phys\.\s*Rev"
    r"|Nature|Science|PNAS|Cell|ApJ|Lancet|NEJM|BMJ|JAMA|Annu\.\s*Rev"
    r"|Textbook|Handbook|Manual|Encyclopedia|Williams"  # canonical English reference works
)


def _backtrack_to_sentence_boundary(desc: str, idx: int) -> int:
    """Find the last sentence-ending punctuation before idx; return position
    AFTER that punctuation (so head[:pos] ends with a complete sentence).
    If none found, return 0 (cut from start)."""
    # Search backwards for 。 . ！ ! ？ ?
    boundary_chars = "。.！!？?"
    for i in range(idx - 1, -1, -1):
        if desc[i] in boundary_chars:
            return i + 1
    return 0


def find_boilerplate(desc: str) -> tuple[str, str] | None:
    """Return (head, tail_to_rewrite) where head ends at a sentence boundary
    before the boilerplate begins (so the join is clean)."""
    for bp in BOILERPLATE_PATTERNS:
        idx = desc.rfind(bp)
        if idx <= 0:
            # also try truncated tail (last 40 chars)
            if bp[-40:] in desc:
                idx = desc.rfind(bp[-40:])
                if idx <= 0:
                    continue
            else:
                continue
        # back up to last sentence boundary BEFORE the boilerplate
        cut = _backtrack_to_sentence_boundary(desc, idx)
        head = desc[:cut].strip()
        if not head:
            # boilerplate starts at sentence 1 — rare; keep mid-sentence
            head = desc[:idx].rstrip("。、，；,;. ")
        return head, desc[cut:]
    return None


PROMPT_TEMPLATE = """你是一个学术知识库内容编辑。下面是一个 description 的"前置内容"。请为它补一段 50-80 字的"延伸尾段"。要求：

【硬性禁忌（出现任一即作废）】
- 不出现以下任何一个 substring：
  "LMIC"、"HIC"、"QALY"、"DALY"、"成本效益"、"需个体化方案"、
  "工业应用涵盖航空"、"工艺节点演进直接映射该参数空间"、
  "是发育生物学跨界范式之一"、"OpenZeppelin"、"Trail of Bits"、
  "formal verification (Certora)"、"是分子机器与活物质研究的核心"、
  "需上下文化策略"、"跨学科保守性"

【必须包含】
- 至少一项**机制层面的具体内容**：临界指数 / 标度律 / 特征长度 / 扩散系数 / 阈值 / Hill 系数 / 弛豫时间等的具体符号或数值。或：**已知验证文献**（Author Year，必须是该领域真实经典文献，宁可不写也不要编造）。或：**典型实验/观测装置**（具体到方法）。

【风格】
- 简洁，不堆术语
- 不重复前置内容里已说过的事
- 不重复领域里其他 entry 共有的套话（如"广泛实验验证"、"跨学科保守性"等空泛表达）

【输出格式】
- 仅输出新尾段中文文本（50-80 字）
- 不要 quote 包裹、不要解释、不要重复前置内容
- 开头不要加句号

---

**领域**：{domain}
**条目名**：{name}
**前置内容**（已结束于句号）：{head}

请输出衔接的新尾段："""


def call_deepseek(prompt: str, retries: int = 3, timeout: int = 30) -> str:
    """Single API call with retry."""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 200,
        "stream": False,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"DeepSeek failed after {retries}: {last_err}")


def validate_rewrite(new_full: str, original: str, head: str = "") -> tuple[bool, str]:
    """3-layer guardrail. Returns (ok, reason_if_fail).

    Forbidden-substring + boilerplate-tail checks apply only to the NEW
    portion (new_full minus head), because the head is preserved verbatim
    and may legitimately contain mechanism terminology that overlaps with
    boilerplate vocabulary.
    """
    # L1: length
    if len(new_full) < 150:
        return False, f"too short ({len(new_full)} < 150)"
    if len(new_full) > 400:
        return False, f"too long ({len(new_full)} > 400)"
    # L2: no forbidden substrings (only check the NEW tail portion)
    new_only = new_full[len(head):] if head and new_full.startswith(head) else new_full
    for forb in FORBIDDEN_SUBSTRINGS:
        if forb in new_only:
            return False, f"forbidden substring in new tail: {forb!r}"
    for bp in BOILERPLATE_PATTERNS:
        if bp[-30:] in new_only:
            return False, f"boilerplate tail still present: {bp[-30:]!r}"
    # L3: author+year reference present (whole new_full OK — head usually has ref)
    if not REF_PATTERN.search(new_full):
        return False, "no Author(Year) / arXiv / journal pattern"
    return True, ""


def rewrite_one(row: dict[str, Any]) -> dict[str, Any]:
    """Process one entry, return result dict."""
    desc = row.get("description", "")
    split = find_boilerplate(desc)
    if not split:
        return {"id": row["id"], "ok": False, "reason": "no boilerplate found"}
    head, tail = split
    prompt = PROMPT_TEMPLATE.format(
        domain=row.get("domain", "?"),
        name=row.get("name", "?"),
        head=head,
    )
    try:
        new_tail = call_deepseek(prompt)
    except Exception as e:  # noqa: BLE001
        return {"id": row["id"], "ok": False, "reason": f"api error: {e}"}
    # Strip quote wrapping if any
    new_tail = new_tail.strip().strip('"\'""''')
    if not new_tail.startswith(("。", ".", "，")):
        # ensure clean join
        joiner = "。" if not head.endswith(("。", ".", "！", "?", "?")) else ""
        new_full = head + joiner + new_tail
    else:
        new_full = head + new_tail
    if not new_full.endswith(("。", "！", "?", ".", "!", "?")):
        new_full += "。"
    ok, reason = validate_rewrite(new_full, desc, head=head)
    return {
        "id": row["id"],
        "domain": row.get("domain", "?"),
        "ok": ok,
        "reason": reason,
        "head_len": len(head),
        "new_tail": new_tail,
        "new_full": new_full,
        "orig_full": desc,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="single call test")
    ap.add_argument("--batch", type=int, default=0, help="first N entries")
    ap.add_argument("--all", action="store_true", help="run all 117")
    ap.add_argument("--apply", action="store_true", help="write back to files")
    ap.add_argument("--workers", type=int, default=8, help="parallel workers")
    args = ap.parse_args()

    flagged_ids = identify_flagged_ids()
    rows = [json.loads(l) for l in open(ADDITIONS_FILE)]
    targets = [r for r in rows if r["id"] in flagged_ids]
    print(f"flagged: {len(targets)}", file=sys.stderr)

    if args.smoke:
        targets = targets[:1]
    elif args.batch > 0:
        targets = targets[: args.batch]
    elif not args.all:
        print("specify --smoke or --batch N or --all", file=sys.stderr)
        sys.exit(2)

    print(f"processing: {len(targets)} with {args.workers} workers", file=sys.stderr)

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        future_to_id = {ex.submit(rewrite_one, r): r["id"] for r in targets}
        for i, fut in enumerate(as_completed(future_to_id), 1):
            res = fut.result()
            results.append(res)
            print(
                f"  [{i:3d}/{len(targets)}] {res['id']:45s} ok={res['ok']} {res.get('reason', '')}",
                file=sys.stderr,
            )
    elapsed = time.time() - t0

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\nstats: {ok_count}/{len(results)} ok, {elapsed:.1f}s elapsed", file=sys.stderr)

    # Dump full output
    out_path = REPO / "data" / "wave3c-rewrite-results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"written: {out_path}", file=sys.stderr)

    if args.smoke:
        print("\n--- SMOKE RESULT ---")
        for r in results:
            print(f"ID: {r['id']}")
            print(f"OK: {r['ok']}, reason: {r.get('reason', '')}")
            print(f"ORIG ({len(r.get('orig_full', ''))}): {r.get('orig_full', '')}")
            print(f"NEW  ({len(r.get('new_full', ''))}): {r.get('new_full', '')}")
        return

    if not args.apply:
        print("\ndry run (no --apply) — files unchanged. Use --apply to write back.", file=sys.stderr)
        return

    # ---- write back ----
    # 1. additions file backup
    bak = ADDITIONS_FILE.with_suffix(".jsonl.bak-pre-rewrite")
    if not bak.exists():
        bak.write_bytes(ADDITIONS_FILE.read_bytes())
        print(f"backed up additions to {bak}", file=sys.stderr)

    # build id -> new_full
    upd = {r["id"]: r["new_full"] for r in results if r["ok"]}
    print(f"applying {len(upd)} updates to additions", file=sys.stderr)
    new_rows = []
    for r in rows:
        if r["id"] in upd:
            r["description"] = upd[r["id"]]
        new_rows.append(r)
    with open(ADDITIONS_FILE, "w") as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 2. master KB cascade
    archive = MASTER_KB.with_name(MASTER_KB.name + ".archive-pre-wave3c-rewrite")
    if not archive.exists():
        archive.write_bytes(MASTER_KB.read_bytes())
        print(f"archived master KB to {archive}", file=sys.stderr)
    master_rows = [json.loads(l) for l in open(MASTER_KB)]
    n_master_upd = 0
    for r in master_rows:
        if r["id"] in upd:
            r["description"] = upd[r["id"]]
            n_master_upd += 1
    with open(MASTER_KB, "w") as f:
        for r in master_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"updated {n_master_upd} entries in master KB ({MASTER_KB})", file=sys.stderr)


if __name__ == "__main__":
    main()
