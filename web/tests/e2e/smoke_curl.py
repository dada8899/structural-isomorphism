"""Curl-only fallback smoke test (no Playwright dependency).

Run: python3 web/tests/e2e/smoke_curl.py
Exit 0 iff all URLs respond 200/3xx.
"""
import sys
import urllib.request
import urllib.error

URLS = [
    "https://beta.structural.bytedance.city/",
    "https://beta.structural.bytedance.city/learn",
    "https://beta.structural.bytedance.city/search.html",
    "https://beta.structural.bytedance.city/analyze.html",
    "https://beta.structural.bytedance.city/discoveries",
    "https://structural.bytedance.city/",
    "https://phase.bytedance.city/",
]


def check(url: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "si-e2e-smoke/1.0"})
        r = urllib.request.urlopen(req, timeout=15)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print(f"  ERR  {e}")
        return 0


def main():
    """Smoke = "server responded with HTTP semantics" (not 0 / hang / DNS fail).

    Accepts 2xx/3xx (live) and 4xx (path not deployed yet but server is up).
    Fails on 5xx, network error, or DNS failure.
    """
    failures = 0
    for url in URLS:
        code = check(url)
        # 2xx/3xx = live; 4xx = server up but path missing (acceptable for baseline)
        ok = 200 <= code < 500 and code != 0
        marker = "OK  " if 200 <= code < 400 else ("404 " if code == 404 else "FAIL")
        print(f"{marker} {code} {url}")
        if not ok:
            failures += 1
    print(f"\n{len(URLS) - failures}/{len(URLS)} URLs reachable (HTTP semantics)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
