# Antigravity ACP Gateway Workaround: Step-by-Step Guide

Use the `gemini-api-key` auth mode with `GOOGLE_GEMINI_BASE_URL` override to route Antigravity ACP through a custom gateway (local proxy). This avoids binary patching and works with the unmodified `agy_acp_server.par`.

---

## Architecture

```
ACP Client (acp_client.py)
    │  stdio (JSON-RPC)
    ▼
ACP Server (agy_acp_server.par)
    │  auth: gemini-api-key
    │  GOOGLE_GEMINI_BASE_URL=http://localhost:8080
    │  GEMINI_API_KEY=<api-key>
    │
    │  POST http://localhost:8080/v1beta/models/{model}:streamGenerateContent?alt=sse
    │  Header: x-goog-api-key: <api-key>
    ▼
Local Gateway Proxy (llm_adapter_proxy.py :8080)
    │  Translates and forwards
    ▼
Google Gemini Backend
    ├─ api-key mode  → https://generativelanguage.googleapis.com/v1beta/...
    └─ adc mode      → https://{location}-aiplatform.googleapis.com/v1beta1/projects/...
```

---

## Prerequisites

| Item | Details |
|---|---|
| ACP server binary | `agy-acp-server/agy_acp_server.par` |
| Python 3.10+ | With `aiohttp`, `google-auth` packages |
| ACP SDK | Installed in venv (`venv/bin/python3`) |
| Gemini API key | Or ADC credentials for Vertex AI |

Install dependencies (if not already):

```bash
pip3 install --break-system-packages aiohttp google-auth
```

---

## Step 1: Start the Local Gateway Proxy

The proxy (`llm_adapter_proxy.py`) accepts Gemini API format requests and forwards to the real backend.

### Option A: API Key Mode (Generative Language API)

```bash
python3 llm_adapter_proxy.py \
  --port 8080 \
  --auth api-key \
  --api-key <YOUR_GEMINI_API_KEY>
```

Backend: `https://generativelanguage.googleapis.com`

### Option B: ADC Mode (Vertex AI)

```bash
# First, authenticate with ADC
gcloud auth application-default login

# Then start the proxy
python3 llm_adapter_proxy.py \
  --port 8080 \
  --auth adc \
  --project <GCP_PROJECT_ID> \
  --location global
```

Backend: `https://aiplatform.googleapis.com` (global) or `https://{location}-aiplatform.googleapis.com`

### Verify the proxy is running

```bash
curl -s http://localhost:8080/v1beta/models/gemini-3.6-flash:generateContent \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Say hello"}]}]}' | python3 -m json.tool
```

Expected: JSON response with `candidates[0].content.parts[0].text`.

---

## Step 2: Configure ACP Server Settings

Update `~/.gemini/antigravity-acp/settings.json` to use `gemini-api-key` auth:

```json
{"auth": {"type": "gemini-api-key"}}
```

This tells the ACP server to:
- Read `GEMINI_API_KEY` from environment for credentials
- Read `GOOGLE_GEMINI_BASE_URL` from environment to override the Gemini API endpoint
- Send requests in Gemini Developer API format

---

## Step 3: Run the ACP Client

Run the ACP client with the two environment variables set:

```bash
GOOGLE_GEMINI_BASE_URL=http://localhost:8080 \
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY> \
/home/wangez/antigravity_acp/venv/bin/python3 acp_client.py -m "Say hello in one sentence"
```

### Environment Variables

| Variable | Value | Purpose |
|---|---|---|
| `GOOGLE_GEMINI_BASE_URL` | `http://localhost:8080` | Overrides the Gemini API base URL to point to the local proxy |
| `GEMINI_API_KEY` | Your API key or any token | Credential the ACP server passes to the gateway via `x-goog-api-key` header |

### Interactive Mode

```bash
GOOGLE_GEMINI_BASE_URL=http://localhost:8080 \
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY> \
/home/wangez/antigravity_acp/venv/bin/python3 acp_client.py
```

Type messages at the `You:` prompt. Type `quit` to exit.

---

## Verified Test Result

```
$ GOOGLE_GEMINI_BASE_URL=http://localhost:8080 \
  GEMINI_API_KEY=AIzaSyC7zMM1OC_HUa4K99nYmbaul-mOfizPE6o \
  venv/bin/python3 acp_client.py -m "Say hello in one sentence"

Starting ACP server: /home/wangez/antigravity_acp/agy-acp-server/agy_acp_server.par
Initializing ACP connection...
Connected to: antigravity-acp vagy_acp_server_20260818_01_RC01
Protocol version: 1
Auth methods: ['oauth-personal', 'oauth-business', 'gemini-api-key', 'agent-platform']
Creating session...
Session: ee68a479-a554-4d76-b014-d9e55cd74c2f

You: Say hello in one sentence

Agent: Hello! How can I assist you today?
```

Proxy log (concurrent):

```
→ POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse&key=AIza...
← 200 (stream complete)
```

---

## How It Works Internally

1. **ACP Client** sends a JSON-RPC `prompt` message over stdio to the ACP server
2. **ACP Server** reads `settings.json` → `auth.type = "gemini-api-key"`
3. During `authenticate()`, server reads `GEMINI_API_KEY` from environment
4. During `_create_agent_config()`, server creates a `GeminiAPIEndpoint` with the API key
5. Server checks `GOOGLE_GEMINI_BASE_URL` env var → overrides the SDK's default base URL from `https://generativelanguage.googleapis.com` to `http://localhost:8080`
6. SDK sends `POST http://localhost:8080/v1beta/models/{model}:streamGenerateContent?alt=sse` with header `x-goog-api-key: <key>`
7. **Local Proxy** receives the request, builds the real backend URL, and forwards with proper auth
8. Response streams back through the proxy → ACP server → ACP client

