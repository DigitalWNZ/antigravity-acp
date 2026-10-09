# Antigravity ACP v1.3.0 — Native Model Gateway Guide

## Overview

Antigravity ACP Server v1.3.0 adds **native model gateway support**. The server now accepts `AGY_LLM_GATEWAY_*` environment variables to route LLM requests through a custom gateway with custom HTTP headers — no sidecar proxy or binary patching needed.

This replaces the old workaround (`GOOGLE_GEMINI_BASE_URL` + `GEMINI_API_KEY` + sidecar header-injection proxy).

---

## 1. Download the ACP Server Binary

### Find the latest version

The ACP server binary metadata is published at the ACP registry:

```
https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json
```

Fetch it programmatically:

```bash
curl -s https://raw.githubusercontent.com/agentclientprotocol/registry/main/antigravity-acp/agent.json | python3 -m json.tool
```

### Download for Linux x86_64

```bash
# Download v1.3.0
curl -L -o agy-acp-server-1.3.0-linux-x86_64.zip \
  "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.3.0-linux-x86_64.zip"

# Extract
python3 -c "
import zipfile
with zipfile.ZipFile('agy-acp-server-1.3.0-linux-x86_64.zip') as z:
    z.extractall('agy-acp-server-v1.3.0/')
"

# Make executable
chmod +x agy-acp-server-v1.3.0/agy_acp_server.par
chmod +x agy-acp-server-v1.3.0/localharness_external
```

### All platform download URLs

| Platform | URL |
|---|---|
| Linux x86_64 | `https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.3.0-linux-x86_64.zip` |
| Linux ARM64 | `https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.3.0-linux-arm64.zip` |
| macOS ARM64 | `https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-1.3.0-darwin-arm64.zip` |
| macOS x86_64 | `https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-1.3.0-darwin-x86_64.zip` |
| Windows x86_64 | `https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-1.3.0-windows-x86_64.zip` |
| Windows ARM64 | `https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-1.3.0-windows-arm64.zip` |

### Contents of the zip

| File | Size | Purpose |
|---|---|---|
| `agy_acp_server.par` | ~884 MB | ACP server (Python .par archive) |
| `localharness_external` | ~125 MB | Go harness binary for gateway routing |

---

## 2. Architecture

```
ACP Client (acp_client_gateway.py)
    │  1. Sets AGY_LLM_GATEWAY_* env vars
    │  2. Sets ANTIGRAVITY_HARNESS_PATH
    │  3. Writes settings.json: {"auth": {"type": "gateway"}}
    │  4. Spawns agy_acp_server.par via spawn_agent_process()
    │
    │  JSON-RPC over stdio
    ▼
ACP Server v1.3.0 (agy_acp_server.par)
    │  Reads AGY_LLM_GATEWAY_* from environment
    │  Launches localharness_external with:
    │    --gemini_service_endpoint=<AGY_LLM_GATEWAY_URL>
    │    --gemini_api_key=<AGY_LLM_GATEWAY_API_KEY>
    │    --gemini_headers=<AGY_LLM_GATEWAY_HEADERS>
    │
    │  POST {AGY_LLM_GATEWAY_URL}/v1beta/models/{model}:streamGenerateContent?alt=sse
    │  Headers:
    │    x-goog-api-key: <AGY_LLM_GATEWAY_API_KEY>
    │    x-adapter-source: <custom>
    │    sso-email: <custom>
    │    User-Agent: google-antigravity-sdk/... acp_version/1.3.0
    ▼
Customer Model Gateway (e.g. llm_adapter_proxy.py on :8080)
    │  Validates custom headers
    │  Adds real LLM credentials (API key or OAuth token)
    │  Forwards to Gemini backend
    ▼
Gemini Backend (Vertex AI or Generative Language API)
```

---

## 3. Gateway Environment Variables

These are the native `AGY_LLM_GATEWAY_*` env vars that the ACP server v1.3.0 reads:

