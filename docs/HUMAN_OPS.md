# HUMAN_OPS — Runbook for llama.cpp_search

This runbook is for a human operator setting up the stack on a fresh host.

## 0. Hardware requirements

| Tier       | RAM    | GPU                | Models supported                          |
| ---------- | ------ | ------------------ | ----------------------------------------- |
| Minimum    | 16 GB  | none               | Qwen3-14B Q4, Qwen3-8B Q4                 |
| Recommended| 32 GB  | none               | Qwen3-27B Q4, Ornith-35B Q4 (32K ctx)     |
| Full       | 64+ GB | NVIDIA 24+ GB VRAM | Any model, full 512K context, fast        |

> ⚠️ **Do not run Ornith 35B Q8 at 512K context on less than 256 GB RAM.** It will OOM-kill.

## 1. Base host setup

```bash
# Ubuntu 24.04
sudo apt update && sudo apt install -y python3 python3-venv nodejs npm git docker.io

# Node 20+ (Playwright MCP requirement)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Docker Compose v2 (already included in docker.io 24+)
docker compose version
```

## 2. llama.cpp

```bash
# Build
git clone https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp
cd /opt/llama.cpp
cmake -B build && cmake --build build --config Release -j

# Verify
./build/bin/llama-server --version
```

Place GGUF models in `/opt/models/`.

## 3. Install this repo

```bash
# Clone
git clone https://github.com/vaskes/llama.cpp_search.git /opt/search
cd /opt/search

# Python deps
python3 -m venv venv
./venv/bin/pip install mcp openai httpx

# Playwright MCP
npm install @playwright/mcp
```

## 4. Install systemd unit

```bash
# Copy the model-agnostic unit
sudo cp systemd/llama.service /etc/systemd/system/llama.service
sudo systemctl daemon-reload

# Pick a preset (or write your own .env)
sudo cp systemd/presets/llama-ornith-32k.env /etc/default/llama-server
sudo systemctl enable --now llama.service

# Verify
systemctl status llama.service
curl http://localhost:8080/health
```

## 5. Start SearXNG

```bash
cd /opt/search/docker
docker compose up -d
# wait 10-20 sec
curl -s "http://localhost:8888/search?q=test&format=json" | head -c 300
```

## 6. Smoke test

```bash
cd /opt/search
./venv/bin/python tests/test_basic.py
```

You should see all 5 tests pass.

## 7. End-to-end test

```bash
./venv/bin/python src/agent.py "What is the boiling point of water?"
./venv/bin/python src/agent.py "Find recent arXiv papers on transformer architecture"
./venv/bin/python src/agent.py "Open https://example.com and tell me what's on it"
```

## 8. Daily use

```bash
# Switch model
sudo cp systemd/presets/llama-qwen38-q4.env /etc/default/llama-server
sudo systemctl restart llama.service

# Update SearXNG settings (engines, formats, etc.)
sudo $EDITOR /opt/search/docker/searxng/settings.yml
cd /opt/search/docker && docker compose restart

# Update mcp_searxng_server.py
sudo $EDITOR /opt/search/src/mcp_searxng_server.py
# (changes take effect on next agent.py run — no daemon to restart)

# View agent logs
tail -f /opt/search/logs/agent.log
cat /opt/search/logs/last_answer.md
```

## 9. Troubleshooting

### llama.service keeps restarting
- Check journal: `journalctl -u llama.service -n 30`
- Common: `port 8080 already in use` → another `llama-server` process is running. `pkill llama-server && sudo systemctl start llama.service`
- Common: `couldn't allocate KV cache` → reduce `LLAMA_CTX_SIZE` in `/etc/default/llama-server`

### SearXNG returns 0 results
- Default engines (DDG, Startpage, Mojeek) often captcha-block from server IPs
- The preset uses API-based engines (Wikipedia, arXiv, GitHub, OpenAlex, Crossref, PubMed, Wikidata, Semantic Scholar) which always work
- For broader web search, set up a proxy or use a public SearXNG instance and change `SEARXNG_URL` in the MCP server

### Agent errors with "unsupported content[].type"
- This is the symptom of `args.prompt` being a list instead of a string
- Fixed in current `agent.py`; if you see it, update the file

### Playwright MCP refuses to start
- "Playwright requires Node.js 20 or higher" — install Node 20
- Browser fails to launch — pass `--no-sandbox` (already in the wrapper)

### MCP tool call returns isError=True
- Check `logs/agent.log` for the actual error
- For SearXNG: test `curl http://localhost:8888/search?q=test&format=json` directly
- For Playwright: try a different URL, or check `--no-sandbox`

### OOM-killer
- Check `dmesg | grep -i 'out of memory'`
- Reduce model size or context length
- See "Hardware requirements" above

## 10. Backup and recovery

All state lives in:
- `/opt/search/` — code, venv, docker config
- `/opt/llama.cpp/build/` — built binary
- `/opt/models/` — GGUF files (the big ones)
- `/etc/default/llama-server` — current model preset
- `/etc/systemd/system/llama.service` — unit file

Docker volumes for SearXNG are inside `/opt/search/docker/searxng/` (no external state).

To redeploy elsewhere, just rsync these paths.

---

## Appendix: model presets

| Preset                     | Model                              | ctx   | RAM  | Notes                                 |
| -------------------------- | ---------------------------------- | ----- | ---- | ------------------------------------- |
| `llama-ornith.env`         | Ornith-1.5-35B-A3B Q8_0 + mmproj   | 512K  | ≥256 | Full preset, mmproj vision            |
| `llama-ornith-32k.env`     | Ornith-1.5-35B-A3B Q8_0 + mmproj   | 32K   | ≥64  | For RAM-constrained hosts             |
| `llama-qwen38-q4.env`      | Qwen3.8-27B Q4_K_M (text only)     | 32K   | ≥24  | Lighter, faster, text-only            |

Create a new preset by copying any of these and editing variables.

---

## Tested presets on this host (llmhost2, 58 GB RAM, no GPU)

| Preset                | Status  | Notes                                           |
| --------------------- | ------- | ----------------------------------------------- |
| `llama-ornith-32k.env`| ✅ works | Loads in ~50 sec, 40 GB RAM used                |
| `llama-qwen38-q4.env` | ✅ works | Loads in ~25 sec, 22 GB RAM used (faster)       |
| `llama-ornith.env`    | ❌ OOM   | 512K ctx needs ≥256 GB RAM                      |

Recommended default: `llama-ornith-32k.env` for capability, `llama-qwen38-q4.env` for speed.
