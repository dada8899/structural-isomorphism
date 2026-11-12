"""Regression for local/external analysis status presentation; no provider calls."""
import subprocess
from pathlib import Path

def test_research_external_answer_status():
    subprocess.run(["node", str(Path(__file__).with_suffix(".cjs"))], check=True, timeout=30)
