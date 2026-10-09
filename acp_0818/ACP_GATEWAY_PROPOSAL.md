# Adding Custom Gateway Support to Antigravity ACP

The Antigravity ACP server (`agy_acp_server.par`) is a closed proprietary binary. You cannot modify its source code. Here are three approaches to add custom gateway support, ordered by complexity.

---

## Option A: ACP Proxy Server (Recommended)

Build a thin ACP server in Python that sits between the client and the Antigravity binary. It intercepts the ACP protocol, adds gateway auth, and routes accordingly.

```
┌──────────┐    ACP (stdio)    ┌─────────────────┐    ACP (stdio)    ┌──────────────────┐
│           │ ───────────────► │                  │ ───────────────► │                  │
│  IDE /    │                  │  ACP Proxy       │                  │  agy_acp_server  │
│  Client   │ ◄─────────────── │  (Python)        │ ◄─────────────── │  .par            │
│           │                  │                  │                  │                  │
└──────────┘                   │  + gateway auth  │                  └──────────────────┘
                               │  + custom route  │
                               │                  │    REST/gRPC     ┌──────────────────┐
                               │                  │ ───────────────► │  Custom LLM      │
                               │                  │ ◄─────────────── │  Endpoint         │
                               └─────────────────┘                  └──────────────────┘
```

### How it works

1. Client spawns the proxy as the ACP server (instead of `agy_acp_server.par`)
2. Proxy handles ACP `initialize` — advertises all Antigravity auth methods **plus** a `gateway` method
3. If client authenticates with `gateway`:
   - Proxy stores `baseUrl` and `headers`
   - On `session/prompt`, proxy calls the custom endpoint directly (e.g. OpenAI-compatible, Gemini API, etc.)
   - Proxy translates responses back into ACP `session/update` messages
4. If client authenticates with any other method:
   - Proxy spawns `agy_acp_server.par` as a subprocess
   - Proxy forwards all ACP messages between client and server transparently

### Implementation

