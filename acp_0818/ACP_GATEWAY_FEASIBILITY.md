# Gateway Auth Feasibility: Can We Modify the Antigravity ACP Binary?

A verification of whether the information extractable from `agy_acp_server.par` is sufficient to add custom gateway auth support by patching the binary.

**Verdict: Yes, it is sufficient.** All five architectural layers have been fully read and understood from the `.par` archive.

---

## What the .par File Contains

The `.par` file is a self-extracting Python archive:
- **ELF binary header** (598 MB) — bundled Python interpreter
- **ZIP payload** (861 MB) — 10,404 files including 71 `.py` source files

The ZIP contains **full readable Python source code**, not just bytecode. Every file needed to understand the gateway routing is present and readable.

---

## Source Files Read

| File | Lines | Purpose | Status |
|---|---|---|---|
| `acp_server/main.py` | 152 | Entry point, creates `AgyAdapter()` | Fully read |
| `acp_server/config_options.py` | 157 | Session modes (default, auto_edit, yolo) | Fully read |
| `acp_server/settings.py` | 349 | Loads `settings.json`, reads `auth.type` | Fully read |
| `acp_server/server.py` | 5,065 | Main server class — all auth/routing logic | Key sections read (see below) |

All paths are under `google3/cloud/developer_experience/antigravity_extensions/` inside the archive.

### server.py Sections Read

| Section | Lines | Content |
|---|---|---|
| Auth constants | 647-684 | `AUTH_METHOD_*` constants, `_KNOWN_AUTH_TYPES`, `_AUTH_METHOD_ALIASES` |
| `_infer_auth_state()` | 862-882 | Reads `auth.type` from settings.json to set initial auth state |
| `class AgyAdapter` constructor | 1348-1427 | Instance vars: `_proxy_server`, `_baic_proxy_server`, `_auth_state`, `_oauth_mgr` |
| `_ensure_auth_state()` | 1926-1944 | Returns auth state, inferring from settings.json if not explicitly set |
| `initialize()` | 2079-2161 | Advertises 4 auth methods as `AuthMethodAgent` objects |
| `authenticate()` | 2383-2494 | if/elif dispatch: oauth → `_ensure_oauth_logged_in()`, business → `_ensure_business_logged_in()`, api-key → reads env var, agent-platform → checks `_vertex_config()` |
| `new_session()` | 2701-2780 | Creates session, calls `_assert_authenticated()` then `_create_agent_config()` |
| `_create_agent_config()` | 3215-3627 | **The critical routing logic** — builds endpoint + config based on auth method |
| `_create_proxy_agent_config()` | 3629-3679 | Starts CCPA loopback proxy, returns `ProxyAgentConfig` |
| `_create_baic_proxy_agent_config()` | 3681-3739 | Starts BAIC loopback proxy, returns `ProxyAgentConfig` |

---

## Architecture: How Auth Routes to Backend

The server uses a 3-step pipeline:

```
Step 1: authenticate()
    Sets _auth_state.method_id based on the chosen auth method
                    ↓
Step 2: new_session()
    Calls _assert_authenticated() to verify credentials
    Calls _create_agent_config() to build the session config
                    ↓
Step 3: _create_agent_config()
    Reads _auth_state.method_id and branches:

    oauth-business  →  VertexEndpoint + BAIC loopback proxy  →  ProxyAgentConfig
    oauth-personal  →  GeminiAPIEndpoint + CCPA loopback proxy  →  ProxyAgentConfig
    agent-platform  →  VertexEndpoint (direct, no proxy)  →  LocalAgentConfig
    gemini-api-key  →  GeminiAPIEndpoint (direct, no proxy)  →  LocalAgentConfig
```

### The Routing Code (server.py lines 3549-3627)

```python
auth_state = self._ensure_auth_state()

if auth_state.method_id == AUTH_METHOD_OAUTH_BUSINESS:
    # VertexEndpoint → BAIC loopback proxy → ProxyAgentConfig
    endpoint = sdk_types_module.VertexEndpoint(
        project=mgr.project, location=mgr.location, http_headers=custom_headers,
    )
    return self._create_baic_proxy_agent_config(common_args)

if auth_state.method_id == AUTH_METHOD_OAUTH:
    # GeminiAPIEndpoint → CCPA loopback proxy → ProxyAgentConfig
    endpoint = sdk_types_module.GeminiAPIEndpoint(
        api_key="dummy_api_key", http_headers=custom_headers,
    )
    return self._create_proxy_agent_config(common_args)

if auth_state.method_id == AUTH_METHOD_AGENT_PLATFORM:
    # VertexEndpoint → direct connection → LocalAgentConfig
    endpoint = sdk_types_module.VertexEndpoint(
        project=vertex_config.project, location=vertex_config.location,
        api_key=vertex_config.api_key, http_headers=custom_headers,
    )
    return LocalAgentConfig(**common_args), None

# API key mode (default)
# GeminiAPIEndpoint → direct connection → LocalAgentConfig
endpoint = sdk_types_module.GeminiAPIEndpoint(
    api_key=api_key, http_headers=api_key_custom_headers,
)
return LocalAgentConfig(**common_args), None
```

### Key SDK Types

| Type | Used By | Purpose |
|---|---|---|
| `VertexEndpoint` | oauth-business, agent-platform | Routes to Vertex AI / BAIC backends |
| `GeminiAPIEndpoint` | oauth-personal, gemini-api-key | Routes to CCPA / Generative Language backends |
| `ProxyAgentConfig` | oauth-personal, oauth-business | Wraps a `LocalAgentConfig` with a loopback proxy URL |
| `LocalAgentConfig` | agent-platform, gemini-api-key | Direct connection to endpoint (no proxy) |

