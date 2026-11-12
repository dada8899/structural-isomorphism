#!/usr/bin/env python3
"""Fail closed when critical Phase content falls back to client-only loading."""

from __future__ import annotations

import argparse
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


CONTRACTS = {
    "/company/AAPL": ("AAPL", "30 秒一句话", "AR1 与方差均无显著上行趋势"),
    "/compare?tickers=AAPL,TSLA": (
        "公司对比",
        'data-testid="compare-grid"',
        'data-ticker="AAPL"',
        'data-ticker="TSLA"',
    ),
}


def validate_html(path: str, html: str) -> list[str]:
    return [marker for marker in CONTRACTS[path] if marker not in html]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:3017")
    args = parser.parse_args()
    failures: list[str] = []
    for path in CONTRACTS:
        try:
            with urlopen(f"{args.base.rstrip('/')}{path}", timeout=10) as response:
                if response.status != 200:
                    failures.append(f"{path}: HTTP {response.status}")
                    continue
                html = response.read().decode("utf-8")
        except HTTPError as error:
            failures.append(f"{path}: HTTP {error.code}")
            continue
        except URLError as error:
            failures.append(f"{path}: request failed: {error.reason}")
            continue
        missing = validate_html(path, html)
        if missing:
            failures.append(f"{path}: missing {missing}")
        else:
            print(f"OK {path}: critical content is server-rendered")
    if failures:
        raise SystemExit("Phase initial HTML contract failed:\n" + "\n".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