```python
#!/usr/bin/env python3
"""ACP Proxy that adds custom gateway support to Antigravity ACP Server."""

import asyncio
import asyncio.subprocess as aio_subprocess
import json
import os
import sys
from typing import Any

from acp import PROTOCOL_VERSION, text_block
from acp.interfaces import Agent
from acp.schema import (
    AgentMessageChunk,
    AuthMethod,
    ClientCapabilities,
    Implementation,
    InitializeResult,
    NewSessionResult,
    PromptResult,
    TextContentBlock,
)


class GatewayConfig:
    """Stores the custom gateway configuration."""

    def __init__(self, base_url: str, headers: dict[str, str], protocol: str = "openai"):
        self.base_url = base_url
        self.headers = headers
        self.protocol = protocol


class AntigravityGatewayProxy(Agent):
    """ACP agent that proxies to Antigravity or a custom gateway."""

    def __init__(self, server_path: str):
        self.server_path = server_path
        self.gateway_config: GatewayConfig | None = None
        self.antigravity_proc = None
        self.antigravity_conn = None

    async def initialize(self, protocol_version, client_capabilities, client_info):
        # Return our own info with gateway auth method added
        auth_methods = [
            # Original Antigravity methods
            AuthMethod(id="oauth-personal", name="Google Account (Personal)"),
            AuthMethod(id="oauth-business", name="Gemini Enterprise"),
            AuthMethod(id="gemini-api-key", name="Gemini API Key"),
            AuthMethod(id="agent-platform", name="Agent Platform (ADC)"),
            # NEW: Custom gateway
            AuthMethod(
                id="gateway",
                name="Custom model gateway",
                _meta={"gateway": {"protocol": "openai", "restartRequired": "false"}},
            ),
        ]
        return InitializeResult(
            protocol_version=PROTOCOL_VERSION,
            agent_info=Implementation(
                name="antigravity-gateway-proxy",
                title="Antigravity ACP + Custom Gateway",
                version="0.1.0",
            ),
            auth_methods=auth_methods,
        )

    async def authenticate(self, method_id: str, _meta: dict | None = None):
        if method_id == "gateway" and _meta and "gateway" in _meta:
            # Store custom gateway config
            gw = _meta["gateway"]
            self.gateway_config = GatewayConfig(
                base_url=gw["baseUrl"],
                headers=gw.get("headers", {}),
                protocol=gw.get("protocol", "openai"),
            )
        else:
            # Forward to Antigravity server
            # (would need to spawn and proxy to the real server)
            pass

    async def new_session(self, **kwargs):
        if self.gateway_config:
            # Create a local session for custom gateway
            session_id = "gw-" + os.urandom(8).hex()
            return NewSessionResult(session_id=session_id)
        else:
            # Forward to Antigravity server
            pass

    async def prompt(self, session_id: str, prompt: list, **kwargs):
        if self.gateway_config:
            # Route to custom gateway endpoint
            await self._call_custom_gateway(session_id, prompt)
        else:
            # Forward to Antigravity server
            pass

    async def _call_custom_gateway(self, session_id: str, prompt: list):
        """Call the custom LLM endpoint and stream responses back."""
        import aiohttp

        # Build request based on protocol
        if self.gateway_config.protocol == "openai":
            url = f"{self.gateway_config.base_url}/chat/completions"
            messages = [{"role": "user", "content": p.text} for p in prompt if hasattr(p, "text")]
            payload = {"model": "gpt-4", "messages": messages, "stream": True}
        elif self.gateway_config.protocol == "gemini":
            url = f"{self.gateway_config.base_url}/v1beta/models/gemini-pro:generateContent"
            payload = {"contents": [{"parts": [{"text": p.text}]} for p in prompt if hasattr(p, "text")]}
        else:
            raise ValueError(f"Unsupported protocol: {self.gateway_config.protocol}")

        headers = {"Content-Type": "application/json", **self.gateway_config.headers}

        async with aiohttp.ClientSession() as http:
            async with http.post(url, json=payload, headers=headers) as resp:
                # Stream response chunks back as ACP session updates
                async for chunk in resp.content:
                    text = chunk.decode()
                    # Parse and emit as AgentMessageChunk
                    # (actual implementation depends on the response format)
                    pass
```

### What you need to build

| Component | Description |
|---|---|
| **ACP server shell** | Implements the `Agent` interface from the ACP SDK |
| **Auth router** | Checks `method_id` — gateway vs. Antigravity native |
| **Gateway HTTP client** | Calls custom endpoint (OpenAI, Gemini, Anthropic compatible) |
| **Response translator** | Converts HTTP streaming responses into ACP `session/update` messages |
| **Antigravity passthrough** | For non-gateway auth, spawns and proxies to `agy_acp_server.par` |

### Effort estimate
- ~200-400 lines of Python
- 1-2 days for basic implementation
- Main complexity: response streaming translation and Antigravity passthrough

---

## Option B: Env Var Redirect (Quick Hack)

Use the `AGY_ACP_CCPA_BASE_URL` env var to redirect the CCPA endpoint to your own proxy server.

```
┌──────────┐    ACP (stdio)    ┌──────────────────┐    CCPA API     ┌──────────────────┐
│  IDE /    │ ───────────────► │  agy_acp_server  │ ──────────────► │  Your Proxy      │
│  Client   │ ◄─────────────── │  .par            │ ◄────────────── │  (CCPA compat)   │
└──────────┘                   └──────────────────┘                 └────────┬─────────┘
                                                                             │
                                                                             ▼
                                                                    ┌──────────────────┐
                                                                    │  Custom LLM      │
                                                                    │  Endpoint         │
                                                                    └──────────────────┘
```

### How it works

```bash
AGY_ACP_CCPA_BASE_URL=https://my-proxy.example.com python acp_client.py -m "Hello"
```

### Limitations

