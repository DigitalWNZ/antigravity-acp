# Why `oauth-business` Does Not Require ADC

A customer using `oauth-business` auth was told ADC (Application Default Credentials) is needed. This is incorrect — ADC is only required for the `agent-platform` auth method. This document explains the confusion and the fix.

---

## The Four Auth Methods

The Antigravity ACP server advertises four auth methods during `initialize()`:

| ID | Display Name | Description | Requires ADC? |
|---|---|---|---|
| `oauth-personal` | Log in with Google | Personal Google account | No |
| `oauth-business` | Log in with Gemini Enterprise | Gemini Enterprise account | **No** |
| `gemini-api-key` | Gemini API key | API key from Google AI Studio | No |
| `agent-platform` | Gemini Enterprise Agent Platform | Formerly Vertex AI | **Yes** |

Only `agent-platform` requires ADC. The `oauth-business` method uses its own OAuth flow with a dedicated client ID and stores tokens at `~/.gemini/antigravity-acp/acp_business_token.json`.

---

## How `oauth-business` Auth Works (No ADC)

```
1. User selects "Log in with Gemini Enterprise" (oauth-business)
              ↓
2. Server opens browser → Google OAuth consent screen
   Client ID: 884354919052-<REDACTED>.apps.googleusercontent.com
   Scopes: cloud-platform, userinfo.email
              ↓
3. User signs in → server receives auth code → exchanges for refresh token
   Token stored: ~/.gemini/antigravity-acp/acp_business_token.json
              ↓
4. Server calls resolve_license(access_token, project, location)
   → Fetches Gemini Enterprise licenses via BAIC API
   → Finds matching license for configured project/location
   → Resolves user_tier (e.g. "gcp-ge-plus-tier")
              ↓
5. Server creates VertexEndpoint + BAIC loopback proxy
   → Proxy injects OAuth token into requests
   → Routes to cloudcode-pa.googleapis.com (CCPA backend)
              ↓
6. Session created — no ADC involved at any step
```

## How `agent-platform` Auth Works (Requires ADC)

```
1. User selects "Gemini Enterprise Agent Platform" (agent-platform)
              ↓
2. Server checks _vertex_config():
   - Reads GOOGLE_API_KEY env var (express mode), OR
   - Reads gcp.project + gcp.location from settings.json
   - Requires ADC via `gcloud auth application-default login`
              ↓
3. Server creates VertexEndpoint with ADC credentials
   → Routes directly to {location}-aiplatform.googleapis.com
              ↓
4. Session created — ADC is the credential source
```

---

## Why the Customer Is Confused

### Likely Cause 1: Wrong auth method selected

Both methods have "Gemini Enterprise" in the display name:

- **"Log in with Gemini Enterprise"** → `oauth-business` (OAuth flow, no ADC)
- **"Gemini Enterprise Agent Platform"** → `agent-platform` (needs ADC)

If the customer (or their IDE) selects `agent-platform` instead of `oauth-business`, the server will require ADC. The naming overlap makes this easy to confuse.

### Likely Cause 2: Missing project/location in settings.json

For `oauth-business`, the license resolution requires **both** `gcp.project` and `gcp.location` in `settings.json`. Without them, the server raises:

```
NoConfigNoLicenseError: No Gemini Enterprise license found and no project configured.
```

This error does not mention ADC, but the customer might interpret "no project configured" as needing to run `gcloud auth application-default login` (which sets a default project). In reality, they just need to add the project to `settings.json`.

### Likely Cause 3: IDE auto-selects wrong method

Some IDEs auto-detect available credentials. If `gcloud auth application-default login` was previously run, the IDE might auto-select `agent-platform` (since ADC is present) instead of `oauth-business`. This would route through Vertex AI, which requires ADC, instead of the BAIC/CCPA path.

---

## Correct Configuration for `oauth-business`

### settings.json

