# How Codex ACP and Claude Agent ACP Handle Custom Endpoints

A deep dive into the source code of both ACP servers to understand how custom model endpoints (gateways) are configured, stored, and routed to the underlying LLM.

---

## Overview

Both Codex ACP and Claude Agent ACP support custom endpoints through two mechanisms:

1. **Gateway auth** — the IDE/client sends a `baseUrl` + `headers` during the ACP `authenticate` call
2. **Providers API** — the client calls `providers/set` at runtime to change the backend

The key difference: Codex routes to **OpenAI-compatible** endpoints, while Claude Agent routes to **Anthropic/Bedrock/Vertex** endpoints.

---

## Codex ACP (`@agentclientprotocol/codex-acp`)

### Gateway Auth Request Structure

```typescript
interface GatewayAuthRequest extends AuthenticateRequest {
    methodId: "gateway";
    _meta: {
        "gateway": {
            baseUrl: string;                    // Custom API endpoint URL
            headers: Record<string, string>;    // Custom HTTP headers
            providerName?: string;              // Optional provider label
        }
    };
}
```

The gateway method is only offered when the client declares support:

```typescript
const supportsGatewayAuth = clientCapabilities?.auth?._meta?.["gateway"] === true;
```

### Internal Storage

Gateway config is stored as:

```typescript
interface GatewayConfig {
    modelProvider: string;    // Always "custom-gateway"
    config: {
        name: string;
        base_url: string;
        http_headers: Record<string, string>;
        wire_api: WireApi;    // "responses" for OpenAI protocol
    }
}
```

### Data Flow: Custom Endpoint → API Call

```
1. Client calls authenticate({ methodId: "gateway", _meta: { gateway: { baseUrl, headers }}})
       or calls providers/set({ providerId: "openai", baseUrl, headers, apiType: "openai" })
                    ↓
2. applyGatewayConfig() validates and stores GatewayConfig
   - Validates protocol (only "openai" → "responses" wire API supported)
   - Validates baseUrl is non-empty
   - Injects "X-Client-Feature-ID": "codex" header merged with user headers
   - Stores: this.gatewayConfig = { modelProvider: "custom-gateway", config: { base_url, http_headers, wire_api, name }}
                    ↓
3. On newSession / resumeSession:
   - createSessionConfig() calls mergeGatewayConfig()
   - Gateway config is injected into config["model_providers"]["custom-gateway"]:
     {
       "model_providers": {
         "custom-gateway": {
           "name": "Custom Gateway",
           "base_url": "https://my-proxy.example.com",
           "http_headers": { "Authorization": "Bearer xxx", "X-Client-Feature-ID": "codex" },
           "wire_api": "responses"
         }
       }
     }
                    ↓
4. codexClient.threadStart({ config: mergedConfig, modelProvider: "custom-gateway" })
   - Codex process receives the full config with the custom provider entry
   - modelProvider tells it which entry in model_providers to use for LLM requests
                    ↓
5. Codex CLI makes API calls to base_url with http_headers
```

### Provider Resolution Priority

```typescript
getModelProvider(): string | null {
    return this.gatewayConfig?.modelProvider   // 1. Gateway config (if set)
        ?? this.modelProvider;                  // 2. Constructor / MODEL_PROVIDER env var
}
```

### Default Endpoint

When no gateway is configured, the native OpenAI config is used:

```typescript
getNativeProviderConfig() {
    // Looks up this.modelProvider in this.config["model_providers"]
    // Falls back to: "https://api.openai.com/v1"
}
```

### Providers API

```typescript
// Set custom endpoint at runtime
setProvider(request: SetProviderRequest): void {
    // Only "openai" provider ID accepted
    this.applyGatewayConfig({ apiType: request.apiType, baseUrl: request.baseUrl, headers: request.headers });
}

// Clear custom endpoint, revert to native
disableProvider(request: DisableProviderRequest): void {
    this.gatewayConfig = null;  // Reverts to native OpenAI routing
}

// Query current provider state
listProviders(): ProviderInfo[] {
    // Returns single "openai" provider with current baseUrl
}
```

### Process Restart on Provider Change

When `setProvider` is called via the server-level handler, the **entire Codex process is restarted**:

