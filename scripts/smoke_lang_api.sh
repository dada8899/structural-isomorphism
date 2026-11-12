#!/usr/bin/env bash
# smoke_lang_api.sh — verify the ?lang=en / ?lang=zh contract on the deployed backend.
#
# Strategy: hit one representative LLM endpoint in each language and count
# Chinese (CJK) vs English (ASCII letter) characters in the response body.
# - zh response should have mostly CJK characters
# - en response should have mostly ASCII letters and almost no CJK
#
# Uses /api/search/assess (POST, LLM-backed, one-shot JSON — cheapest to probe).

set -u

BASE_URL="${BASE_URL:-https://beta.structural.bytedance.city}"
QUERY="${QUERY:-团队规模变大后效率反而下降}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

pass=0
fail=0

# count_cjk FILE -> prints number of CJK unified ideograph codepoints
count_cjk() {
  python3 -c '
import sys, re
data = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
print(len(re.findall(r"[\u4e00-\u9fff]", data)))
' "$1"
}

# count_ascii_letters FILE -> number of a-zA-Z characters
count_ascii_letters() {
  python3 -c '
import sys, re
data = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
print(len(re.findall(r"[A-Za-z]", data)))
' "$1"
}

run_case() {
  local label="$1" body="$2" outfile="$3"
  echo "--- $label ---"
  curl -sS -X POST "$BASE_URL/api/search/assess" \
    -H 'Content-Type: application/json' \
    -d "$body" \
    -o "$outfile" \
    -w "HTTP %{http_code} in %{time_total}s\n"
}

ZH_OUT="$TMPDIR/zh.json"
EN_OUT="$TMPDIR/en.json"

run_case "zh (default, legacy — regression check)" \
  "{\"query\": \"$QUERY\"}" "$ZH_OUT"
run_case "en" \
  "{\"query\": \"$QUERY\", \"lang\": \"en\"}" "$EN_OUT"

zh_cjk=$(count_cjk "$ZH_OUT")
zh_ascii=$(count_ascii_letters "$ZH_OUT")
en_cjk=$(count_cjk "$EN_OUT")
en_ascii=$(count_ascii_letters "$EN_OUT")

echo
echo "=== Results ==="
echo "zh response: CJK=$zh_cjk  ASCII-letters=$zh_ascii"
echo "en response: CJK=$en_cjk  ASCII-letters=$en_ascii"
echo

# zh regression: must have meaningful Chinese output
if [ "$zh_cjk" -gt 30 ]; then
  echo "PASS  zh still returns Chinese (CJK=$zh_cjk > 30)"
  pass=$((pass+1))
else
  echo "FAIL  zh regression: expected CJK > 30, got $zh_cjk"
  echo "----- zh body head -----"
  head -c 800 "$ZH_OUT"
  echo
  fail=$((fail+1))
fi

# en: ASCII letters must dominate CJK
if [ "$en_ascii" -gt "$en_cjk" ] && [ "$en_ascii" -gt 50 ]; then
  echo "PASS  en returns predominantly English (ASCII=$en_ascii > CJK=$en_cjk)"
  pass=$((pass+1))
else
  echo "FAIL  en not predominantly English: ASCII=$en_ascii  CJK=$en_cjk"
  echo "----- en body head -----"
  head -c 800 "$EN_OUT"
  echo
  fail=$((fail+1))
fi

echo
echo "=== Summary ==="
echo "Pass: $pass  Fail: $fail"
[ "$fail" -eq 0 ]
