"""Build samples_manifest.json: maps each sample to its dynamics family.

Used by company.html to show 类似结构的深度样例 cross-links.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
SAMPLES = ROOT / "samples"

SAMPLE_TICKERS = {
    "01-nflx": "NFLX",
    "02-nvda": "NVDA",
    "03-pdd": "PDD",
    "04-tsla": "TSLA",
    "05-pton": "PTON",
    "06-byd": "1211.HK",
    "07-shop": "SHOP",
    "08-meituan": "3690.HK",
    "09-snow": "SNOW",
    "10-liauto": "LI",
}


def title_of(slug):
    md = SAMPLES / f"{slug}.md"
    if not md.exists():
        return slug
    txt = md.read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+)$", txt, re.MULTILINE)
    return m.group(1).strip() if m else slug


def main():
    by_tk = {}
    with open(DATA / "companies_struct.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                d = json.loads(line)
                by_tk[d["ticker"]] = d

    samples = []
    for slug, tk in SAMPLE_TICKERS.items():
        c = by_tk.get(tk, {})
        samples.append({
            "slug": slug,
            "ticker": tk,
            "title": title_of(slug),
            "dynamics_family": c.get("dynamics_family", "Unknown"),
            "phase_state": c.get("phase_state", "stable"),
            "name": c.get("name", tk),
        })

    out = DATA / "samples_manifest.json"
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(samples)} samples → {out.name}")
    for s in samples:
        print(f"  {s['slug']:12} {s['ticker']:10} {s['dynamics_family']}")


if __name__ == "__main__":
    main()
