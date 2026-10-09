# Antigravity ACP Server: Auth URLs & OAuth Configuration

All auth URLs, OAuth client IDs, scopes, and token paths used by the Antigravity ACP server. Extracted from the server binary (`agy_acp_server.par`) using `strings`.

---

## OAuth Endpoints

| Endpoint | URL |
|---|---|
| Authorization | `https://accounts.google.com/o/oauth2/v2/auth` |
| Token exchange | `https://oauth2.googleapis.com/token` |
| Token info | `https://oauth2.googleapis.com/tokeninfo` |
| Device code (fallback) | `https://oauth2.googleapis.com/device/code` |

---

## OAuth Client IDs

Three distinct OAuth client IDs are embedded in the binary, one per auth flow:

### oauth-personal (consumer)

| Field | Value |
|---|---|
| Client ID | `1071006060591-<REDACTED>.apps.googleusercontent.com` |
| Client Secret | `GOCSPX-<REDACTED>` |
| Keychain Account | `antigravity-acp` |
| Source Module | `ccpa_connection/ccpa_client.py` |
| Constant | `_DEFAULT_CLIENT_ID` |

### oauth-business (Gemini Enterprise)

| Field | Value |
|---|---|
| Client ID | `884354919052-<REDACTED>.apps.googleusercontent.com` |
| Client Secret | `GOCSPX-<REDACTED>` |
| Keychain Account | `antigravity-acp-business` |
| Source Module | `baic_connection/business_auth.py` |
| Constant | `_BUSINESS_CLIENT_ID` |

### agent-platform (ADC / gcloud)

| Field | Value |
|---|---|
| Client ID | `764086051850-<REDACTED>.apps.googleusercontent.com` |
| Managed by | Google Cloud SDK (`gcloud`) |
| Constant | `CLOUD_SDK_CLIENT_ID` |

Note: The personal and business client IDs are marked in the source as "for internal testing; the final client ID is pending (b/531797807)." They may change in future server releases.

---

## OAuth Scopes

### oauth-personal

```
https://www.googleapis.com/auth/cloud-platform
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/aicode
```

The `aicode` scope is **consumer-only** — it grants access to the free-tier AI coding features.

### oauth-business

```
https://www.googleapis.com/auth/cloud-platform
https://www.googleapis.com/auth/userinfo.email
```

Business scopes deliberately **exclude** `auth/aicode` (consumer-only, per jetski's `getBusinessAuthScopes`). Enterprise access is validated through Gemini Enterprise licensing instead.

### agent-platform

Uses whatever scopes are granted by `gcloud auth application-default login`, typically:

```
https://www.googleapis.com/auth/cloud-platform
```

---

## Token File Paths

All token files are stored under `$GEMINI_HOME/antigravity-acp/` (default: `~/.gemini/antigravity-acp/`).

| Auth Type | Token File | Constant |
|---|---|---|
| oauth-personal | `acp_token.json` | `_CONSUMER_TOKEN_FILE_NAME` |
| oauth-business | `acp_business_token.json` | `_BUSINESS_TOKEN_FILE_NAME` |
| agent-platform | `~/.config/gcloud/application_default_credentials.json` | Managed by gcloud SDK |

### Token file format (oauth-personal / oauth-business)

```json
{
  "client_id": "<OAuth client ID>",
  "client_secret": "<OAuth client secret>",
  "refresh_token": "<refresh token from OAuth flow>",
  "token_uri": "https://oauth2.googleapis.com/token",
  "scopes": ["<granted scopes>"]
}
```

### Clearing tokens (to switch users)

```bash
# Clear personal OAuth token
rm -f ~/.gemini/antigravity-acp/acp_token.json

# Clear business OAuth token
rm -f ~/.gemini/antigravity-acp/acp_business_token.json

# Clear cached sessions
rm -rf ~/.gemini/antigravity-acp/conversations/
```

---

## OAuth Flow

### Browser-based flow (default)

1. Server starts a local HTTP listener on a random port (e.g. `127.0.0.1:33005`)
2. Server opens browser to:
   ```
   https://accounts.google.com/o/oauth2/v2/auth
     ?client_id=<CLIENT_ID>
     &scope=<SCOPES>
     &response_type=code
     &redirect_uri=http://127.0.0.1:<PORT>
     &access_type=offline
     &prompt=consent
   ```
3. User signs in with Google account
4. Browser redirects to `http://127.0.0.1:<PORT>/?code=<AUTH_CODE>&scope=<SCOPES>&state=<STATE>`
5. Server exchanges the auth code for a refresh token via `https://oauth2.googleapis.com/token`
6. Token is cached to disk for future sessions

### Device code flow (fallback)

When browser auth is unavailable, the server can use device code flow via `https://oauth2.googleapis.com/device/code`.

### Remote VM workaround

On remote VMs, the browser opens on the local machine but the callback listener runs on the VM. Copy the redirect URL from the browser and `curl` it on the VM:

```bash
curl "http://127.0.0.1:<PORT>/?state=...&code=...&scope=..."
```

---

## Internal Code Structure

| Module Path | Purpose |
|---|---|
| `acp_server/ccpa_connection/ccpa_client.py` | Personal OAuth flow, CCPA onboarding, `loadCodeAssist` |
| `acp_server/baic_connection/business_auth.py` | Business/Enterprise OAuth flow, `BusinessAuthManager` |
| `acp_server/baic_connection/licensing.py` | Gemini Enterprise license validation |
| `acp_server/baic_connection/baic_client.py` | Business AI Companion client |
| `acp_server/baic_connection/converters.py` | Request/response format conversion |
| `acp_server/baic_connection/proxy_server.py` | Proxy server for business connections |
| `acp_server/paths.py` | Token file path resolution (`GEMINI_HOME` handling) |
| `acp_server/main.py` | Auth method selection and server entry point |

Note: All module paths are under `google3/cloud/developer_experience/antigravity_extensions/` inside the binary.

---

## Investigation Method

All information was extracted using `strings` on the binary `agy_acp_server.par` — no decompilation was performed. The binary is a self-extracting Python archive (`.par` format) containing Google-internal Python packages and a bundled Python runtime.