| Environment Variable | Required | Description |
|---|---|---|
| `AGY_LLM_GATEWAY_URL` | Yes | Base URL of the customer gateway (e.g. `http://localhost:8080/`) |
| `AGY_LLM_GATEWAY_API_KEY` | Yes | API key or token sent as `x-goog-api-key` header to the gateway |
| `AGY_LLM_GATEWAY_HEADERS` | No | Comma-separated custom headers: `"key1: val1, key2: val2"` |
| `AGY_LLM_GATEWAY_MODELS` | No | Comma-separated model allowlist (first is default). e.g. `"gemini-3.8-flash, gemini-3.7-flash"` |
| `AGY_LLM_GATEWAY_CA_CERT` | No | Path to a custom CA certificate for TLS verification |
| `AGY_LLM_GATEWAY_PROXY_URL` | No | HTTP proxy URL for gateway connections (e.g. corporate proxy) |
| `ANTIGRAVITY_HARNESS_PATH` | Recommended | Absolute path to `localharness_external` binary |

### Additional env vars (unchanged from old version)

| Environment Variable | Description |
|---|---|
| `AGY_ACP_DEFAULT_MODEL` | Override default model (v1.3.0 default: `gemini-3.8-flash-high`) |
| `AGY_ACP_ENABLE_GATEWAY_AUTH` | Enable gateway auth mode |
| `GEMINI_HOME` | Path to `~/.gemini` (where `settings.json` lives) |

---

## 4. Settings File

The ACP server requires a settings file at `$GEMINI_HOME/antigravity-acp/settings.json`.

For gateway mode, set auth type to `"gateway"`:

```json
{
  "auth": {
    "type": "gateway"
  }
}
```

Default location: `~/.gemini/antigravity-acp/settings.json`

### All supported auth types

| Auth Type | Description | Required Env Vars |
|---|---|---|
| `gateway` | **New in v1.3.0.** Route through customer gateway | `AGY_LLM_GATEWAY_URL`, `AGY_LLM_GATEWAY_API_KEY` |
| `gemini-api-key` | Direct Gemini API with API key | `GEMINI_API_KEY` |
| `oauth-personal` | OAuth personal account | (interactive login) |

---

## 5. Supported Models

v1.3.0 supports the following models (set via `AGY_LLM_GATEWAY_MODELS` or `AGY_ACP_DEFAULT_MODEL`):

| Model ID | Thinking Level | Base Model |
|---|---|---|
| `gemini-3.8-flash` | Default | gemini-3.8-flash |
| `gemini-3.8-flash-high` | High (default model) | gemini-3.8-flash |
| `gemini-3.8-flash-medium` | Medium | gemini-3.8-flash |
| `gemini-3.8-flash-low` | Low | gemini-3.8-flash |
| `gemini-3.7-flash` | Default | gemini-3.7-flash |
| `gemini-3.7-flash-high` | High | gemini-3.7-flash |
| `gemini-3.7-flash-medium` | Medium | gemini-3.7-flash |
| `gemini-3.7-flash-low` | Low | gemini-3.7-flash |

The old version (Aug 18) defaulted to `gemini-3.7-flash-high`. The new v1.3.0 defaults to `gemini-3.8-flash-high`.

---

## 6. ACP Client Setup

### Install the ACP Python SDK

```bash
python3 -m venv venv
venv/bin/pip install agent-client-protocol aiohttp
```

The ACP SDK provides:
- `spawn_agent_process()` — launches and manages the ACP server subprocess (new in recent SDK versions)
- `connect_to_agent()` — lower-level alternative for manual subprocess management
- `Client` interface — callbacks for permission requests, session updates, tool calls
- `text_block()`, `PROTOCOL_VERSION` — protocol helpers

### Client Code (`acp_client_gateway.py`)

Full working client:

