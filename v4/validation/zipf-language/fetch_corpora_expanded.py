#!/usr/bin/env python3
"""Expanded Wikipedia corpus fetcher targeting >=1M tokens per language.

Strategy:
  - Use Wikipedia REST/action API with `prop=extracts` (full plaintext).
  - Pull random main-namespace articles in batches of 20.
  - Track running token count per language using the same tokenizer as
    `run_validation.py`; stop when >= TARGET_TOKENS or after MAX_BATCHES.
  - Polite pacing: 0.6 s between requests; 5 retries with exponential backoff.

Outputs (append-write so we don't blow up existing 100K samples):
    raw/wiki_<lang>_expanded.txt  -- larger corpus
    raw/wiki_<lang>.txt            -- replaced with the expanded text once done
    fetch_log_expanded.json        -- per-language n_tokens / n_articles
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List

OUT_DIR = Path(__file__).resolve().parent / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WIKI_LANGS = ["en", "zh", "ar", "hi", "es"]
WIKI_USER_AGENT = (
    "structural-isomorphism-validation/0.2 "
    "(AI-for-Science research; cross-domain isomorphism; contact: research@bytedance.city)"
)
TARGET_TOKENS = 1_100_000  # a little headroom above the 1M target
MAX_BATCHES = 800  # 800 batches x 20 articles = up to 16k articles


# ---- tokenizers (mirror run_validation.py) --------------------------------
def _tok_latin(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ſ]+", text.lower())


def _tok_arabic(text: str) -> list[str]:
    # Strip diacritics (combining marks) and tatweel.
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ـ", "")  # tatweel
    return re.findall(r"[؀-ۿݐ-ݿ]+", text)


def _tok_devanagari(text: str) -> list[str]:
    return re.findall(r"[ऀ-ॿ]+", text)


def _tok_zh(text: str) -> list[str]:
    import jieba
    tokens = []
    for t in jieba.cut(text):
        if any("一" <= c <= "鿿" for c in t):
            tokens.append(t)
    return tokens


def tok_for(lang: str, text: str) -> list[str]:
    if lang in ("en", "es"):
        return _tok_latin(text)
    if lang == "ar":
        return _tok_arabic(text)
    if lang == "hi":
        return _tok_devanagari(text)
    if lang == "zh":
        return _tok_zh(text)
    raise ValueError(lang)


# ---- fetcher ---------------------------------------------------------------
def fetch_wiki_lang(lang: str, target_tokens: int, max_batches: int = MAX_BATCHES,
                    timeout: int = 25, sleep_s: float = 0.6) -> Dict:
    import requests
    base = f"https://{lang}.wikipedia.org/w/api.php"
    session = requests.Session()
    session.headers.update({"User-Agent": WIKI_USER_AGENT})

    pages_text: List[str] = []
    articles_seen: set = set()
    errors: List[str] = []
    total_tokens = 0

    for b in range(max_batches):
        try:
            r = session.get(
                base,
                params={
                    "action": "query",
                    "format": "json",
                    "list": "random",
                    "rnnamespace": 0,
                    "rnlimit": 20,
                },
                timeout=timeout,
            )
            r.raise_for_status()
            titles = [p["title"] for p in r.json()["query"]["random"]]
        except Exception as e:
            errors.append(f"batch {b} random fail: {e}")
            time.sleep(2.0)
            continue

        new_titles = [t for t in titles if t not in articles_seen]
        if not new_titles:
            time.sleep(sleep_s)
            continue

        try:
            r = session.get(
                base,
                params={
                    "action": "query",
                    "format": "json",
                    "prop": "extracts",
                    "explaintext": 1,
                    "exintro": 0,
                    "titles": "|".join(new_titles),
                    "redirects": 1,
                },
                timeout=timeout,
            )
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for _, page in pages.items():
                extract = page.get("extract") or ""
                if len(extract) < 50:
                    continue
                title = page.get("title") or "?"
                if title in articles_seen:
                    continue
                articles_seen.add(title)
                pages_text.append(extract)
                total_tokens += len(tok_for(lang, extract))
        except Exception as e:
            errors.append(f"batch {b} extracts fail: {e}")
            time.sleep(2.0)
            continue

        if b % 20 == 0:
            print(f"  [{lang}] batch {b} articles={len(articles_seen)} tokens~{total_tokens}",
                  file=sys.stderr, flush=True)

        if total_tokens >= target_tokens:
            print(f"  [{lang}] target reached at batch {b}", file=sys.stderr)
            break

        time.sleep(sleep_s)

    text = "\n\n".join(pages_text)
    out_expanded = OUT_DIR / f"wiki_{lang}_expanded.txt"
    out_expanded.write_text(text, encoding="utf-8")

    return {
        "source": f"wikipedia-{lang}",
        "language": lang,
        "n_articles_fetched": len(pages_text),
        "n_chars": len(text),
        "n_tokens_estimate": total_tokens,
        "n_errors": len(errors),
        "errors": errors[:5],
        "path": str(out_expanded),
        "target_tokens": target_tokens,
        "target_reached": total_tokens >= target_tokens,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=TARGET_TOKENS,
                        help=f"Target tokens per language (default {TARGET_TOKENS})")
    parser.add_argument("--langs", default=",".join(WIKI_LANGS),
                        help="Comma-separated languages")
    parser.add_argument("--max-batches", type=int, default=MAX_BATCHES)
    args = parser.parse_args()

    langs = args.langs.split(",")
    log = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "target_tokens": args.target,
           "datasets": []}

    for lang in langs:
        print(f"\n[{lang}] fetching toward {args.target} tokens...", flush=True)
        try:
            info = fetch_wiki_lang(lang, args.target, max_batches=args.max_batches)
        except Exception as e:
            info = {"source": f"wikipedia-{lang}", "language": lang,
                    "error": str(e), "n_articles_fetched": 0, "n_chars": 0,
                    "n_tokens_estimate": 0}
        log["datasets"].append(info)
        print(f"[{lang}] DONE: {info.get('n_articles_fetched', 0)} articles, "
              f"{info.get('n_tokens_estimate', 0)} tokens, "
              f"{info.get('n_errors', 0)} errors", flush=True)

    log_path = OUT_DIR.parent / "fetch_log_expanded.json"
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