- Your proxy must implement the **full CCPA API** (`loadCodeAssist`, streaming responses, etc.)
- Only works for `oauth-personal` and `oauth-business` auth types (CCPA flows)
- Does NOT work for `agent-platform` or `gemini-api-key` (different backends)
- The CCPA API is undocumented and complex — reverse-engineering it is non-trivial
- The server still handles OAuth, token exchange, licensing checks — your proxy must pass these

### Effort estimate
- High — requires reverse-engineering the CCPA protocol
- Not recommended unless you already understand the CCPA API

---

## Option C: Standalone ACP Server (Most Flexible)

Skip the Antigravity binary entirely. Build a full ACP server from scratch using the Python SDK that supports gateway auth natively.

```
┌──────────┐    ACP (stdio)    ┌──────────────────┐    REST/gRPC    ┌──────────────────┐
│  IDE /    │ ───────────────► │  Custom ACP      │ ──────────────► │  Any LLM         │
│  Client   │ ◄─────────────── │  Server (Python) │ ◄────────────── │  Endpoint         │
└──────────┘                   └──────────────────┘                 └──────────────────┘
```

### How it works

Build an ACP server that:
1. Accepts any auth method (gateway, API key, OAuth)
2. Routes `session/prompt` to any LLM endpoint (OpenAI, Anthropic, Gemini, local models)
3. Translates LLM responses into ACP `session/update` messages
4. Handles tool calls, permissions, file ops as needed

### What you lose

- No access to Google's Antigravity agent capabilities (multi-agent, subagents, web search, image generation)
- No access to Antigravity-specific features (code exploration, project understanding)
- You're building a generic LLM-to-ACP bridge, not an Antigravity replacement

### What you gain

- Full control over model selection, endpoint routing, and auth
- Can use any LLM: GPT-4, Claude, Gemini, Llama, Mistral, local models
- Can add custom tools, MCP servers, and agent behaviors
- Open-source and fully transparent

### Effort estimate
- ~500-1000 lines for basic implementation
- 3-5 days for a working prototype with streaming, tool calls, and multi-model support
- The ACP Python SDK (`agent-client-protocol`) provides the server-side scaffolding

---

## Recommendation

| Approach | Effort | Flexibility | Keeps Antigravity? |
|---|---|---|---|
| **A: ACP Proxy** | Medium (1-2 days) | High | Yes (passthrough mode) |
| **B: Env Var Redirect** | High (CCPA reverse-eng) | Low | Yes |
| **C: Standalone Server** | Medium (3-5 days) | Highest | No |

**Option A (ACP Proxy)** is the best balance — you keep full Antigravity access for Google auth users, while adding custom gateway support for users who want to bring their own endpoint. The proxy is transparent: clients don't know whether they're talking to Antigravity or the custom gateway.

If you don't need Antigravity at all and just want a generic ACP server with custom endpoint support, **Option C** is cleaner.

---

## Changes Summary (Option A)

To add gateway auth to Antigravity ACP via a proxy, you need:

### 1. New file: `acp_proxy.py`

The ACP proxy server that:
- Implements `Agent` interface from the ACP Python SDK
- Advertises `gateway` auth method alongside Antigravity's native methods
- Routes gateway-authenticated sessions to custom endpoints
- Passes through non-gateway sessions to `agy_acp_server.par`

### 2. Modified: `settings.json` (optional)

Add gateway config:
```json
{
  "auth": { "type": "gateway" },
  "gateway": {
    "base_url": "https://my-llm-proxy.example.com/v1",
    "protocol": "openai",
    "headers": {
      "Authorization": "Bearer sk-xxx"
    }
  }
}
```

### 3. Modified: `acp_client.py`

Point at the proxy instead of the binary:
```python
# Before:
parser.add_argument("--server", default="./agy-acp-server/agy_acp_server.par")

# After:
parser.add_argument("--server", default="python3 acp_proxy.py")
```

### 4. No changes to the Antigravity binary

The `.par` file remains untouched. The proxy spawns it as a subprocess when needed.