```python
#!/usr/bin/env python3
"""ACP Client using Antigravity's native gateway support."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from typing import Any

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
)

DEFAULT_SERVER_DIR = "./agy-acp-server-v1.3.0"
DEFAULT_SERVER_PATH = f"{DEFAULT_SERVER_DIR}/agy_acp_server.par"
DEFAULT_HARNESS_PATH = f"{DEFAULT_SERVER_DIR}/localharness_external"


class SimpleAcpClient(Client):
    """Minimal ACP client that prints streamed agent responses."""

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: Any,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        option_id = options[0].option_id if options else "allow"
        return RequestPermissionResponse(
            outcome=AllowedOutcome(option_id=option_id, outcome="selected")
        )

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        if isinstance(update, AgentMessageChunk):
            if isinstance(update.content, TextContentBlock):
                print(update.content.text, end="", flush=True)
        elif isinstance(update, AgentThoughtChunk):
            if isinstance(update.content, TextContentBlock):
                print(f"[thought] {update.content.text}", flush=True)
        elif isinstance(update, ToolCallStart):
            print(f"\n[tool: {update.title}]", flush=True)


def get_gcloud_token(cmd: str) -> str:
    try:
        return subprocess.check_output(
            ["gcloud", "auth", cmd], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""


def build_gateway_env(
    gateway_url: str, model: str, headers: list[str], api_key: str = ""
) -> dict[str, str]:
    """Configure AGY_LLM_GATEWAY_* env vars for native gateway support."""
    if not api_key:
        api_key = get_gcloud_token("print-identity-token")

    # Write settings.json for gateway auth mode
    settings_dir = os.path.expanduser("~/.gemini/antigravity-acp")
    os.makedirs(settings_dir, exist_ok=True)
    with open(
        os.path.join(settings_dir, "settings.json"), "w", encoding="utf-8"
    ) as f:
        json.dump({"auth": {"type": "gateway"}}, f, indent=2)

    env = os.environ.copy()

    # Point to the external harness binary
    harness_path = os.path.abspath(DEFAULT_HARNESS_PATH)
    if os.path.exists(harness_path):
        env["ANTIGRAVITY_HARNESS_PATH"] = harness_path

    # Native gateway configuration
    env["AGY_LLM_GATEWAY_URL"] = gateway_url
    env["AGY_LLM_GATEWAY_API_KEY"] = api_key
    env["AGY_LLM_GATEWAY_HEADERS"] = ", ".join(headers)
    env["AGY_LLM_GATEWAY_MODELS"] = model

    return env


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Antigravity ACP Client with Native Gateway Support"
    )
    parser.add_argument(
        "--server", default=DEFAULT_SERVER_PATH,
        help="Path to agy_acp_server.par"
    )
    parser.add_argument(
        "--gateway-url", default="http://localhost:8080/",
        help="Gateway URL"
    )
    parser.add_argument(
        "--model", default="gemini-3.7-flash",
        help="Model to use"
    )
    parser.add_argument(
        "--header", action="append", default=[],
        help="Custom header: 'Name: Value' (repeatable)"
    )
    parser.add_argument(
        "--api-key", default="",
        help="Gateway API key (default: gcloud identity token)"
    )
    parser.add_argument(
        "-m", "--message", default=None,
        help="Single prompt message to send"
    )
    args = parser.parse_args()

    headers = args.header if args.header else [
        "x-adapter-source: antigravity",
        "sso-email: zhangsan@xxxx.com",
    ]

    env = build_gateway_env(args.gateway_url, args.model, headers, args.api_key)
    server_path = os.path.abspath(args.server)

    print(f"Gateway URL:   {env['AGY_LLM_GATEWAY_URL']}")
    print(f"Gateway Model: {env['AGY_LLM_GATEWAY_MODELS']}")
    print(f"Headers:       {env['AGY_LLM_GATEWAY_HEADERS']}")
    print(f"Harness:       {env.get('ANTIGRAVITY_HARNESS_PATH', 'not found')}")
    print(f"Server:        {server_path}")
    print()

    async with spawn_agent_process(
        SimpleAcpClient(),
        server_path,
        env=env,
        cwd=os.path.dirname(server_path),
        transport_kwargs={"limit": 16 * 1024 * 1024},
    ) as (conn, _proc):
        await conn.initialize(protocol_version=PROTOCOL_VERSION)
        session = await conn.new_session(cwd=os.getcwd(), mcp_servers=[])
        print(f"ACP Session:   {session.session_id}\n")

        if args.message:
            print(f"You: {args.message}\nAgent: ", end="", flush=True)
            await conn.prompt(
                session_id=session.session_id,
                prompt=[text_block(args.message)],
            )
            print()
        else:
            print("Interactive mode. Type 'quit' to exit.\n")
            while True:
                try:
                    line = input("\nYou: ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line or line.lower() in ("quit", "exit", "q"):
                    break
                print("Agent: ", end="", flush=True)
                await conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(line)],
                )
                print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

### Key differences from old client (`acp_client.py`)

| Feature | Old Client | New Client |
|---|---|---|
| Server launch | Manual `create_subprocess_exec()` + `connect_to_agent()` | `spawn_agent_process()` context manager |
| Custom headers | Sidecar `HeaderInjectionSidecar` proxy | `AGY_LLM_GATEWAY_HEADERS` env var (native) |
| Auth type | `gemini-api-key` | `gateway` |
| Gateway URL | `GOOGLE_GEMINI_BASE_URL` | `AGY_LLM_GATEWAY_URL` |
| API key | `GEMINI_API_KEY` (dummy, stripped by sidecar) | `AGY_LLM_GATEWAY_API_KEY` |
| Cleanup | Manual `proc.terminate()` + `sidecar.stop()` | Automatic via `async with` |
| Permission handling | `{"outcome": "approved"}` dict | `AllowedOutcome(option_id=..., outcome="selected")` |

---

## 7. Customer Model Gateway Proxy (`llm_adapter_proxy.py`)

The gateway proxy sits between the ACP server and the Gemini backend. It:
1. Receives Gemini-format requests from the ACP server
2. Validates custom headers (`x-adapter-source`, `sso-email`)
3. Adds real LLM credentials (ADC OAuth token or API key)
4. Forwards to the Gemini backend (Vertex AI or Generative Language API)

### Wire Format

The ACP server sends requests in Gemini Developer API format:

```
POST {AGY_LLM_GATEWAY_URL}/v1beta/models/{model}:streamGenerateContent?alt=sse
Content-Type: application/json
x-goog-api-key: {AGY_LLM_GATEWAY_API_KEY}
x-adapter-source: antigravity          ← custom header from AGY_LLM_GATEWAY_HEADERS
sso-email: zhangsan@xxxx.com           ← custom header from AGY_LLM_GATEWAY_HEADERS
User-Agent: google-antigravity-sdk/0.0.0-dev ... acp_version/1.3.0