1. Waits for active prompts to finish
2. Ends stdin on old process, waits for exit (2s force-kill timeout)
3. Starts new `CodexConnection`
4. Creates new `CodexAcpClient` with updated config
5. Re-initializes with saved `initializeRequest`
6. Resumes all existing sessions against the new process

---

## Claude Agent ACP (`@agentclientprotocol/claude-agent-acp`)

### Gateway Auth Request Structure

```typescript
type GatewayAuthMeta = {
    gateway: {
        baseUrl: string;                    // Custom API endpoint URL
        headers: Record<string, string>;    // Custom HTTP headers (e.g. API key)
    };
};

// Two gateway methods:
// "gateway"         → Anthropic protocol
// "gateway-bedrock" → Bedrock protocol
```

### Internal Storage

Provider config is stored as:

```typescript
type ProviderConfig = {
    apiType: LlmProtocol;                   // "anthropic" | "bedrock" | "vertex"
    baseUrl: string;
    headers: Record<string, string>;
    vertex?: { projectId: string; region: string };
};
```

### Data Flow: Custom Endpoint → API Call

```
1. Client calls authenticate({ methodId: "gateway", _meta: { gateway: { baseUrl, headers }}})
       or calls providers/set({ providerId: "main", baseUrl, headers, apiType })
                    ↓
2. Gateway auth: gatewayAuthRequest stored on ClaudeAcpAgent
   providers/set: ProviderConfig built and stored, enqueueProviderUpdate() called
                    ↓
3. resolveProviderConfig() determines active config:
   - this.providerConfig (from providers/set)       ← highest priority
   - gatewayRequestToProviderConfig(gatewayAuth)    ← gateway auth
   - defaultProviderConfig()                        ← env vars / defaults
                    ↓
4. defaultProviderConfig() fallback chain:
   a. Gateway auth request → ProviderConfig
   b. CLAUDE_CODE_USE_BEDROCK → { apiType: "bedrock", baseUrl: ANTHROPIC_BEDROCK_BASE_URL }
   c. CLAUDE_CODE_USE_VERTEX  → { apiType: "vertex",  baseUrl: ANTHROPIC_VERTEX_BASE_URL }
   d. Default                 → { apiType: "anthropic", baseUrl: ANTHROPIC_BASE_URL || "https://api.anthropic.com" }
                    ↓
5. createEnvForProvider(providerConfig) builds environment variables:
   - Maps baseUrl → ANTHROPIC_BASE_URL (or equivalent for bedrock/vertex)
   - Maps headers → custom env vars consumed by the SDK
   - Maps apiType → SDK routing flags
                    ↓
6. Claude Agent SDK query() is spawned with those env vars
   - SDK subprocess makes API calls to the configured baseUrl with headers
                    ↓
7. providerCacheKey derived from routing-relevant env vars
   - Scopes context window cache per-provider
   - Same model ID can have different windows behind different base URLs
```

### Provider Resolution Priority

```typescript
resolveProviderConfig(): ProviderConfig | null {
    return this.providerConfig                                    // 1. providers/set (highest)
        ?? gatewayRequestToProviderConfig(this.gatewayAuthRequest); // 2. Gateway auth
}

// If both are null, defaultProviderConfig() uses env vars:
// 3. CLAUDE_CODE_USE_BEDROCK + ANTHROPIC_BEDROCK_BASE_URL
// 4. CLAUDE_CODE_USE_VERTEX + ANTHROPIC_VERTEX_BASE_URL
// 5. ANTHROPIC_BASE_URL (default: "https://api.anthropic.com")
```

### Default Endpoints

| Provider | Env Var | Default |
|---|---|---|
| Anthropic (direct) | `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` |
| AWS Bedrock | `ANTHROPIC_BEDROCK_BASE_URL` | `https://bedrock-runtime.amazonaws.com` |
| Google Vertex | `ANTHROPIC_VERTEX_BASE_URL` | `https://aiplatform.googleapis.com` |

### Providers API

