#!/usr/bin/env bash
# deploy_donsetch.sh — full deployment of donsetch-http MCP server on a clean host
# Tested on Ubuntu 24.04 with docker compose v2.
set -euo pipefail

# ----- 0. preflight -----
command -v docker >/dev/null || { echo "docker not installed"; exit 1; }
docker compose version >/dev/null || { echo "docker compose v2 not installed"; exit 1; }

# ----- 1. pick ports -----
read -rp "donsetch-http listen port [8765]: " PORT
PORT=${PORT:-8765}

read -rp "Where to put donsetch source? [/opt/hound]: " HOUND_DIR
HOUND_DIR=${HOUND_DIR:-/opt/hound}

# ----- 2. clone donsetch -----
if [[ ! -d "$HOUND_DIR/.git" ]]; then
  echo "==> cloning donsetch to $HOUND_DIR"
  mkdir -p "$(dirname "$HOUND_DIR")"
  git clone https://github.com/dondai44423/donsetch.git "$HOUND_DIR"
else
  echo "==> $HOUND_DIR already exists, git pull"
  (cd "$HOUND_DIR" && git pull)
fi

cd "$HOUND_DIR"

# ----- 3. build image with Chrome (1.2 GB, takes ~3 min) -----
echo "==> building donsetch-mcp:latest (this can take 2-5 minutes)"
docker build --build-arg INSTALL_CHROME=true -t donsetch-mcp:latest .

# ----- 4. open port to all interfaces (so other containers can reach it) -----
echo "==> patching docker-compose.yml: 127.0.0.1:8765 -> 0.0.0.0:8765"
sed -i.bak "s|      - \"127.0.0.1:${PORT}:${PORT}\"|      - \"${PORT}:${PORT}\"|" docker-compose.yml

# ----- 5. start donsetch-http -----
echo "==> starting donsetch-http on port ${PORT}"
docker compose --profile http up -d

# ----- 6. health check -----
sleep 5
HEALTH=$(curl -sS --max-time 5 "http://127.0.0.1:${PORT}/health" || echo "FAIL")
echo "==> health: $HEALTH"

if [[ "$HEALTH" != *\"ok\"* ]]; then
  echo "WARNING: health check did not return ok"
  echo "logs:"
  docker logs donsetch-http --tail 30
  exit 1
fi

cat <<"TIP"

donsetch-http is now running on port ${PORT}.

Next steps:
  - Connect from llama.cpp (--mcp-servers-config /opt/search/mcp-servers.json already has it)
  - Connect from Open WebUI (Tools > DonSeTch toggle)
  - Open firewall: ufw allow ${PORT}/tcp

Tools available (id = donsetch):
  - donsetch__web_search     - search 6 engines (bing, ddg, brave, mojeek, yahoo, google)
  - donsetch__web_fetch      - full markdown of a URL
  - donsetch__web_crawl      - multi-page from one site
  - donsetch__web_screenshot  - PNG render
TIP
