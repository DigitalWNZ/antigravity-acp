# Antigravity ACP Server Internals: Endpoint Routing & Model Gateway

How the ACP server routes requests to Google's backend services. None of this is user-configurable — it's all hardcoded in the server binary (`agy_acp_server.par`).

---

## Overview

The ACP server is a **protocol translator**:
- **Input:** ACP (JSON-RPC 2.0 over stdio) from the client
- **Output:** REST/gRPC calls to one of three Google backend services

The backend is selected automatically based on `auth.type` in `~/.gemini/antigravity-acp/settings.json`. There is no endpoint URL configuration for users.

---

## Endpoint Routing by Auth Type

```
settings.json auth.type
        │
        ├── oauth-personal ──────► cloudcode-pa.googleapis.com (CCPA)
        ├── oauth-business ──────► cloudcode-pa.googleapis.com (CCPA)
        ├── agent-platform ──────► {location}-aiplatform.googleapis.com (Vertex AI)
        └── gemini-api-key ──────► generativelanguage.googleapis.com (Gemini API)
```

### 1. CCPA — Cloud Code Pair Assistance (`oauth-personal`, `oauth-business`)

| Field | Value |
|---|---|
| Production endpoint | `https://cloudcode-pa.googleapis.com` |
| Daily/staging endpoint | `https://daily-cloudcode-pa.googleapis.com` |
| Env override | `AGY_ACP_CCPA_BASE_URL` |
| Onboarding RPC | `loadCodeAssist` |
| Source module | `google3/cloud/developer_experience/antigravity_extensions/acp_server/ccpa_connection/ccpa_client.py` |

This is the same backend that powers **Gemini in IDEs** (VS Code, JetBrains, Xcode). The server calls `loadCodeAssist` to:
1. Onboard the user
2. Resolve a Google-managed project ID (or use the user's configured project)
3. Obtain the CCPA endpoint URL for subsequent requests

The default URL is set via `DEFAULT_CCPA_BASE_URL` in `ccpa_client.py`, and the production endpoint is `_PROD_ENDPOINT = ccpa_client.DEFAULT_CCPA_BASE_URL`.

### 2. Vertex AI / AI Platform (`agent-platform`)

| Field | Value |
|---|---|
| Endpoint pattern | `https://{location}-aiplatform.googleapis.com` |
| Global endpoint | `https://aiplatform.googleapis.com` |
| API path | `/v1beta1/projects/{project}/locations/{location}/agents` |
| Auth | ADC (`gcloud auth application-default login`) or `GOOGLE_API_KEY` |
| Alias | `vertex-ai` (legacy spelling, maps to `agent-platform`) |

The endpoint is constructed from `gcp.location` in settings.json:
- `location: "us-central1"` → `https://us-central1-aiplatform.googleapis.com`
- `location: "global"` → `https://aiplatform.googleapis.com`

A full lookup table of all regional `{region}-aiplatform.googleapis.com` URLs is embedded in the binary.

Resolved endpoint configuration is stored in a `_VertexConfig` dataclass with fields:
- `project` — GCP project ID (ADC flow only)
- `location` — GCP location (ADC flow only)
- `api_key` — express-mode key (API key flow only)

### 3. Generative Language API (`gemini-api-key`)

| Field | Value |
|---|---|
| Endpoint | `https://generativelanguage.googleapis.com` |
| API path | `/v1beta/interactions` |
| Auth | `GEMINI_API_KEY` environment variable |
| Staging endpoint | `https://autopush-generativelanguage.sandbox.googleapis.com` |

This endpoint also supports:
- `/v1beta/agents` — create/list/delete custom agents
- `/v1beta/interactions/{id}` — get/cancel/delete interactions

Example model references found in the binary: `gemini-3.6-flash`, `antigravity-preview-05-2026`, `deep-research-pro-preview-12-2025`.

---

## Where This Information Lives

All of the above is embedded in the server binary `agy_acp_server.par`. The `.par` format is a self-extracting Python archive that bundles:

- **Google-internal Python packages** at paths like:
  - `google3/cloud/developer_experience/antigravity_extensions/acp_server/main.py`
  - `google3/cloud/developer_experience/antigravity_extensions/acp_server/ccpa_connection/ccpa_client.py`
- **A Python runtime** — the binary is self-contained (~1.5 GB)
- **Hardcoded string constants** — endpoint URLs, auth method aliases, model names
- **Embedded API discovery documents** — full protobuf/REST schemas for the Google services

Key constants found in the binary:
```
DEFAULT_CCPA_BASE_URL = "https://cloudcode-pa.googleapis.com"
_PROD_ENDPOINT = ccpa_client.DEFAULT_CCPA_BASE_URL
_PROD_DAILY_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com"
CCPA_BASE_URL_ENV_VAR = "AGY_ACP_CCPA_BASE_URL"
_AUTH_METHOD_ALIASES = { "vertex-ai": "agent-platform" }
```

---

## Auth Method Aliases

| User-facing name | Canonical ID | Notes |
|---|---|---|
| `agent-platform` | `agent-platform` | Primary spelling |
| `vertex-ai` | `agent-platform` | Legacy alias, mapped internally |
| `oauth-personal` | `oauth-personal` | Personal Google account |
| `oauth-business` | `oauth-business` | Gemini Enterprise |
| `gemini-api-key` | `gemini-api-key` | Google AI Studio key |

---

## Environment Variable Overrides

| Variable | Purpose |
|---|---|
| `AGY_ACP_CCPA_BASE_URL` | Override the CCPA endpoint (for Google-internal staging/testing) |
| `GOOGLE_API_KEY` | API key for `agent-platform` auth |
| `GEMINI_API_KEY` | API key for `gemini-api-key` auth |
| `GOOGLE_CLOUD_PROJECT` | Override `gcp.project` in settings.json |
| `GOOGLE_CLOUD_LOCATION` | Override `gcp.location` in settings.json |
| `GEMINI_HOME` | Config directory (default: `~/.gemini`) |

---

## Investigation Method

This information was extracted by running `strings` on the binary (`agy_acp_server.par`) and searching for:
- URL patterns (`googleapis.com`, `cloudcode-pa`, `aiplatform`, `generativelanguage`)
- Python source fragments (class definitions, constant assignments, docstrings)
- Auth method identifiers and routing logic

The binary was not decompiled — only printable string extraction was used.
