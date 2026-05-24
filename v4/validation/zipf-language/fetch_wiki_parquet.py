#!/usr/bin/env python3
"""Stream Wikipedia text from the wikimedia/wikipedia parquet on Hugging Face.

Used as a faster alternative to the wikipedia action API when stub-heavy
languages (ar, zh) make the random-sample loop too slow.

Approach
--------
Hugging Face serves parquet via CDN with HTTP range requests. We use
pyarrow.parquet.ParquetFile + a per-batch iter_batches to read rows
incrementally. Stop once we've accumulated TARGET_TOKENS.

Outputs:
  raw/wiki_<lang>_expanded.txt
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Wikipedia dump shards on HF (20231101 release)
DUMP_DATE = "20231101"
LANG_SHARDS = {
    "en": 41, "zh": 6, "ar": 7, "hi": 2, "es": 13,
}


def _tok_latin(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ſ]+", text.lower())


def _tok_arabic(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ـ", "")
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


def stream_parquet_to_text(lang: str, target_tokens: int) -> dict:
    """Stream the first parquet shard of the language; stop at target_tokens."""
    import pyarrow.parquet as pq

    n_shards = LANG_SHARDS[lang]
    shard_idx_str = f"{0:05d}"
    n_shards_str = f"{n_shards:05d}"
    url = (f"https://huggingface.co/datasets/wikimedia/wikipedia/"
           f"resolve/main/{DUMP_DATE}.{lang}/"
           f"train-{shard_idx_str}-of-{n_shards_str}.parquet")
    print(f"  [{lang}] streaming {url}", file=sys.stderr, flush=True)

    # ParquetFile can open via HTTPS URL using pyarrow >= 8; uses range gets.
    try:
        import pyarrow as pa
        from pyarrow.fs import HadoopFileSystem  # noqa: F401
    except Exception:
        pass

    # Simpler: use fsspec-style HTTPS via pyarrow.HadoopFileSystem? Actually
    # pyarrow.parquet.read_table only supports URL via pyarrow.fs.FileSystem.
    # Use requests + BytesIO with the trick that small head reads suffice.
    # Easiest: download the parquet bytes incrementally, parse row-groups
    # as they arrive. But pq.ParquetFile needs random access. So we download
    # via requests with stream=True and write to a temp file, parsing
    # row groups as the file grows. That requires fancy I/O. Easier: just
    # download the whole shard but stream into a tempfile, and parse it.

    import tempfile
    import requests
    tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    try:
        r = requests.get(url, stream=True, timeout=120, allow_redirects=True)
        r.raise_for_status()
        total = 0
        chunk_size = 1 << 20  # 1 MB
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                tmp.write(chunk)
                total += len(chunk)
                if total % (32 << 20) < chunk_size:  # log every 32 MB
                    print(f"    [{lang}] downloaded {total / (1<<20):.0f} MB",
                          file=sys.stderr, flush=True)
        tmp.flush()
        tmp.close()
        size_mb = total / (1 << 20)
        print(f"  [{lang}] download done: {size_mb:.0f} MB", file=sys.stderr, flush=True)

        # Now parse with pq.ParquetFile - we only iterate rows until target
        out_lines: list[str] = []
        total_tokens = 0
        pf = pq.ParquetFile(tmp.name)
        n_rg = pf.num_row_groups
        print(f"  [{lang}] {n_rg} row groups, {pf.metadata.num_rows} rows",
              file=sys.stderr, flush=True)

        for rg in range(n_rg):
            table = pf.read_row_group(rg, columns=["text"])
            texts = table.column("text").to_pylist()
            for t in texts:
                if not t:
                    continue
                out_lines.append(t)
                total_tokens += len(tok_for(lang, t))
                if total_tokens >= target_tokens:
                    break
            if total_tokens >= target_tokens:
                break
            print(f"    [{lang}] rg {rg+1}/{n_rg}, tokens={total_tokens}",
                  file=sys.stderr, flush=True)

        text = "\n\n".join(out_lines)
        out_path = OUT_DIR / f"wiki_{lang}_expanded.txt"
        out_path.write_text(text, encoding="utf-8")
        return {
            "language": lang,
            "source": f"wikimedia/wikipedia parquet {DUMP_DATE}.{lang}/shard0",
            "n_articles": len(out_lines),
            "n_chars": len(text),
            "n_tokens_estimate": total_tokens,
            "path": str(out_path),
            "target_reached": total_tokens >= target_tokens,
        }
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=1_100_000)
    parser.add_argument("--langs", default="ar,zh")
    args = parser.parse_args()
    import json
    log = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "target_tokens": args.target,
           "datasets": []}
    for lang in args.langs.split(","):
        try:
            info = stream_parquet_to_text(lang, args.target)
        except Exception as e:
            info = {"language": lang, "error": str(e),
                    "n_tokens_estimate": 0}
        log["datasets"].append(info)
        print(f"[{lang}] DONE: tokens={info.get('n_tokens_estimate', 0)} "
              f"articles={info.get('n_articles', 0)}", flush=True)
    log_path = OUT_DIR.parent / "fetch_log_parquet.json"
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
