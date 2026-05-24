#!/bin/bash
# Run this ON THE VPS after deploy.sh completes.
# Creates venv, installs deps, sets up systemd + nginx + ssl.
set -e

ROOT=/root/Projects/structural-isomorphism
WEB=$ROOT/web

echo "== Creating venv =="
if [ ! -d "$ROOT/venv" ]; then
  python3 -m venv $ROOT/venv
fi

echo "== Installing dependencies =="
$ROOT/venv/bin/pip install --upgrade pip

echo "-- Install web + ML libs (default index) --"
$ROOT/venv/bin/pip install \
  fastapi==0.110.0 \
  'uvicorn[standard]==0.27.1' \
  pydantic==2.6.1 \
  python-dotenv==1.0.1 \
  httpx==0.26.0 \
  numpy \
  sentence-transformers 2>&1 | tail -10

echo "-- Install torch CPU wheels --"
$ROOT/venv/bin/pip install torch \
  --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -5

echo "== Installing systemd service =="
cp $WEB/scripts/structural-web.service /etc/systemd/system/structural-web.service
systemctl daemon-reload
systemctl enable structural-web

echo "== Starting service =="
systemctl restart structural-web
sleep 8
systemctl status structural-web --no-pager | head -15

echo "== Installing nginx config =="
cp $WEB/scripts/beta-structural.nginx.conf /etc/nginx/conf.d/beta-structural.conf
nginx -t && nginx -s reload

echo "== Done =="
echo "Now run: certbot --nginx -d beta.structural.bytedance.city --non-interactive --agree-tos -m riazward110@gmail.com"