{
  "contents": [...],
  "systemInstruction": {...},
  "tools": [...],
  "generationConfig": {...}
}
```

The response must be in Gemini API format:
- **Streaming**: `text/event-stream` with SSE `data:` lines containing `GenerateContentResponse` JSON
- **Non-streaming**: `application/json` with a single `GenerateContentResponse`

### Running the Proxy (ADC Mode)

```bash
# Authenticate with GCP
gcloud auth application-default login

# Start the proxy
python3 llm_adapter_proxy.py \
  --port 8080 \
  --auth adc \
  --project cloud-llm-preview1 \
  --location global
```

### Running the Proxy (API Key Mode)

```bash
python3 llm_adapter_proxy.py \
  --port 8080 \
  --auth api-key \
  --api-key AIzaSy...
```

### Proxy endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/v1beta/models/{model}:streamGenerateContent` | Streaming generation |
| POST | `/v1beta/models/{model}:generateContent` | Non-streaming generation |
| GET | `/v1beta/models` | List available models |
| GET | `/health` | Health check |

### Cloud Run Deployment

For production, deploy the gateway to Cloud Run. See the reference implementation at `https://github.com/eeeeethan2333/antigravity-with-ge` which includes a `Dockerfile` and `main.py` (FastAPI gateway) with support for both direct Gemini API and Gemini Enterprise App routing.

---

## 8. Step-by-Step: Local End-to-End Test

### Prerequisites

- Python 3.11+
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- GCP project with Vertex AI API enabled

### Step 1: Download and extract the ACP server

```bash
mkdir -p antigravity_acp && cd antigravity_acp

curl -L -o agy-acp-server-v1.3.0.zip \
  "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.3.0-linux-x86_64.zip"

python3 -c "
import zipfile
with zipfile.ZipFile('agy-acp-server-v1.3.0.zip') as z:
    z.extractall('agy-acp-server-v1.3.0/')
"
chmod +x agy-acp-server-v1.3.0/agy_acp_server.par
chmod +x agy-acp-server-v1.3.0/localharness_external
```

### Step 2: Create a Python virtual environment

```bash
python3 -m venv venv
venv/bin/pip install agent-client-protocol aiohttp google-auth requests
```

