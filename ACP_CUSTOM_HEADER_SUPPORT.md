# ACP Custom Header Support: Codex vs Antigravity

Investigation into whether the ACP protocol and its implementations support custom HTTP headers for custom gateway endpoints.

---

## ACP Protocol Spec (schema v1.19.0)

The ACP protocol defines three provider-related methods:

| Method | Purpose |
|---|---|
| `providers/list` | List configurable providers with current routing info |
| `providers/set` | Configure a provider with custom endpoint + headers |
| `providers/disable` | Disable a provider |

The `SetProviderRequest` schema supports:

```json
{
  "method": "providers/set",
  "params": {
    "providerId": "string",
    "apiType": "anthropic" | "openai" | "azure" | "vertex" | "bedrock" | {},
    "baseUrl": "string",
    "headers": {
      "key": "value"
    }
  }
}
```

Key field: **`headers: Optional[Dict[str, str]]`** — described as "Full headers map for this provider. May include authorization, routing, or other integration-specific headers."

The `providers` capability is marked as **UNSTABLE** in the spec — "not part of the spec yet, and may be removed or changed at any point."

Source: `acp/schema.py` lines 1863-1898 (ACP SDK)

---

## Codex ACP (github.com/agentclientprotocol/codex-acp)

**Fully implements custom headers for custom gateway endpoints.**

### Mechanism 1: `providers/set`

The client sends a JSON-RPC call to configure a provider with custom endpoint and headers:

```json
{
  "method": "providers/set",
  "params": {
    "providerId": "openai",
    "apiType": "openai",
    "baseUrl": "https://llm-gateway.corp.example.com/openai/v1",
    "headers": {
      "Authorization": "Bearer super-secret",
      "x-adapter-source": "openclaw",
      "sso-email": "zhangsan@xxxx.com"
    }
  }
}
```

Server behavior (`CodexAcpClient.ts`):
- Stores headers in `GatewayConfig.config.http_headers` (line 1323-1331)
- On session creation, merges headers into `model_providers` config (line 1428-1442)
- Headers are sent with every HTTP request to the gateway
- Server auto-adds `"X-Client-Feature-ID": "codex"` to every gateway request (line 361)
- **Security**: headers are never echoed back via `providers/list` (verified in tests, line 76-77)

### Mechanism 2: `authenticate` with `gateway` method

Alternative path — pass headers during authentication via `_meta`:

```json
{
  "method": "authenticate",
  "params": {
    "methodId": "gateway",
    "_meta": {
      "gateway": {
        "baseUrl": "https://gateway.internal/openai",
        "headers": {
          "Authorization": "Bearer via-auth",
          "sso-email": "zhangsan@xxxx.com"
        },
        "providerName": "Corp gateway"
      }
    }
  }
}
```

Both mechanisms call the same `applyGatewayConfig()` (line 340) internally, so header handling is identical.

### Limitation

Codex currently only supports `apiType: "openai"` for gateway routing:

```typescript
const SUPPORTED_GATEWAY_PROTOCOLS: Record<acp.LlmProtocol, WireApi> = {
    openai: "responses",
};
```

Passing `apiType: "anthropic"`, `"vertex"`, etc. throws `invalid_params`. The gateway must speak OpenAI Responses wire format.

---

## Antigravity ACP (agy_acp_server.par)

**Does NOT implement custom headers for custom endpoints.**

### What's missing

- `providers/set` — not implemented (zero references to "provider" in `server.py`)
- `providers/list` — not implemented
- `providers/disable` — not implemented
- No custom header injection mechanism
- No gateway auth method

### Current workaround

Custom endpoint is supported only via environment variable override:

```bash
GOOGLE_GEMINI_BASE_URL=http://localhost:8080
GEMINI_API_KEY=<any-value>
```

This overrides the Gemini SDK's base URL but provides no way to add custom headers. The SDK always sends `x-goog-api-key` and `User-Agent` — these are hardcoded in:

| File | Line | Header |
|---|---|---|
| `google/genai/_api_client.py` | 847 | `x-goog-api-key: {GEMINI_API_KEY}` |
| `server.py` | 3510 | `User-Agent: {api_key_user_agent}` |
| `google/genai/_gaos/_hooks/google_genai_auth.py` | 138 | `x-goog-api-key: {api_key}` (per-request hook) |

