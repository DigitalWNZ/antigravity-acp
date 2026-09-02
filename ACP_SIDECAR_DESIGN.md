# Sidecar Header Injection Proxy for Antigravity ACP

## Problem

The Antigravity ACP server does not support custom HTTP headers for custom gateway endpoints. The ACP protocol defines `providers/set` with a `headers` field (and Codex ACP implements it), but Antigravity has not implemented this method.

Enterprise customers need to send custom headers (e.g. `x-adapter-source`, `sso-email`) to their gateway for routing and authentication. The GenAI SDK inside the ACP server hardcodes `x-goog-api-key` and `User-Agent` — there is no mechanism to add arbitrary headers without binary patching.

## Solution

A lightweight sidecar reverse proxy that runs alongside the ACP server, intercepts all outgoing LLM requests, strips `x-goog-api-key`, injects custom headers, and forwards to the real gateway.

## Architecture

```
ACP Client (acp_client.py)
    │  1. Starts sidecar on random port (e.g. :37805)
    │  2. Sets GOOGLE_GEMINI_BASE_URL=http://127.0.0.1:37805
    │  3. Sets GEMINI_API_KEY=sidecar-managed
    │  4. Starts ACP server subprocess with these env vars
    │
    │  stdio (JSON-RPC)
    ▼
ACP Server (agy_acp_server.par)
    │  GenAI SDK sends request to GOOGLE_GEMINI_BASE_URL
    │
    │  POST http://127.0.0.1:37805/v1beta/models/gemini-3.7-flash:streamGenerateContent?alt=sse
    │  x-goog-api-key: sidecar-managed     ← injected by SDK, will be stripped
    │  User-Agent: google-antigravity-sdk/...
    │  Content-Type: application/json
    ▼
Sidecar Proxy (:37805, inside acp_client.py)
    │  - Strips x-goog-api-key header
    │  - Injects custom headers:
    │      x-adapter-source: openclaw
    │      sso-email: zhangsan@xxxx.com
    │  - Forwards to gateway
    │
    │  POST http://localhost:8080/v1beta/models/gemini-3.7-flash:streamGenerateContent?alt=sse
    │  x-adapter-source: openclaw
    │  sso-email: zhangsan@xxxx.com
    │  User-Agent: google-antigravity-sdk/...
    │  Content-Type: application/json
    ▼
Customer Gateway Proxy (:8080, llm_adapter_proxy.py)
    │  - Validates custom headers
    │  - Adds real LLM credentials (API key or ADC token)
    │  - Forwards to backend
    ▼
Gemini Backend (Vertex AI or Generative Language API)
```

## Implementation

All changes are in a single file: `acp_client.py`.

### 1. HeaderInjectionSidecar Class

```python
class HeaderInjectionSidecar:
    """Lightweight reverse proxy that injects custom headers and forwards to the gateway."""

    def __init__(self, gateway_url: str, inject_headers: dict[str, str]):
        self.gateway_url = gateway_url.rstrip("/")
        self.inject_headers = inject_headers
        self.session: ClientSession | None = None
        self.runner: web.AppRunner | None = None
        self.port: int = 0
```

The sidecar takes two parameters:
- `gateway_url` — the real gateway endpoint to forward to
- `inject_headers` — dict of custom headers to inject into every request

### 2. Startup (binds to random port)

```python
async def start(self) -> int:
    self.session = ClientSession(timeout=ClientTimeout(total=300))
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", self._proxy)
    self.runner = web.AppRunner(app)
    await self.runner.setup()
    site = web.TCPSite(self.runner, "127.0.0.1", 0)  # port 0 = OS picks random
    await site.start()
    self.port = site._server.sockets[0].getsockname()[1]
    return self.port
```

- Binds to `127.0.0.1` on a random available port (port 0)
- Catches all HTTP methods and paths via wildcard route
- Returns the assigned port so the caller can set `GOOGLE_GEMINI_BASE_URL`

### 3. Request Proxy (header injection + stripping)

```python
async def _proxy(self, request: web.Request) -> web.StreamResponse:
    target_url = f"{self.gateway_url}/{request.path_qs.lstrip('/')}"
    body = await request.read()

    headers = dict(request.headers)
    headers.pop("Host", None)              # Replace with gateway's host
    headers.pop("x-goog-api-key", None)    # Strip SDK-injected API key
    headers.pop("X-Goog-Api-Key", None)    # Case variant
    headers.update(self.inject_headers)    # Inject custom headers

    resp = await self.session.request(
        request.method, target_url, data=body, headers=headers,
    )

    # Handle SSE streaming responses
    if "text/event-stream" in (resp.content_type or ""):
        response = web.StreamResponse(
            status=resp.status,
            headers={"Content-Type": resp.content_type, "Cache-Control": "no-cache"},
        )
        await response.prepare(request)
        async for chunk in resp.content.iter_any():
            await response.write(chunk)
        await response.write_eof()
        return response

    # Handle regular responses
    resp_body = await resp.read()
    return web.Response(
        status=resp.status,
        content_type=resp.content_type or "application/json",
        body=resp_body,
    )
```