### Step 3: Start the gateway proxy

```bash
# Save llm_adapter_proxy.py (see Section 7)
# Then start it:
python3 llm_adapter_proxy.py \
  --port 8080 \
  --auth adc \
  --project YOUR_PROJECT_ID \
  --location global &

# Verify it's running
curl -s http://localhost:8080/health
# {"status": "ok"}
```

### Step 4: Save the ACP client

Save `acp_client_gateway.py` from Section 6.

### Step 5: Run a single prompt

```bash
venv/bin/python3 acp_client_gateway.py \
  --gateway-url "http://localhost:8080/" \
  --model "gemini-3.7-flash" \
  --header "x-adapter-source: antigravity" \
  --header "sso-email: zhangsan@xxxx.com" \
  --api-key "gateway-managed" \
  -m "What is 2+2? Reply in one word."
```

Expected output:

```
Gateway URL:   http://localhost:8080/
Gateway Model: gemini-3.7-flash
Headers:       x-adapter-source: antigravity, sso-email: zhangsan@xxxx.com
API Key:       gateway-managed...
Harness:       /path/to/agy-acp-server-v1.3.0/localharness_external
Server:        /path/to/agy-acp-server-v1.3.0/agy_acp_server.par

ACP Session:   5834cdb4-f756-447b-bc5a-d480fc97f42a

You: What is 2+2? Reply in one word.
Agent: Four
```

### Step 6: Run in interactive mode

```bash
venv/bin/python3 acp_client_gateway.py \
  --gateway-url "http://localhost:8080/" \
  --model "gemini-3.7-flash" \
  --header "x-adapter-source: antigravity" \
  --header "sso-email: zhangsan@xxxx.com" \
  --api-key "gateway-managed"
```

### Step 7: Verify custom headers arrive at gateway

Check the proxy log output. You should see:

```
Gateway headers: x-adapter-source=antigravity, sso-email=zhangsan@xxxx.com
x-goog-api-key present (IGNORED by gateway, using proxy's own key)
```

This confirms:
- Custom headers (`x-adapter-source`, `sso-email`) are injected by the ACP server natively
- `x-goog-api-key` is sent (set to `AGY_LLM_GATEWAY_API_KEY` value) — the gateway can use or ignore it
- The User-Agent confirms `acp_version/1.3.0`

---

## 9. Request Flow Detail

### What the ACP client sends (JSON-RPC over stdio)

```json
{
  "jsonrpc": "2.0",
  "method": "prompt",
  "params": {
    "session_id": "5834cdb4-...",
    "prompt": [{"type": "text", "text": "What is 2+2?"}]
  },
  "id": 3
}
```

~100 bytes over stdio.

### What the ACP server sends to the gateway (HTTP)

```
POST http://localhost:8080/v1beta/models/gemini-3.7-flash:streamGenerateContent?alt=sse
x-goog-api-key: gateway-managed
x-adapter-source: antigravity
sso-email: zhangsan@xxxx.com
User-Agent: google-antigravity-sdk/0.0.0-dev ... acp_version/1.3.0
Content-Type: application/json

{
  "contents": [
    {"role": "user", "parts": [{"text": "<system prompt + user message>"}]}
  ],
  "systemInstruction": {"parts": [{"text": "..."}]},
  "tools": [15 tool declarations (~40KB)],
  "generationConfig": {
    "temperature": 1.0,
    "topP": 0.95,
    "maxOutputTokens": 65536,
    "thinkingConfig": {"thinkingBudget": 24576}
  }
}
```

~50 KB. The ACP server expands the ~100 byte client prompt into a full Gemini API request with system instructions, tools, and generation config.

### What the gateway forwards to Gemini backend

The gateway strips/replaces credentials and forwards to Vertex AI:

```
POST https://aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/publishers/google/models/gemini-3.7-flash:streamGenerateContent?alt=sse
Authorization: Bearer {ADC OAuth token}
Content-Type: application/json

{same body as above}
```

---

## 10. Version Comparison

