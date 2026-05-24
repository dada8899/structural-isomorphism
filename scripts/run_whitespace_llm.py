#!/usr/bin/env python3
"""One-off runner: build the A2 whitespace matrix WITH the LLM judging layer,
routed through DeepSeek instead of OpenRouter.

Why this exists: build_whitespace_matrix.py's --llm layer calls
services.llm_client.complete_json, which is hard-wired to the OpenRouter
endpoint + OPENROUTER_API_KEY. This repo only has a DeepSeek key configured
(.env: DEEPSEEK_API_KEY). DeepSeek's API is OpenAI-compatible, so we:
  1. feed the DeepSeek key in as OPENROUTER_API_KEY,
  2. repoint the endpoint constant to DeepSeek,
  3. pin the model to deepseek-chat,
then run the existing builder unchanged.

Usage:  .venv/bin/python scripts/run_whitespace_llm.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_deepseek_key() -> str:
    env = REPO / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DEEPSEEK_API_KEY not found in .env")


def main() -> int:
    key = _load_deepseek_key()
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is empty in .env")

    # The llm_client reads OPENROUTER_API_KEY / LLM_MODEL_S18 from env.
    os.environ["OPENROUTER_API_KEY"] = key
    os.environ["LLM_MODEL_S18"] = "deepseek-chat"

    # services.* imports need web/backend; structural_isomorphism is the
    # top-level package at the repo root; build_whitespace_matrix is in scripts/.
    sys.path.insert(0, str(REPO / "web" / "backend"))
    sys.path.insert(0, str(REPO / "scripts"))
    sys.path.insert(0, str(REPO))

    # Repoint the endpoint constant to DeepSeek's OpenAI-compatible API.
    # llm_client did `from services.llm_service import OPENROUTER_URL`, so the
    # name that complete_json() actually reads lives on llm_client.
    from services import llm_service, llm_client
    deepseek_url = "https://api.deepseek.com/chat/completions"
    llm_service.OPENROUTER_URL = deepseek_url
    llm_client.OPENROUTER_URL = deepseek_url

    import build_whitespace_matrix as bw
    return bw.main(["--llm"])


if __name__ == "__main__":
    raise SystemExit(main())