```json
{
  "auth": {
    "type": "oauth-business"
  },
  "gcp": {
    "project": "<GCP_PROJECT_ID>",
    "location": "global"
  }
}
```

Location: `~/.gemini/antigravity-acp/settings.json`

### Requirements

| Requirement | Details |
|---|---|
| `auth.type` | Must be `"oauth-business"` (not `"agent-platform"`) |
| `gcp.project` | GCP project ID with Gemini Enterprise subscription |
| `gcp.location` | Subscription location: `"global"`, `"eu"`, or `"us"` |
| Gemini Enterprise license | The project must have an active Gemini Enterprise seat for the user |
| ADC | **Not required** |
| `gcloud auth application-default login` | **Not required** |

### What IS required

1. The binary `agy_acp_server.par`
2. A `settings.json` with `auth.type`, `gcp.project`, and `gcp.location`
3. A Google account with a Gemini Enterprise license on the configured project
4. Browser access to complete the OAuth sign-in flow (first time only)

### What is NOT required

- `gcloud` CLI
- `gcloud auth application-default login`
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable
- Service account keys
- Any form of ADC

---

## Comparison: Auth Method vs Credential Source

| Auth Method | Credential Source | Token Storage | Backend |
|---|---|---|---|
| `oauth-business` | OAuth browser flow (dedicated client ID) | `acp_business_token.json` | CCPA via BAIC proxy |
| `agent-platform` | ADC (`gcloud auth application-default login`) or `GOOGLE_API_KEY` | `application_default_credentials.json` | Vertex AI direct |

These are two completely different credential pipelines. Mixing them up (using `agent-platform` when you mean `oauth-business`) is the most common reason a customer is told ADC is needed.

---

## Troubleshooting Checklist

If a customer using `oauth-business` is told ADC is needed:

1. **Check `settings.json`**: Is `auth.type` set to `"oauth-business"` or `"agent-platform"`?
   ```bash
   cat ~/.gemini/antigravity-acp/settings.json
   ```

2. **Check both project and location are set**: Missing either one causes `NoConfigNoLicenseError`
   ```json
   {
     "gcp": {
       "project": "my-project-id",
       "location": "global"
     }
   }
   ```

3. **Check which auth method the IDE selected**: The IDE logs or ACP traffic should show the `method_id` in the `authenticate` request. Look for `"oauth-business"` vs `"agent-platform"`.

4. **Check the license**: The user must have a Gemini Enterprise seat on the configured project. Without it, `resolve_license` fails with `LicenseUnavailableError`:
   ```
   No license for project <PROJECT> / location <LOCATION>, and self-assign failed (HTTP 403)
   ```

5. **Clear cached token and retry**: If the token is stale or was obtained with the wrong account:
   ```bash
   rm -f ~/.gemini/antigravity-acp/acp_business_token.json
   ```

---

## Source Code References

All code paths verified from `agy_acp_server.par` source (extracted from ZIP payload):

| File | Lines | What It Shows |
|---|---|---|
| `server.py` | 2106-2132 | Auth method display names (both say "Gemini Enterprise") |
| `server.py` | 2383-2494 | `authenticate()` dispatch — oauth-business uses `_ensure_business_logged_in()` |
| `server.py` | 2598-2611 | `_assert_authenticated()` — oauth-business triggers OAuth, not ADC |
| `server.py` | 3550-3574 | `_create_agent_config()` — oauth-business creates `VertexEndpoint` + BAIC proxy |
| `server.py` | 3590-3610 | `_create_agent_config()` — agent-platform creates `VertexEndpoint` + ADC direct |
| `business_auth.py` | 57-167 | `BusinessAuthManager` — uses OAuth token, never ADC |
| `licensing.py` | 149-198 | `resolve_license()` — requires project+location, raises `NoConfigNoLicenseError` without them |
| `proxy_agent_config.py` | 1-135 | `ProxyAgentConfig` — BAIC proxy injects OAuth token, no ADC |