| Feature | Old (agy_acp_server_20260818) | New v1.3.0 (Sep 29) |
|---|---|---|
| Binary size | 1.5 GB (.par) + 113 MB (harness) | 884 MB (.par) + 125 MB (harness) |
| Default model | `gemini-3.7-flash-high` | `gemini-3.8-flash-high` |
| Gateway URL | `GOOGLE_GEMINI_BASE_URL` (workaround) | `AGY_LLM_GATEWAY_URL` (native) |
| Custom headers | Not supported (needs sidecar) | `AGY_LLM_GATEWAY_HEADERS` (native) |
| Gateway API key | `GEMINI_API_KEY` (repurposed) | `AGY_LLM_GATEWAY_API_KEY` (dedicated) |
| Model allowlist | Not supported | `AGY_LLM_GATEWAY_MODELS` |
| CA certificate | Not supported | `AGY_LLM_GATEWAY_CA_CERT` |
| HTTP proxy | Not supported | `AGY_LLM_GATEWAY_PROXY_URL` |
| Auth type | `gemini-api-key` | `gateway` |
| SDK API | `connect_to_agent()` (manual) | `spawn_agent_process()` (context manager) |
| Permission schema | Dict `{"outcome": "approved"}` | `AllowedOutcome` typed object |
| gemini-3.8 models | Not present | Supported |

---

## 11. Troubleshooting

### "Authentication required" error

```
acp.exceptions.RequestError: Authentication required
```

**Cause**: `settings.json` has the wrong auth type, or `AGY_LLM_GATEWAY_*` env vars are not set.

**Fix**: Ensure `~/.gemini/antigravity-acp/settings.json` contains `{"auth": {"type": "gateway"}}` and all required env vars are set.

### ACP server can't find `localharness_external`

**Cause**: `ANTIGRAVITY_HARNESS_PATH` not set or points to wrong location.

**Fix**: Set `ANTIGRAVITY_HARNESS_PATH` to the absolute path of `localharness_external`:

```bash
export ANTIGRAVITY_HARNESS_PATH=/path/to/agy-acp-server-v1.3.0/localharness_external
```

### Gateway receives `x-goog-api-key` with the value from `AGY_LLM_GATEWAY_API_KEY`

This is expected. The ACP server sends `x-goog-api-key` with the value from `AGY_LLM_GATEWAY_API_KEY`. Your gateway should:
- Use this value for gateway-level authentication, OR
- Ignore it and authenticate independently (e.g. via ADC)

### Connection refused / timeout

Check that the gateway proxy is running and accessible on the configured URL:

```bash
curl -s http://localhost:8080/health
```

### Model not found

The `AGY_LLM_GATEWAY_MODELS` value must match a model the gateway and backend support. Common values:
- `gemini-3.8-flash` (v1.3.0 default base)
- `gemini-3.7-flash`

### Old `.par` binary doesn't support `AGY_LLM_GATEWAY_*`

Verify your binary version:

```bash
strings agy_acp_server.par | grep "agy_acp_server_2026"
# Old: agy_acp_server_20260818_01_RC01

strings agy_acp_server.par | grep "AGY_LLM_GATEWAY"
# Should list AGY_LLM_GATEWAY_URL, AGY_LLM_GATEWAY_HEADERS, etc.
# If empty, you need the new v1.3.0 binary.
```

---

## 12. File Structure

```
antigravity_acp/
├── agy-acp-server-v1.3.0/
│   ├── agy_acp_server.par         # ACP server binary (v1.3.0)
│   └── localharness_external      # Go harness for gateway routing
├── acp_client_gateway.py          # ACP client with native gateway support
├── llm_adapter_proxy.py           # Customer gateway proxy (ADC or API key)
├── venv/                          # Python virtualenv
│   └── (agent-client-protocol, aiohttp, google-auth)
└── ~/.gemini/
    └── antigravity-acp/
        └── settings.json          # {"auth": {"type": "gateway"}}
```

---

## 13. Reference Implementation

See `https://github.com/eeeeethan2333/antigravity-with-ge` for a complete working example including:
- `acp-client-gateway.py` — ACP client using native gateway env vars
- `main.py` — FastAPI gateway on Cloud Run with two Gemini routing modes:
  - `gemini-enterprise` — routes to Gemini Enterprise App via Discovery Engine
  - `official` — routes directly to Vertex AI / AI Studio Gemini API
- `Dockerfile` — ready for Cloud Run deployment
