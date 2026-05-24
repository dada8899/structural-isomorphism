#!/bin/bash
# Structural Web 本地开发启动脚本
set -e

cd "$(dirname "$0")/.."

export PYTHONPATH="$HOME/projects/structural-isomorphism:$PYTHONPATH"

cd backend
exec python3 -m uvicorn main:app --host 127.0.0.1 --port 5004 --reload
