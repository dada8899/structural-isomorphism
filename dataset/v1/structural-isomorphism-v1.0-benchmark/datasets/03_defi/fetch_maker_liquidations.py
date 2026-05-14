#!/usr/bin/env python3
"""
Fetch MakerDAO Dog 'Bark' events (Liquidation 2.0, 2021+).

Dog contract: 0x135954d155898D42C90D2a57824C690e0c7BEf1B
Event signature (Liquidation 2.0):
  Bark(bytes32 indexed ilk, address indexed urn, uint256 ink, uint256 art,
       uint256 due, address clip, bytes32 indexed id)

Topic0 = keccak256("Bark(bytes32,address,uint256,uint256,uint256,address,bytes32)")

Topics:
  [0] = event hash
  [1] = ilk (bytes32 collateral-type tag, e.g. 0x4554482d41000...  = "ETH-A\0\0\0...")
  [2] = urn (address, left-padded)
  [3] = id (auction id)

Data (non-indexed, 4 slots):
  [0] ink  (uint256 collateral locked, in collateral token's wei)
  [1] art  (uint256 normalized debt, DAI wei pre-multiply by rate)
  [2] due  (uint256 DAI amount due after penalty)
  [3] clip (address of the Clipper contract)

`art` / 1e18 gives an approximate DAI-denominated debt size (exact DAI = art * rate).
For power-law fitting, the multiplicative factor per-ilk drops out of the exponent.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
OUT_JSONL = OUT_DIR / "maker_dog_liquidations.jsonl"

API_KEY = os.getenv("ETHERSCAN_API_KEY") or ""
if not API_KEY:
    env = OUT_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ETHERSCAN_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break

API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1
DOG = "0x135954d155898D42C90D2a57824C690e0c7BEf1B"
# Bark topic0
BARK_TOPIC0 = "0x85258d09e1e4ef299ff3fc11e74af99563f022d21f3f940db982229dc2a3358c"

START_BLOCK = 12486800   # Dog contract deployed May 2021
END_BLOCK = 19000000
CHUNK = 100000
SLEEP = 0.22
MIN_CHUNK = 500


def hex_to_int(s):
    if not s:
        return 0
    return int(s, 16)


def bytes32_to_ascii(h):
    """Convert a bytes32 hex string to the trimmed ASCII label (e.g. ETH-A)."""
    if h.startswith("0x"):
        h = h[2:]
    try:
        b = bytes.fromhex(h)
        return b.rstrip(b"\x00").decode("ascii", errors="replace")
    except Exception:
        return h[:20]


def parse(rec):
    topics = rec.get("topics", [])
    data = rec.get("data", "0x")
    if data.startswith("0x"):
        data = data[2:]
    ilk_hex = topics[1] if len(topics) > 1 else "0x"
    urn = "0x" + topics[2][-40:].lower() if len(topics) > 2 else None
    auction_id = topics[3] if len(topics) > 3 else "0x"
    ink = hex_to_int("0x" + data[0:64]) if len(data) >= 64 else 0
    art = hex_to_int("0x" + data[64:128]) if len(data) >= 128 else 0
    due = hex_to_int("0x" + data[128:192]) if len(data) >= 192 else 0
    clip = "0x" + data[192:256][-40:].lower() if len(data) >= 256 else None

    ts = hex_to_int(rec.get("timeStamp", "0x0"))
    block = hex_to_int(rec.get("blockNumber", "0x0"))
    return {
        "block": block,
        "ts_unix": ts,
        "ts_iso": datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else None,
        "tx_hash": rec.get("transactionHash"),
        "log_index": hex_to_int(rec.get("logIndex", "0x0")),
        "ilk_raw": ilk_hex,
        "ilk": bytes32_to_ascii(ilk_hex),
        "urn": urn,
        "auction_id_raw": auction_id,
        "ink_raw": str(ink),
        "art_raw": str(art),
        "due_raw": str(due),
        "clip": clip,
        # Approximate DAI-denominated debt size (exact requires multiplying by ilk rate).
        # art is 18-decimal RAD-adjusted normalized debt; for power-law fitting scale drops out.
        "debt_dai_approx": art / 1e18,
        "due_dai": due / 1e18,
    }


def fetch_chunk(from_block, to_block):
    params = {
        "chainid": CHAIN_ID,
        "module": "logs",
        "action": "getLogs",
        "fromBlock": from_block,
        "toBlock": to_block,
        "address": DOG,
        "topic0": BARK_TOPIC0,
        "apikey": API_KEY,
    }
    for _ in range(4):
        try:
            r = requests.get(API_URL, params=params, timeout=40)
            r.raise_for_status()
            j = r.json()
            st = j.get("status")
            msg = j.get("message", "")
            result = j.get("result")
            if st == "1" and isinstance(result, list):
                return result
            if st == "0" and "No records" in str(msg):
                return []
            if "rate limit" in str(msg).lower():
                time.sleep(1.0); continue
            return []
        except Exception:
            time.sleep(1.0)
    return []


def scan(from_block, to_block):
    res = fetch_chunk(from_block, to_block)
    time.sleep(SLEEP)
    if len(res) < 1000:
        return res
    if to_block - from_block < MIN_CHUNK:
        return res
    mid = (from_block + to_block) // 2
    out = scan(from_block, mid)
    out.extend(scan(mid + 1, to_block))
    return out


def main():
    if not API_KEY:
        print("Missing ETHERSCAN_API_KEY", file=sys.stderr); sys.exit(1)
    n_total = 0
    start = time.time()
    with OUT_JSONL.open("w") as fout:
        cur = START_BLOCK
        while cur <= END_BLOCK:
            hi = min(cur + CHUNK - 1, END_BLOCK)
            chunk = scan(cur, hi)
            for rec in chunk:
                try:
                    parsed = parse(rec)
                    fout.write(json.dumps(parsed) + "\n")
                    n_total += 1
                except Exception as e:
                    print(f"  parse err: {e}", file=sys.stderr)
            elapsed = time.time() - start
            print(f"  [{cur:>9} - {hi:>9}]  got {len(chunk):4d}  total {n_total:6d}  {elapsed:.1f}s")
            cur = hi + 1
            fout.flush()
    print(f"\nDONE: {n_total} Maker Dog events in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