### Loopback Proxy Pattern

For OAuth auth types, the server spins up a **local HTTP proxy** that:
1. Listens on `127.0.0.1:<random_port>`
2. Intercepts SDK requests
3. Injects the real OAuth access token (replacing the dummy API key)
4. Forwards to the actual Google backend

This is why `api_key="dummy_api_key"` appears — the SDK requires an API key in the config, but the proxy replaces it before the request hits the wire.

```
SDK → http://127.0.0.1:<port> (proxy) → https://cloudcode-pa.googleapis.com (CCPA)
      ↑ injects real token here
```

---

## Changes Required to Add Gateway Auth

Six modifications to the binary's Python source code:

### 1. Auth constant (server.py ~line 647)

```python
# Add new constant
AUTH_METHOD_GATEWAY = "gateway"

# Add to known types
_KNOWN_AUTH_TYPES = frozenset({
    AUTH_METHOD_OAUTH, AUTH_METHOD_OAUTH_BUSINESS,
    AUTH_METHOD_API_KEY, AUTH_METHOD_AGENT_PLATFORM,
    AUTH_METHOD_GATEWAY,  # NEW
})
```

### 2. AuthState dataclass

Add fields to store gateway config:

```python
@dataclasses.dataclass
class AuthState:
    method_id: str
    api_key: str | None = None
    gateway_base_url: str | None = None      # NEW
    gateway_headers: dict[str, str] | None = None  # NEW
```

### 3. initialize() — advertise gateway auth (server.py ~line 2132)

Add a 5th `AuthMethodAgent` entry:

```python
schema.AuthMethodAgent(
    id=AUTH_METHOD_GATEWAY,
    name="Custom Gateway",
    description="Connect to a custom LLM endpoint",
)
```

### 4. authenticate() — handle gateway auth (server.py ~line 2467)

Add new branch:

```python
elif method == AUTH_METHOD_GATEWAY:
    gateway_meta = kwargs.get("_meta", {}).get("gateway", {})
    base_url = gateway_meta.get("baseUrl", "")
    headers = gateway_meta.get("headers", {})
    if not base_url:
        raise ValueError("Gateway auth requires a baseUrl")
    self._auth_state = AuthState(
        method_id=AUTH_METHOD_GATEWAY,
        gateway_base_url=base_url,
        gateway_headers=headers,
    )
```

### 5. _create_agent_config() — route to gateway (server.py ~line 3610)

Add new branch before the API key fallback:

```python
if auth_state.method_id == AUTH_METHOD_GATEWAY:
    # Route to custom gateway endpoint
    # Option A: Use GeminiAPIEndpoint with gateway URL (if Gemini-compatible)
    # Option B: Start a custom loopback proxy that forwards to the gateway
    # Option C: Use VertexEndpoint if the gateway speaks Vertex protocol
    endpoint = sdk_types_module.GeminiAPIEndpoint(
        api_key=auth_state.gateway_headers.get("x-api-key", "gateway"),
        http_headers={**custom_headers, **auth_state.gateway_headers},
    )
    text_target = self._build_mapped_model_target(model_id, endpoint)
    common_args["models"] = [text_target]
    return LocalAgentConfig(**common_args), None
```

### 6. settings.py — parse gateway config

Add support for:
```json
{
  "auth": { "type": "gateway" },
  "gateway": {
    "base_url": "https://my-llm-proxy.example.com/v1",
    "headers": { "Authorization": "Bearer sk-xxx" }
  }
}
```

---

## Patching the Binary

The `.par` file can be modified by:

1. **Split** the ELF header from the ZIP payload:
   ```bash
   # Find ZIP start (PK signature: 0x504b0304)
   ZIP_OFFSET=$(python3 -c "
   with open('agy_acp_server.par','rb') as f:
       data = f.read()
       print(data.index(b'PK\x03\x04'))
   ")
   dd if=agy_acp_server.par of=elf_header bs=1 count=$ZIP_OFFSET
   dd if=agy_acp_server.par of=payload.zip bs=1 skip=$ZIP_OFFSET
   ```

2. **Extract** the ZIP, modify `.py` files, delete corresponding `.pyc` files

3. **Repackage**: `cat elf_header new_payload.zip > agy_acp_server_patched.par`

4. **Make executable**: `chmod +x agy_acp_server_patched.par`

### Risks of Binary Patching

| Risk | Severity | Mitigation |
|---|---|---|
| Breaks on every server update | High | Must re-patch after each release |
| `.pyc` cache mismatch | Medium | Delete all `.pyc` files for modified `.py` files |
| SDK type changes | Medium | `VertexEndpoint`/`GeminiAPIEndpoint` API may change |
| Signature verification | Low | No signing observed in current binary |
| Google ToS | Unknown | Modifying the binary may violate terms of service |

---

## Recommendation

While binary patching is **technically feasible**, the **ACP Proxy approach (Option A from [ACP_GATEWAY_PROPOSAL.md](ACP_GATEWAY_PROPOSAL.md))** is strongly recommended:

| Approach | Maintenance | Reliability | Complexity |
|---|---|---|---|
| **Binary patching** | Re-patch every update | Fragile | Medium |
| **ACP Proxy** | Independent of binary | Robust | Medium |

The proxy sits between the client and the Antigravity binary, intercepts gateway auth, routes to custom endpoints, and passes through all other auth methods to the unmodified binary. No binary modification needed.

---

## Investigation Method

All source code was extracted from the `.par` archive using Python's `zipfile` module:

```python
import zipfile
z = zipfile.ZipFile('agy_acp_server.par')
content = z.read('google3/.../server.py').decode()
```

No decompilation or reverse engineering tools were used — the source code is stored as plain `.py` text files inside the ZIP payload.
