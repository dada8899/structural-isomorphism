#!/usr/bin/env python3
"""
Fetch Compound V2 LiquidateBorrow events per cToken (stablecoin debt markets).

Compound V2 emits LiquidateBorrow on the cToken that was REPAID, so the debt
asset is implied by the emitting contract. We target cUSDC / cDAI / cUSDT to
mirror the stablecoin-debt filter used for Aave V2.

Event (all non-indexed):
  LiquidateBorrow(address liquidator, address borrower, uint256 repayAmount,
                  address cTokenCollateral, uint256 seizeTokens)

Data layout: 5 x 32 bytes = 160 bytes = 320 hex chars
  [0] liquidator (address, left-padded)
  [1] borrower
  [2] repayAmount (uint256 in debt underlying's decimals)
  [3] cTokenCollateral (address)
  [4] seizeTokens (uint256 in collateral cToken units, not underlying)
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
OUT_JSONL = OUT_DIR / "compound_v2_liquidations.jsonl"

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
LIQ_BORROW_TOPIC0 = "0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"

# cToken -> (symbol, underlying_decimals, debt_asset_symbol)
CTOKENS = {
    "0x39AA39c021dfbaE8faC545936693aC917d5E7563": ("cUSDC", 6, "USDC"),
    "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643": ("cDAI", 18, "DAI"),
    "0xf650C3d88D12dB855b8bf7D11Be6C55A4e07dCC9": ("cUSDT", 6, "USDT"),
    "0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5": ("cETH", 18, "ETH"),
    "0xccF4429DB6322D5C611ee964527D42E5d685DD6a": ("cWBTC2", 8, "WBTC"),
}

START_BLOCK = 11362579   # Match Aave window for comparability
END_BLOCK = 19000000
CHUNK = 100000           # Compound has fewer events per block than Aave
SLEEP = 0.22
MIN_CHUNK = 500


def hex_to_int(s):
    if not s:
        return 0
    return int(s, 16)


def parse(rec, ctoken_addr, debt_sym, debt_dec):
    data = rec.get("data", "0x")
    if data.startswith("0x"):
        data = data[2:]
    # LiquidateBorrow has 5 non-indexed params in data
    liquidator = "0x" + data[0:64][-40:].lower() if len(data) >= 64 else None
    borrower = "0x" + data[64:128][-40:].lower() if len(data) >= 128 else None
    repay_raw = hex_to_int("0x" + data[128:192]) if len(data) >= 192 else 0
    ctoken_collateral = "0x" + data[192:256][-40:].lower() if len(data) >= 256 else None
    seize_raw = hex_to_int("0x" + data[256:320]) if len(data) >= 320 else 0

    ts = hex_to_int(rec.get("timeStamp", "0x0"))
    block = hex_to_int(rec.get("blockNumber", "0x0"))
    return {
        "block": block,
        "ts_unix": ts,
        "ts_iso": datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else None,
        "tx_hash": rec.get("transactionHash"),
        "log_index": hex_to_int(rec.get("logIndex", "0x0")),
        "ctoken": ctoken_addr.lower(),
        "debt_symbol": debt_sym,
        "debt_decimals": debt_dec,
        "liquidator": liquidator,
        "borrower": borrower,
        "repay_raw": str(repay_raw),
        "debt_usd": repay_raw / (10 ** debt_dec) if debt_sym in ("USDC", "USDT", "DAI") else None,
        "ctoken_collateral": ctoken_collateral,
        "seize_raw": str(seize_raw),
    }


def fetch_chunk(from_block, to_block, address):
    params = {
        "chainid": CHAIN_ID,
        "module": "logs",
        "action": "getLogs",
        "fromBlock": from_block,
        "toBlock": to_block,
        "address": address,
        "topic0": LIQ_BORROW_TOPIC0,
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


def scan(from_block, to_block, address):
    out = []
    res = fetch_chunk(from_block, to_block, address)
    time.sleep(SLEEP)
    if len(res) < 1000:
        return res
    if to_block - from_block < MIN_CHUNK:
        return res
    mid = (from_block + to_block) // 2
    out.extend(scan(from_block, mid, address))
    out.extend(scan(mid + 1, to_block, address))
    return out


def main():
    if not API_KEY:
        print("Missing ETHERSCAN_API_KEY", file=sys.stderr); sys.exit(1)
    n_total = 0
    start = time.time()
    with OUT_JSONL.open("w") as fout:
        for ctoken, (sym, dec, debt_sym) in CTOKENS.items():
            print(f"\n=== {sym} ({ctoken}) debt={debt_sym} dec={dec} ===")
            cur = START_BLOCK
            n_per = 0
            while cur <= END_BLOCK:
                hi = min(cur + CHUNK - 1, END_BLOCK)
                chunk = scan(cur, hi, ctoken)
                for rec in chunk:
                    try:
                        parsed = parse(rec, ctoken, debt_sym, dec)
                        fout.write(json.dumps(parsed) + "\n")
                        n_per += 1
                        n_total += 1
                    except Exception as e:
                        print(f"  parse err: {e}", file=sys.stderr)
                elapsed = time.time() - start
                print(f"  [{cur:>9} - {hi:>9}]  got {len(chunk):4d}  {sym}_total {n_per:6d}  all_total {n_total:6d}  {elapsed:.1f}s")
                cur = hi + 1
                fout.flush()
            print(f"  {sym}: {n_per} events")
    print(f"\nDONE: {n_total} total events in {time.time() - start:.1f}s")
    print(f"  JSONL: {OUT_JSONL}")


if __name__ == "__main__":
    main()
