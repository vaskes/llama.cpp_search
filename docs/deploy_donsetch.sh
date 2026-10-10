#!/usr/bin/env bash
# deploy_donsetch.sh — full deployment of donsetch-http MCP server on a clean host
# Tested on Ubuntu 24.04 with docker compose v2.
#
# After this script finishes, follow QUICKSTART.md step 3 (point
# llama-server at mcp-servers.json from this repo) to wire the
# tools into the LLM.
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

# ----- 4. open port to all interfaces (so other containers on the
#          same host can reach donsetch-http too — the stdIO shim
#          in this repo still uses 127.0.0.1:8765) -----
echo "==> patching docker-compose.yml: 127.0.0.1:${PORT} -> 0.0.0.0:${PORT}"
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
  # Use docker compose logs (compose-aware) instead of bare
  # `docker logs donsetch-http` which only works when the
  # compose service has an explicit container_name.
  docker compose logs --tail 30 donsetch-http
  exit 1
fi

# ----- 7. smoke test the MCP transport -----
TOOLS=$(curl -sS --max-time 5 -X POST "http://127.0.0.1:${PORT}/mcp" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("result",{}).get("tools",[])))' \
  2>/dev/null || echo "FAIL")
echo "==> tools advertised: ${TOOLS}"
if [[ "${TOOLS}" == "0" || "${TOOLS}" == "FAIL" ]]; then
  echo "WARNING: tools/list returned ${TOOLS} tools — check donsetch logs"
  docker compose logs --tail 30 donsetch-http
fi

# Note: ${PORT} is expanded here (no quotes around the heredoc
# delimiter). The previous version used `<<\"TIP\"` which left
# literal "${PORT}" in the on-screen message.
cat <<TIP

donsetch-http is now running on port ${PORT}.

Next steps:
  - Connect from llama.cpp (the stdIO shim in this repo is already
    configured — see mcp-servers.json and QUICKSTART.md)
  - Open firewall: ufw allow ${PORT}/tcp (only if other hosts need it)

Tools available (4 expected):
  - web_search     - search 6 engines (bing, ddg, brave, mojeek, yahoo, google)
  - web_fetch      - full markdown of a URL
  - web_crawl      - multi-page from one site
  - web_screenshot  - PNG render
TIP
