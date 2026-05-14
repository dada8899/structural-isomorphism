"""Tiny stdlib HTTP server exposing backtest artifacts.

NOT auto-started — phase-detector frontend integration is a follow-up task.
Run manually:
    python3 v4/product/d1_phase_detector/serve_backtest.py --port 8019

Endpoints:
  GET /backtest-result       -> data/backtest_result.json
  GET /backtest-cumulative   -> data/backtest_cumulative.csv as JSON array
  GET /health                -> {"status": "ok"}

CORS: Access-Control-Allow-Origin: * (dev only).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple

LOG = logging.getLogger("serve_backtest")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULT = os.path.join(SCRIPT_DIR, "data", "backtest_result.json")
DEFAULT_CUMCSV = os.path.join(SCRIPT_DIR, "data", "backtest_cumulative.csv")


def _read_result(path: str) -> Tuple[int, bytes]:
    if not os.path.exists(path):
        return 404, json.dumps({"error": "backtest_result.json not found", "path": path}).encode("utf-8")
    with open(path, "rb") as f:
        return 200, f.read()


def _read_cumulative(path: str) -> Tuple[int, bytes]:
    if not os.path.exists(path):
        return 404, json.dumps({"error": "backtest_cumulative.csv not found", "path": path}).encode("utf-8")
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "date": row["date"],
                    "near_critical_cumret": float(row["near_critical_cumret"]),
                    "other_cumret": float(row["other_cumret"]),
                })
            except (KeyError, ValueError):
                continue
    return 200, json.dumps({"rows": rows, "count": len(rows)}).encode("utf-8")


def make_handler(result_path: str, cum_path: str):
    class Handler(BaseHTTPRequestHandler):
        # quieter default logging
        def log_message(self, fmt, *args):  # noqa: N802
            LOG.info("%s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(204, b"")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._send(200, json.dumps({"status": "ok"}).encode("utf-8"))
            elif path == "/backtest-result":
                status, body = _read_result(result_path)
                self._send(status, body)
            elif path == "/backtest-cumulative":
                status, body = _read_cumulative(cum_path)
                self._send(status, body)
            else:
                self._send(404, json.dumps({"error": "not found", "path": path}).encode("utf-8"))

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backtest artifact server (dev)")
    parser.add_argument("--port", type=int, default=8019)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--result", default=DEFAULT_RESULT)
    parser.add_argument("--cumulative", default=DEFAULT_CUMCSV)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
    handler = make_handler(args.result, args.cumulative)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    LOG.info("Serving backtest artifacts on http://%s:%d", args.host, args.port)
    LOG.info("  result=%s", args.result)
    LOG.info("  cumulative=%s", args.cumulative)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
