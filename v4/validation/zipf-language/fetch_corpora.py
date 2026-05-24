#!/usr/bin/env python3
"""Fetch multi-language corpora for Zipf's law validation.

Sources
-------
1. NLTK Brown corpus (English, ~1.16M tokens). Offline-capable.
2. Wikipedia article-extract sample for {en, zh, ar, hi, es} via the public
   action API (best-effort; falls back gracefully if a language is unreachable).

Outputs to v4/validation/zipf-language/raw/:
    brown_en.txt                — NLTK Brown corpus full text
    wiki_<lang>.txt             — concatenated plaintext extracts (5 languages)
    fetch_log.json              — provenance: n_articles, n_chars, retrieval time

All retrieved text is best-effort; if a language fails, we record the failure
and downstream validation skips it. Brown is the mandatory minimum.
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
    "structural-isomorphism-validation/0.1 "
    "(AI-for-Science research; cross-domain isomorphism; contact: research@bytedance.city)"
)


def fetch_brown() -> Dict:
    """Save NLTK Brown corpus as a single text file."""
    import nltk
    try:
        nltk.data.find("corpora/brown")
    except LookupError:
        print("[brown] downloading NLTK Brown corpus...")
        nltk.download("brown", quiet=True)
    from nltk.corpus import brown

    words = brown.words()
    text = " ".join(words)
    out = OUT_DIR / "brown_en.txt"
    out.write_text(text, encoding="utf-8")
    return {
        "source": "nltk-brown",
        "language": "en",
        "n_tokens_raw": len(words),
        "n_chars": len(text),
        "path": str(out),
    }


def fetch_wiki_lang(lang: str, n_articles: int = 200, timeout: int = 20) -> Dict:
    """Fetch n_articles plaintext extracts from a Wikipedia language edition.

    Returns provenance dict (with success/failure status).
    """
    import requests

    base = f"https://{lang}.wikipedia.org/w/api.php"
    headers = {"User-Agent": WIKI_USER_AGENT}
    session = requests.Session()
    session.headers.update(headers)

    pages_text: List[str] = []
    articles_seen: List[str] = []
    errors: List[str] = []

    # Wikipedia extracts API: 20 pages per call max.
    batches = max(1, n_articles // 20)
    for b in range(batches):
        try:
            # Step 1: get random titles in main namespace
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
            continue

        # Step 2: fetch plaintext extracts for those titles
        try:
            r = session.get(
                base,
                params={
                    "action": "query",
                    "format": "json",
                    "prop": "extracts",
                    "explaintext": 1,
                    "exintro": 0,
                    "titles": "|".join(titles),
                    "redirects": 1,
                },
                timeout=timeout,
            )
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for _, page in pages.items():
                extract = page.get("extract", "")
                if extract and len(extract) > 50:
                    pages_text.append(extract)
                    articles_seen.append(page.get("title", "?"))
        except Exception as e:
            errors.append(f"batch {b} extracts fail: {e}")
            continue

        time.sleep(0.4)  # be polite

    text = "\n\n".join(pages_text)
    out = OUT_DIR / f"wiki_{lang}.txt"
    out.write_text(text, encoding="utf-8")

    return {
        "source": f"wikipedia-{lang}",
        "language": lang,
        "n_articles_fetched": len(pages_text),
        "n_chars": len(text),
        "n_errors": len(errors),
        "errors": errors[:5],
        "path": str(out),
    }


def main(args: argparse.Namespace) -> None:
    log: Dict = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "datasets": []}

    print("[1/2] Fetching NLTK Brown corpus...")
    brown_info = fetch_brown()
    log["datasets"].append(brown_info)
    print(f"      Brown: {brown_info['n_tokens_raw']} tokens, {brown_info['n_chars']} chars")

    if args.skip_wiki:
        print("[2/2] Skipping Wikipedia (--skip-wiki).")
    else:
        print(f"[2/2] Fetching Wikipedia samples for {WIKI_LANGS} "
              f"({args.n_articles} articles each)...")
        for lang in WIKI_LANGS:
            try:
                info = fetch_wiki_lang(lang, n_articles=args.n_articles)
            except Exception as e:
                info = {"source": f"wikipedia-{lang}", "language": lang,
                        "error": str(e), "n_articles_fetched": 0, "n_chars": 0}
            log["datasets"].append(info)
            print(f"      {lang}: {info.get('n_articles_fetched', 0)} articles, "
                  f"{info.get('n_chars', 0)} chars "
                  f"({info.get('n_errors', 0)} errors)")

    log_path = OUT_DIR.parent / "fetch_log.json"
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-articles", type=int, default=200,
                        help="Wikipedia articles per language (default 200)")
    parser.add_argument("--skip-wiki", action="store_true",
                        help="Skip Wikipedia, fetch only Brown (offline mode)")
    main(parser.parse_args())
