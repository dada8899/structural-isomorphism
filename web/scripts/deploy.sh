#!/bin/bash
# Deploy Structural Web to beta.structural.bytedance.city
set -e

VPS="vps"
REMOTE_ROOT="/root/Projects/structural-isomorphism"
LOCAL_MAC_ROOT="$HOME/projects/structural-isomorphism"
LOCAL_WEB="$HOME/Projects/structural-isomorphism/web"

echo "== Step 1: Sync structural_isomorphism Python package =="
rsync -avz --delete \
  "$LOCAL_MAC_ROOT/structural_isomorphism/" \
  "$VPS:$REMOTE_ROOT/structural_isomorphism/"

echo "== Step 2: Sync data (kb-5000-merged only) =="
ssh $VPS "mkdir -p $REMOTE_ROOT/data"
rsync -avz \
  "$LOCAL_MAC_ROOT/data/kb-5000-merged.jsonl" \
  "$VPS:$REMOTE_ROOT/data/kb-5000-merged.jsonl"

echo "== Step 3: Sync model (exclude checkpoints) =="
ssh $VPS "mkdir -p $REMOTE_ROOT/models/structural-v1"
rsync -avz --delete \
  --exclude 'checkpoint-*' \
  "$LOCAL_MAC_ROOT/models/structural-v1/" \
  "$VPS:$REMOTE_ROOT/models/structural-v1/"

echo "== Step 4: Sync web directory =="
rsync -avz --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  "$LOCAL_WEB/" \
  "$VPS:$REMOTE_ROOT/web/"

echo "== Step 5: Update .env for VPS paths =="
ssh $VPS "cat > $REMOTE_ROOT/web/backend/.env <<EOF
OPENROUTER_API_KEY=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
LLM_MODEL=anthropic/claude-sonnet-4.6
STRUCTURAL_DATA_DIR=$REMOTE_ROOT/data
STRUCTURAL_KB_FILE=kb-5000-merged.jsonl
STRUCTURAL_MODEL_PATH=$REMOTE_ROOT/models/structural-v1
STRUCTURAL_PRECOMPUTED_EMBEDDINGS=$REMOTE_ROOT/web/data/kb_embeddings.npy
PORT=5004
EOF
echo '.env written'
cat $REMOTE_ROOT/web/backend/.env | head -3"

echo "== All files synced =="