No mechanism exists to add arbitrary headers like `x-adapter-source` or `sso-email` without:
1. Binary patching `server.py` inside the `.par` archive
2. Adding a header-injection proxy between the ACP server and the gateway
3. Infrastructure-level injection (load balancer, service mesh sidecar)

---

## Side-by-Side Comparison

| Feature | ACP Protocol Spec | Codex ACP | Antigravity ACP |
|---|---|---|---|
| `providers/set` | Defined (UNSTABLE) | Implemented | **Not implemented** |
| `providers/list` | Defined (UNSTABLE) | Implemented | **Not implemented** |
| `providers/disable` | Defined (UNSTABLE) | Implemented | **Not implemented** |
| Custom headers | `headers: Dict[str, str]` | Full support | **Not supported** |
| Custom base URL | `baseUrl: str` | Via `providers/set` | Via env var `GOOGLE_GEMINI_BASE_URL` |
| Gateway auth method | Not in spec | `authenticate` with `methodId: "gateway"` | **Not supported** |
| Supported protocols | anthropic, openai, azure, vertex, bedrock | openai only | vertex, gemini only |
| Header security | Not specified | Never echoed in list | N/A |
| API key handling | Not specified | Via `headers` field | Via `GEMINI_API_KEY` env var → `x-goog-api-key` header |

---

## What This Means for Custom Gateway Integration

### With Codex ACP (works today)

The client can configure the gateway with custom headers at runtime:

```
ACP Client
    │ providers/set {baseUrl, headers: {x-adapter-source, sso-email}}
    ▼
Codex ACP Server
    │ HTTP request with custom headers injected
    │ POST https://gateway.internal/openai/v1/responses
    │ x-adapter-source: openclaw
    │ sso-email: zhangsan@xxxx.com
    ▼
Customer Gateway
    │ Validates SSO headers, adds real LLM credentials
    ▼
LLM Backend (OpenAI format)
```

### With Antigravity ACP (requires workaround)

Custom headers cannot be injected natively. The workaround requires:

```
ACP Client
    │ No way to pass custom headers via ACP protocol
    ▼
Antigravity ACP Server
    │ HTTP request with only x-goog-api-key + User-Agent
    │ POST http://localhost:8080/v1beta/models/{model}:streamGenerateContent
    │ x-goog-api-key: dummy-not-used  (cannot be removed)
    ▼
Header Injection Layer (proxy / LB / sidecar)
    │ Strips x-goog-api-key, adds custom headers
    │ x-adapter-source: openclaw
    │ sso-email: zhangsan@xxxx.com
    ▼
Customer Gateway Proxy (llm_adapter_proxy.py)
    │ Adds real credentials (API key or ADC)
    ▼
Gemini Backend (Vertex AI or Generative Language API)
```

---

## Recommendation

For enterprise customers who need custom header injection for gateway authentication:

1. **Short term**: Use the `GOOGLE_GEMINI_BASE_URL` env var workaround with a header-injection proxy. The gateway must ignore `x-goog-api-key` and handle auth independently.

2. **Medium term**: Request Google to implement the `providers/set` ACP method in the Antigravity ACP server. The protocol schema already defines it — it just needs server-side implementation.

3. **Alternative**: If OpenAI wire format is acceptable, consider using Codex ACP which supports custom headers natively via `providers/set`.

---

## Source References

| Source | Location | What |
|---|---|---|
| ACP Protocol Schema | `acp/schema.py:1863-1898` | `SetProviderRequest` with `headers` field |
| ACP Protocol Schema | `acp/schema.py:5534-5543` | `providers` capability (UNSTABLE) |
| ACP Protocol Meta | `acp/meta.py:6-8` | `providers/list`, `providers/set`, `providers/disable` methods |
| Codex ACP Server | `CodexAcpClient.ts:424-442` | `providers/set` implementation |
| Codex ACP Server | `CodexAcpClient.ts:245-259` | `authenticate` gateway method |
| Codex ACP Server | `CodexAcpClient.ts:1323-1331` | `GatewayConfig` with `http_headers` |
| Codex ACP Server | `CodexAcpClient.ts:340` | `applyGatewayConfig()` shared handler |
| Antigravity Server | `server.py:3509-3620` | Hardcoded `custom_headers` (User-Agent only) |
| Antigravity GenAI SDK | `_api_client.py:844-847` | `x-goog-api-key` header injection |