### Key: The `GOOGLE_GEMINI_BASE_URL` Override

The ACP server's Gemini SDK respects this environment variable to override the base URL. This is the official workaround documented by the Antigravity team — no binary patching required.

---

## Model Selection

The `{model}` in the URL is determined by the ACP server — not configured by the user. The server maps an internal ACP model ID to the actual model name sent in the API call.

### Default Model

`gemini-3.7-flash-high` — overridable via env var `AGY_ACP_DEFAULT_MODEL`.

### Model Map (gemini-api-key mode)

In `gemini-api-key` mode, the server uses a hardcoded static model list (no CCPA fetch). The ACP model ID maps to a `base_model_id` + thinking level:

| ACP model_id (internal) | base_model_id (in URL) | Thinking Level |
|---|---|---|
| `gemini-3.7-flash-high` **(default)** | `gemini-3.7-flash` | HIGH |
| `gemini-3.7-flash-medium` | `gemini-3.7-flash` | MEDIUM |
| `gemini-3.7-flash-low` | `gemini-3.7-flash` | LOW |
| `gemini-3.6-flash-high` | `gemini-3.6-flash` | HIGH |
| `gemini-3.6-flash-medium` | `gemini-3.6-flash` | MEDIUM |
| `gemini-3.6-flash-low` | `gemini-3.6-flash` | LOW |
| `gemini-3.5-flash-high` | `gemini-3.5-flash` | HIGH |
| `gemini-3.5-flash-medium` | `gemini-3.5-flash` | MEDIUM |
| `gemini-3.5-flash-low` | `gemini-3.5-flash` | LOW |
| `gemini-3.1-pro-high` | `gemini-3.1-pro-preview` | HIGH |
| `gemini-3.1-pro-low` | `gemini-3.1-pro-preview` | LOW |

The `base_model_id` is what appears as `{model}` in the URL. For example, the default `gemini-3.7-flash-high` results in:

```
POST {GOOGLE_GEMINI_BASE_URL}/v1beta/models/gemini-3.7-flash:streamGenerateContent?alt=sse
```

### Implications for the Gateway

- The gateway proxy does **not** need to know the model list — it just forwards whatever `{model}` the ACP server puts in the URL
- The thinking level is sent inside the request body (`generationConfig.thinkingConfig`), not in the URL
- To change the default model, set `AGY_ACP_DEFAULT_MODEL=<acp-model-id>` in the ACP server's environment

Source: `model_selection.py` inside `agy_acp_server.par` (lines 25-119)

---

## Gateway Protocol Requirements

The gateway (proxy) must accept requests in Gemini Developer API format:

```
POST {GOOGLE_GEMINI_BASE_URL}/v1beta/models/{model}:streamGenerateContent?alt=sse
Header: x-goog-api-key: {GEMINI_API_KEY}
Content-Type: application/json

{
  "contents": [{"role": "user", "parts": [{"text": "..."}]}],
  "generationConfig": {...},
  "safetySettings": [...]
}
```

Response must be SSE with Gemini Developer API shape:

```
data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "..."}]}}], "usageMetadata": {...}, "modelVersion": "..."}
```

---

## Proxy Auth Modes Comparison

| Mode | Flag | Backend | Auth Mechanism | Use Case |
|---|---|---|---|---|
| API Key | `--auth api-key --api-key <key>` | generativelanguage.googleapis.com | API key in query string | Simple, no GCP project needed |
| ADC | `--auth adc --project <id> --location <loc>` | {location}-aiplatform.googleapis.com | OAuth2 Bearer token from ADC | Vertex AI, provisioned throughput |

### Tested Configurations

| Proxy Auth | Project | Location | Model | Result |
|---|---|---|---|---|
| api-key | N/A | N/A | gemini-3.6-flash | Working |
| adc | agolis-allen-first | global | gemini-3.7-flash | Working |
| adc | cloud-llm-preview1 | global | gemini-3.7-flash | Working (provisioned throughput) |

---

## Troubleshooting

### Proxy returns 403

- **ADC mode**: Check that the ADC identity has `roles/aiplatform.user` on the project
  ```bash
  gcloud auth application-default login  # re-auth as correct user
  ```
- **API key mode**: Verify the API key is valid and not restricted

### Proxy returns 404

- Model name may be deprecated. Try a current model (e.g. `gemini-3.6-flash`, `gemini-3.7-flash`)

### ACP client can't import `acp` module

- Use the venv Python: `venv/bin/python3 acp_client.py`

### ACP server stdout corruption

- Only happens with OAuth auth types (browser opener writes to stdout)
- Does NOT happen with `gemini-api-key` auth — no browser flow
- If using OAuth modes, use `acp_server_wrapper.py` to filter stdout

---

## Files

| File | Purpose |
|---|---|
| `llm_adapter_proxy.py` | Local gateway proxy — accepts Gemini format, forwards to backend |
| `acp_client.py` | ACP test client — connects to ACP server over stdio |
| `acp_server_wrapper.py` | Stdout filter wrapper for OAuth auth modes (not needed for api-key) |
| `agy-acp-server/agy_acp_server.par` | Antigravity ACP server binary |
| `~/.gemini/antigravity-acp/settings.json` | ACP server configuration |
