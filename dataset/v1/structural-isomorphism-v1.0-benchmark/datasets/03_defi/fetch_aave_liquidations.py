#!/usr/bin/env python3
"""
Layer 5 Phase 3: Fetch Aave V2 LiquidationCall events via Etherscan V2 API.

Aave V2 LendingPool (mainnet): 0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9
LiquidationCall event signature:
  LiquidationCall(
    address indexed collateralAsset,
    address indexed debtAsset,
    address indexed user,
    uint256 debtToCover,
    uint256 liquidatedCollateralAmount,
    address liquidator,
    bool receiveAToken
  )
Topic0 = 0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286

Pagination: Etherscan caps at 1000 logs per call. We chunk block ranges
into 50K-block windows; if we hit the 1000 cap, halve the window and
retry until we're below the cap.

Output:
  - aave_v2_liquidations.jsonl  (one event per line, parsed)
  - fetch_log.json
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

import requests

OUT_DIR = Path(__file__).resolve().parent
OUT_JSONL = OUT_DIR / "aave_v2_liquidations.jsonl"
LOG_FILE = OUT_DIR / "fetch_log.json"

API_KEY = os.getenv("ETHERSCAN_API_KEY") or ""
if not API_KEY:
    env = OUT_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ETHERSCAN_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break
if not API_KEY:
    print("Missing ETHERSCAN_API_KEY in env or .env file", file=sys.stderr)
    sys.exit(1)

API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1
AAVE_V2_LENDING_POOL = "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9"
LIQUIDATION_TOPIC0 = "0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286"

# Aave V2 launch was Dec 1 2020 ~ block 11362579
START_BLOCK = 11362579
# End at a reasonable cap: block 19000000 ~ Jan 2024 (comfortable buffer,
# enough for ~3 years of data; can extend later)
END_BLOCK = 19000000

CHUNK_BLOCKS = 50000  # initial chunk size
MIN_CHUNK = 500       # stop recursing below this
SLEEP_SEC = 0.22      # ~4.5 req/sec (under Etherscan 5/sec limit)


def hex_to_int(s: str) -> int:
    if s is None or s == "":
        return 0
    return int(s, 16)


def topic_to_address(t: str) -> str:
    # Addresses in topics are 32-byte left-padded
    return "0x" + t[-40:].lower()


def parse_event(rec: dict) -> dict:
    topics = rec.get("topics", [])
    data = rec.get("data", "0x")
    if data.startswith("0x"):
        data = data[2:]
    # data slots (each 64 hex chars = 32 bytes):
    #   [0] debtToCover (uint256)
    #   [1] liquidatedCollateralAmount (uint256)
    #   [2] liquidator (address)
    #   [3] receiveAToken (bool)
    debt_to_cover = hex_to_int("0x" + data[0:64]) if len(data) >= 64 else 0
    collateral_amount = hex_to_int("0x" + data[64:128]) if len(data) >= 128 else 0

    block_number = hex_to_int(rec.get("blockNumber", "0x0"))
    timestamp = hex_to_int(rec.get("timeStamp", "0x0"))
    return {
        "block": block_number,
        "ts_unix": timestamp,
        "ts_iso": datetime.utcfromtimestamp(timestamp).isoformat() + "Z" if timestamp else None,
        "tx_hash": rec.get("transactionHash"),
        "log_index": hex_to_int(rec.get("logIndex", "0x0")),
        "collateral_asset": topic_to_address(topics[1]) if len(topics) > 1 else None,
        "debt_asset": topic_to_address(topics[2]) if len(topics) > 2 else None,
        "user": topic_to_address(topics[3]) if len(topics) > 3 else None,
        "debt_to_cover_raw": str(debt_to_cover),
        "liquidated_collateral_raw": str(collateral_amount),
    }


def fetch_chunk(from_block: int, to_block: int, depth: int = 0) -> list:
    """Fetch one chunk of logs. If 1000 cap hit, recurse by halving."""
    params = {
        "chainid": CHAIN_ID,
        "module": "logs",
        "action": "getLogs",
        "fromBlock": from_block,
        "toBlock": to_block,
        "address": AAVE_V2_LENDING_POOL,
        "topic0": LIQUIDATION_TOPIC0,
        "apikey": API_KEY,
    }
    for attempt in range(4):
        try:
            r = requests.get(API_URL, params=params, timeout=40)
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            print(f"    retry {attempt + 1} after error: {type(e).__name__}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
            continue

        status = j.get("status")
        message = j.get("message", "")
        result = j.get("result")

        if status == "1" and isinstance(result, list):
            return result
        if status == "0" and "No records found" in str(message):
            return []
        if status == "0" and "rate limit" in str(message).lower():
            time.sleep(1.0)
            continue
        # Other non-OK — just return empty
        print(f"    non-OK status={status} message={message!r}", file=sys.stderr)
        return []
    return []


def scan_range(from_block: int, to_block: int, depth: int = 0) -> list:
    """Recursive chunker to cope with 1000-cap ceiling."""
    out = []
    # Recursion base: small chunk
    results = fetch_chunk(from_block, to_block)
    time.sleep(SLEEP_SEC)
    if len(results) < 1000:
        out.extend(results)
        return out
    # Hit the cap — split into 2 halves
    if to_block - from_block < MIN_CHUNK:
        # Edge case: more than 1000 events in a tiny window; accept what we have
        out.extend(results)
        return out
    mid = (from_block + to_block) // 2
    print(f"    cap hit at [{from_block}, {to_block}] — splitting at {mid}")
    out.extend(scan_range(from_block, mid, depth + 1))
    out.extend(scan_range(mid + 1, to_block, depth + 1))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching Aave V2 LiquidationCall events")
    print(f"  contract: {AAVE_V2_LENDING_POOL}")
    print(f"  topic0:   {LIQUIDATION_TOPIC0}")
    print(f"  block range: [{START_BLOCK}, {END_BLOCK}] ({END_BLOCK - START_BLOCK:,} blocks)")
    print(f"  chunk: {CHUNK_BLOCKS} blocks")
    print()

    all_events = []
    start = time.time()
    with OUT_JSONL.open("w") as fout:
        cur = START_BLOCK
        while cur <= END_BLOCK:
            hi = min(cur + CHUNK_BLOCKS - 1, END_BLOCK)
            chunk = scan_range(cur, hi)
            for rec in chunk:
                try:
                    parsed = parse_event(rec)
                    all_events.append(parsed)
                    fout.write(json.dumps(parsed) + "\n")
                except Exception as e:
                    print(f"  parse error at block {rec.get('blockNumber')}: {e}", file=sys.stderr)
            elapsed = time.time() - start
            eta = (elapsed / max(cur - START_BLOCK, 1)) * (END_BLOCK - cur) if cur > START_BLOCK else 0
            print(f"  [{cur:>9} - {hi:>9}]  got {len(chunk):4d}  total {len(all_events):6d}  elapsed {elapsed:6.1f}s  eta {eta:6.1f}s")
            cur = hi + 1
            fout.flush()

    log = {
        "contract": AAVE_V2_LENDING_POOL,
        "topic0": LIQUIDATION_TOPIC0,
        "start_block": START_BLOCK,
        "end_block": END_BLOCK,
        "chunk_blocks": CHUNK_BLOCKS,
        "n_events": len(all_events),
        "elapsed_sec": time.time() - start,
        "finished_at": datetime.utcnow().isoformat() + "Z",
    }
    LOG_FILE.write_text(json.dumps(log, indent=2))
    print()
    print(f"DONE: {len(all_events)} events in {time.time() - start:.1f}s")
    print(f"  JSONL: {OUT_JSONL}")


if __name__ == "__main__":
    main()