Key behaviors:
- **Strips `x-goog-api-key`** — the GenAI SDK always adds this header; the sidecar removes it so the gateway doesn't see it
- **Injects custom headers** — `headers.update(self.inject_headers)` adds the configured headers to every request
- **Preserves other headers** — `User-Agent`, `Content-Type`, `X-Goog-Api-Client` etc. are passed through
- **Handles SSE streaming** — `streamGenerateContent` responses are streamed back chunk by chunk
- **Forwards body unchanged** — the Gemini API request body passes through unmodified

### 4. CLI Integration in main()

```python
parser.add_argument("--gateway-url", default=None,
                    help="Gateway proxy URL (e.g. http://localhost:8080)")
parser.add_argument("--header", action="append", default=[],
                    help="Custom header to inject: 'Name: Value' (repeatable)")
```

When `--gateway-url` is provided:

```python
sidecar = None
if args.gateway_url:
    inject_headers = {}
    for h in args.header:
        name, _, value = h.partition(":")
        inject_headers[name.strip()] = value.strip()

    sidecar = HeaderInjectionSidecar(args.gateway_url, inject_headers)
    sidecar_port = await sidecar.start()
    sidecar_url = f"http://127.0.0.1:{sidecar_port}"

    env["GOOGLE_GEMINI_BASE_URL"] = sidecar_url
    if not env.get("GEMINI_API_KEY"):
        env["GEMINI_API_KEY"] = "sidecar-managed"
```

- Parses `--header` flags into a dict
- Starts the sidecar and gets its port
- Sets `GOOGLE_GEMINI_BASE_URL` to point the ACP server at the sidecar
- Sets `GEMINI_API_KEY=sidecar-managed` if not already set (the ACP server requires this for `gemini-api-key` mode, but the value is meaningless — the sidecar strips it)

### 5. Cleanup

```python
if sidecar:
    await sidecar.stop()
```

Closes the HTTP session and shuts down the web runner on exit.

## Usage

### Prerequisites

- Gateway proxy running (e.g. `llm_adapter_proxy.py` on port 8080)
- `settings.json` set to `{"auth": {"type": "gemini-api-key"}}`

### Command

```bash
venv/bin/python3 acp_client.py \
  --gateway-url http://localhost:8080 \
  --header "x-adapter-source: openclaw" \
  --header "sso-email: zhangsan@xxxx.com" \
  -m "What is 1+1?"
```

### Output

```
Sidecar proxy started on http://127.0.0.1:37805
  Gateway: http://localhost:8080
  Injected headers: {'x-adapter-source': 'openclaw', 'sso-email': 'zhangsan@xxxx.com'}
  x-goog-api-key: stripped from outgoing requests
Starting ACP server: /home/wangez/antigravity_acp/agy-acp-server/agy_acp_server.par
Initializing ACP connection...
Connected to: antigravity-acp vagy_acp_server_20260818_01_RC01
...
Agent: Two
```

### Gateway proxy log confirms headers

```
Gateway headers: x-adapter-source=openclaw, sso-email=zhangsan@xxxx.com
x-goog-api-key absent (gateway auth via custom headers)
```

## Header Transformation

| Header | ACP Server sends | Sidecar output | Gateway receives |
|---|---|---|---|
| `x-goog-api-key` | `sidecar-managed` | **Stripped** | Absent |
| `x-adapter-source` | Absent | **Injected** | `openclaw` |
| `sso-email` | Absent | **Injected** | `zhangsan@xxxx.com` |
| `User-Agent` | SDK version string | Passed through | SDK version string |
| `Content-Type` | `application/json` | Passed through | `application/json` |
| `X-Goog-Api-Client` | SDK build info | Passed through | SDK build info |
| Request body | Gemini API format | **Unchanged** | Gemini API format |

## Design Decisions

### Why a sidecar instead of modifying the gateway proxy?

The sidecar separates concerns:
- **Sidecar** = client-side concern (what headers to inject, what to strip)
- **Gateway proxy** = server-side concern (how to authenticate to the LLM backend)

A customer's gateway is typically shared infrastructure. Custom headers per-client should be injected client-side, not configured in the gateway.

### Why inside acp_client.py?

The client already spawns the ACP server subprocess and controls its environment. Adding the sidecar here means:
- Single process manages the full lifecycle (sidecar + server)
- No separate process to start/stop
- Headers are configured via CLI flags, not config files
- Clean shutdown — sidecar stops when client exits

### Why random port?

Port 0 lets the OS assign an available port, avoiding conflicts. The sidecar runs on `127.0.0.1` only — not exposed externally.

### Why strip x-goog-api-key?

The GenAI SDK inside the ACP server always injects `x-goog-api-key: {GEMINI_API_KEY}` into every request. We can't prevent this without patching the binary. The sidecar strips it so the gateway doesn't receive a meaningless API key alongside the real auth headers.

## Dependencies

- `aiohttp` — already used by `llm_adapter_proxy.py`, installed in the venv

## Files Changed

| File | Change |
|---|---|
| `acp_client.py` | Added `HeaderInjectionSidecar` class (~65 lines), CLI args, sidecar lifecycle |

No other files need modification. The gateway proxy (`llm_adapter_proxy.py`) works unchanged.