```typescript
// Set custom endpoint at runtime
async unstable_setProvider(params: SetProviderRequest): Promise<void> {
    // Validates: providerId === "main"
    // Validates: apiType in ["anthropic", "bedrock", "vertex"]
    // Validates: baseUrl is valid absolute HTTP(S) URL
    // For vertex: extracts projectId/region from _meta.claudeCode.vertex
    const config: ProviderConfig = { apiType, baseUrl, headers };
    await this.enqueueProviderUpdate(config);
}

// Clear custom endpoint, revert to native routing
async unstable_disableProvider(params: DisableProviderRequest): Promise<void> {
    if (params.providerId === "main") {
        await this.enqueueProviderUpdate(undefined);
    }
}
```

### Live Provider Switching (No Process Restart)

Unlike Codex which restarts the entire process, Claude Agent ACP **recreates sessions in-place**:

1. `enqueueProviderUpdate(config)` stores the new `providerConfig`
2. All active sessions are paused (serialized via a promise chain)
3. Each session's SDK query is torn down
4. New queries are created with updated env vars from `createEnvForProvider()`
5. Sessions resume with the new backend, using stored `creationParams`
6. Context window cache is re-keyed per the new `providerCacheKey`

### Logout Behavior

```typescript
async logout(): Promise<void> {
    this.gatewayAuthRequest = null;   // Clear gateway auth
    this.providerConfig = null;        // Clear providers/set config
    this.contextWindowCache.clear();   // Purge (entitlements are per-org/tier)
    // Runs: claude auth logout (clears keychain/config credentials)
}
```

---

## Side-by-Side Comparison

| Aspect | Codex ACP | Claude Agent ACP |
|---|---|---|
| **Protocol** | OpenAI-compatible only | Anthropic, Bedrock, Vertex |
| **Gateway auth method ID** | `"gateway"` | `"gateway"`, `"gateway-bedrock"` |
| **Gateway capability check** | `clientCapabilities.auth._meta.gateway === true` | Same |
| **Custom endpoint fields** | `baseUrl`, `headers`, `providerName` | `baseUrl`, `headers` |
| **Provider ID** | `"openai"` | `"main"` |
| **Default endpoint** | `https://api.openai.com/v1` | `https://api.anthropic.com` |
| **Env var override** | `CODEX_API_KEY`, `OPENAI_API_KEY` | `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_BEDROCK`, etc. |
| **Config injection** | Into `config.model_providers["custom-gateway"]` | Into env vars for SDK subprocess |
| **Provider change** | Full process restart | In-place session recreation |
| **Supported protocols** | `["openai"]` | `["anthropic", "bedrock", "vertex"]` |
| **Extra header injected** | `X-Client-Feature-ID: codex` | None |
| **Vertex support** | No | Yes (with `projectId` + `region`) |

---

## How to Use Custom Endpoints in Practice

### Codex ACP — Point at a custom OpenAI-compatible endpoint

**Option 1: Environment variable**
```bash
OPENAI_API_KEY=sk-xxx MODEL_PROVIDER=custom npx @agentclientprotocol/codex-acp
```

**Option 2: Pre-configured gateway auth**
```bash
DEFAULT_AUTH_REQUEST='{"methodId":"gateway","_meta":{"gateway":{"baseUrl":"https://my-llm-proxy.example.com/v1","headers":{"Authorization":"Bearer my-token"},"providerName":"My LLM"}}}' \
npx @agentclientprotocol/codex-acp
```

**Option 3: Client sends gateway auth at session init**
The IDE sends an ACP `authenticate` request with the gateway method — no server-side env vars needed.

### Claude Agent ACP — Point at a custom Anthropic-compatible endpoint

**Option 1: Environment variable**
```bash
ANTHROPIC_BASE_URL=https://my-anthropic-proxy.example.com npx claude-agent-acp
```

**Option 2: Bedrock**
```bash
CLAUDE_CODE_USE_BEDROCK=1 ANTHROPIC_BEDROCK_BASE_URL=https://my-bedrock-endpoint.example.com npx claude-agent-acp
```

**Option 3: Vertex**
```bash
CLAUDE_CODE_USE_VERTEX=1 ANTHROPIC_VERTEX_BASE_URL=https://my-vertex-endpoint.example.com npx claude-agent-acp
```

**Option 4: Client sends gateway auth at session init**
The IDE sends an ACP `authenticate` request with `methodId: "gateway"` or `"gateway-bedrock"`.

**Option 5: Runtime providers API**
The client calls `providers/set` with `{ providerId: "main", apiType: "anthropic", baseUrl: "...", headers: {...} }`.
