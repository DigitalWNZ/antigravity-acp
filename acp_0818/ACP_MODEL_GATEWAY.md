# ACP Model Gateway: How Antigravity, Claude, and Codex Configure Endpoints

A comparison of how each ACP server implementation handles model endpoint routing — where the backend URL comes from, how auth selects the endpoint, and what users can customize.

---

## Summary

| ACP Server | Package | Endpoint Configuration | User Customizable? |
|---|---|---|---|
| **Antigravity** | `agy_acp_server.par` (binary) | Hardcoded in binary | No (env override for staging only) |
| **Claude Agent** | `@agentclientprotocol/claude-agent-acp` | Env vars + gateway auth + CLI providers API | Yes |
| **Codex** | `@agentclientprotocol/codex-acp` | Env vars + gateway auth | Yes |

---

## 1. Antigravity ACP Server (Google)

**Source:** Proprietary binary (`agy_acp_server.par`, ~1.5 GB)

Endpoints are **hardcoded** in the binary. The auth type in `settings.json` determines which backend is used:

```
auth.type                    Backend Endpoint
─────────────────────────    ──────────────────────────────────────────
oauth-personal               https://cloudcode-pa.googleapis.com (CCPA)
oauth-business               https://cloudcode-pa.googleapis.com (CCPA)
agent-platform (vertex-ai)   https://{location}-aiplatform.googleapis.com
gemini-api-key               https://generativelanguage.googleapis.com
```

### Key details
- **CCPA** (Cloud Code Pair Assistance) — same backend as Gemini in VS Code/JetBrains
- **Vertex AI** — endpoint constructed from `gcp.location` (e.g. `us-central1-aiplatform.googleapis.com`)
- **Generative Language API** — used with Gemini API keys from Google AI Studio
- **No user endpoint configuration** — the only env override is `AGY_ACP_CCPA_BASE_URL` (for Google-internal staging)
- Model references found in binary: `gemini-3.6-flash`, `antigravity-preview-05-2026`, `gemini-3-pro-preview`

### Internal code path
```
google3/cloud/developer_experience/antigravity_extensions/acp_server/ccpa_connection/ccpa_client.py
  → DEFAULT_CCPA_BASE_URL = "https://cloudcode-pa.googleapis.com"
  → _PROD_ENDPOINT = ccpa_client.DEFAULT_CCPA_BASE_URL
```

---

## 2. Claude Agent ACP (Anthropic / Zed)

**Source:** Open-source TypeScript — `@agentclientprotocol/claude-agent-acp`
**GitHub:** https://github.com/agentclientprotocol/claude-agent-acp
**Dependencies:** `@anthropic-ai/claude-agent-sdk`, `@agentclientprotocol/sdk`

### Endpoint Configuration

Three API providers are supported, each with an env var to override the base URL:

| Provider | Env: Enable | Env: Base URL | Default |
|---|---|---|---|
| **Anthropic (direct)** | *(default)* | `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` |
| **AWS Bedrock** | `CLAUDE_CODE_USE_BEDROCK=1` | `ANTHROPIC_BEDROCK_BASE_URL` | `https://bedrock-runtime.amazonaws.com` |
| **Google Vertex** | `CLAUDE_CODE_USE_VERTEX=1` | `ANTHROPIC_VERTEX_BASE_URL` | `https://aiplatform.googleapis.com` |

### Provider Resolution Order

The server resolves the active provider in this priority:

1. **Gateway auth request** — if the client sent a gateway auth with `baseUrl` and `headers`
2. **`CLAUDE_CODE_USE_BEDROCK`** — env var enables Bedrock routing
3. **`CLAUDE_CODE_USE_VERTEX`** — env var enables Vertex routing
4. **Fallback** — Anthropic direct API with `ANTHROPIC_BASE_URL`

### Authentication Methods

| Method ID | Description | When Available |
|---|---|---|
| `claude-ai-login` | OAuth via Claude subscription | Non-remote environments |
| `console-login` | OAuth via Anthropic Console | Non-remote environments |
| `gateway` | Custom Anthropic-protocol proxy | Client advertises `auth._meta.gateway` |
| `gateway-bedrock` | Custom Bedrock-protocol proxy | Client advertises `auth._meta.gateway` |

### Gateway Auth (Custom Proxy)

Clients that support custom endpoints can send a **gateway auth request** with:

```typescript
interface GatewayAuthRequest {
  baseUrl: string;               // Custom API endpoint URL
  headers: Record<string, string>; // Custom headers (e.g. API key)
  protocol: "anthropic" | "bedrock" | "vertex";
}
```

This is converted into a `ProviderConfig`:

```typescript
interface ProviderConfig {
  apiType: "anthropic" | "bedrock" | "vertex";
  baseUrl: string;
  headers: Record<string, string>;
  vertex?: { projectId: string; region: string };
}
```

### Providers API (Runtime Configuration)

The server exposes two ACP extension methods:

- **`providers/set`** — set a custom provider at runtime (validates URL and protocol)
- **`providers/disable`** — clear custom provider, restore native routing

When a provider changes, all open sessions are recreated.

### Key Design Points
- Provider config is **process-scoped**, not per-session
- The API key flows through the Claude CLI's own credential store or gateway headers
- Supported protocols: `["anthropic", "bedrock", "vertex"]`
- Context window cache is keyed per-provider (same model can have different windows behind different base URLs)
- Config directory: `CLAUDE_CONFIG_DIR` (default: `~/.claude`)

---

## 3. Codex ACP (OpenAI)

**Source:** Open-source TypeScript — `@agentclientprotocol/codex-acp`
**GitHub:** https://github.com/agentclientprotocol/codex-acp
**Dependencies:** `@openai/codex`, `@agentclientprotocol/sdk`

### Environment Variables

| Variable | Purpose |
|---|---|
| `CODEX_API_KEY` | API key (takes precedence over `OPENAI_API_KEY`) |
| `OPENAI_API_KEY` | Fallback API key |
| `MODEL_PROVIDER` | Model provider passed to Codex for new sessions |
| `CODEX_CONFIG` | JSON object merged into session config |
| `CODEX_PATH` | Path to custom Codex binary |
| `DEFAULT_AUTH_REQUEST` | ACP auth request JSON for pre-configured auth |
| `INITIAL_AGENT_MODE` | `read-only`, `agent`, or `agent-full-access` |
| `NO_BROWSER` | Hide browser-based ChatGPT auth |
| `APP_SERVER_LOGS` | Directory for adapter logs |

### Authentication Methods

| Method ID | Description | When Available |
|---|---|---|
| `api-key` | OpenAI API key | Always |
| `chat-gpt` | Browser-based ChatGPT OAuth | Unless `NO_BROWSER` is set |
| `chat-gpt-device-code` | Device code flow (paste URL + code) | Client supports URL elicitation |
| `gateway` | Custom OpenAI-compatible endpoint | Client advertises `auth._meta.gateway` |

### Gateway Auth (Custom Proxy)

The gateway auth allows connecting to any **OpenAI-compatible API endpoint**:

```typescript
interface GatewayAuthRequest {
  baseUrl: string;               // Custom API endpoint URL (e.g. your proxy)
  headers: Record<string, string>; // Custom HTTP headers for auth
  providerName?: string;          // Optional provider identifier
}
```

Gateway metadata: `{ protocol: "openai", restartRequired: "false" }`

This enables using Codex with:
- Self-hosted OpenAI-compatible models
- Enterprise proxy endpoints
- Alternative LLM providers with OpenAI-compatible APIs

---

## Comparison: How to Point Each Server at a Custom Endpoint

### Antigravity
**Not possible.** Endpoints are hardcoded. You can only choose which Google backend to use via `auth.type` in `settings.json`.

### Claude Agent ACP
**Option A — Environment variable:**
```bash
ANTHROPIC_BASE_URL=https://my-proxy.example.com npx claude-agent-acp
```

**Option B — Bedrock/Vertex:**
```bash
CLAUDE_CODE_USE_BEDROCK=1 ANTHROPIC_BEDROCK_BASE_URL=https://my-bedrock.example.com npx claude-agent-acp
```

**Option C — Gateway auth (client sends at session init):**
The IDE/client sends a gateway auth request with `baseUrl` and `headers`. No env vars needed.

**Option D — Providers API (runtime):**
Client calls `providers/set` with a `ProviderConfig` to change the backend mid-session.

### Codex ACP
**Option A — Environment variable:**
```bash
CODEX_API_KEY=sk-xxx OPENAI_API_KEY=sk-xxx npx @agentclientprotocol/codex-acp
```

**Option B — Model provider:**
```bash
MODEL_PROVIDER=my-provider npx @agentclientprotocol/codex-acp
```

**Option C — Gateway auth (client sends at session init):**
The IDE/client sends a gateway auth request with `baseUrl`, `headers`, and optional `providerName`.

**Option D — Pre-configured auth:**
```bash
DEFAULT_AUTH_REQUEST='{"method":"gateway","baseUrl":"https://my-proxy.example.com","headers":{"Authorization":"Bearer xxx"}}' npx @agentclientprotocol/codex-acp
```
