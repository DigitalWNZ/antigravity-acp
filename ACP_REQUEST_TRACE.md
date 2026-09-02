# ACP Gateway Request Trace: All Three Hops

Captured from a live test run of the full chain:
ACP Client → ACP Server → Local Gateway Proxy → Gemini Backend

Test message: `"hi"`

---

## Hop 1: ACP Client → ACP Server

**Transport**: stdio (JSON-RPC 2.0)

The ACP client sends the user's message as a simple text prompt over the JSON-RPC protocol:

```json
{
  "jsonrpc": "2.0",
  "method": "prompt",
  "params": {
    "session_id": "e9e30dc9-6964-44e6-81e5-453685951318",
    "prompt": [
      {"type": "text", "text": "hi"}
    ]
  },
  "id": 3
}
```

This is the ACP protocol layer — the client only sends the raw user text. All system instructions, tools, generation config, and model selection are added by the ACP server.

---

## Hop 2: ACP Server → Local Gateway Proxy

**Transport**: HTTP POST (Gemini Developer API format)

```
POST http://localhost:8080/v1beta/models/gemini-3.7-flash:streamGenerateContent?alt=sse
```

### Headers

```
Host: localhost:8080
Content-Type: application/json
Content-Length: 44255
X-Goog-Api-Key: AIzaSyC7zMM1OC_HUa4K99nYmbaul-mOfizPE6o
X-Goog-Api-Client: google-genai-sdk/1.68.0 gl-go/go1.28-20260721-RC01 cl/951519500 ...
User-Agent: google-antigravity-sdk/0.0.0-dev python/3.14.5 client-os/linux ... acp-test-client/0.1.0
Accept-Encoding: gzip
```

Key headers:
- `X-Goog-Api-Key` — the `GEMINI_API_KEY` env var value, injected by the GenAI SDK
- `X-Goog-Api-Client` — SDK version and build info
- `User-Agent` — identifies the Antigravity ACP server and client surface

### Body (44,255 bytes)

```json
{
  "systemInstruction": {
    "parts": [
      {
        "text": "<identity>\nYou are Antigravity, a powerful agentic AI assistant designed by the Google Deepmind team.\nThe task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.\nThe USER will send you requests, which you must always prioritize addressing...\n</identity>\n<user_information>\nThe USER's OS version is linux.\nThe user has 5 active workspaces...\n</user_information>\n..."
      }
    ]
  },
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "<USER_REQUEST>\nhi\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-09-01T06:22:02Z.\n</ADDITIONAL_METADATA>"
        }
      ]
    }
  ],
  "generationConfig": {
    "candidateCount": 1,
    "maxOutputTokens": 65535,
    "stopSequences": [
      "<|user|>",
      "<|bot|>",
      "<|context_request|>",
      "<|endoftext|>",
      "<|end_of_turn|>"
    ],
    "temperature": 1,
    "thinkingConfig": {
      "includeThoughts": true,
      "thinkingLevel": "high"
    },
    "topK": 50,
    "topP": 1
  },
  "tools": [
    {
      "functionDeclarations": [
        {"name": "ask_question", "description": "Use this tool to ask the user one or more multiple-choice questions..."},
        {"name": "define_subagent", "description": "Defines a new type of subagent that can be invoked via invoke_subagent..."},
        {"name": "find_by_name", "description": "Search for files and subdirectories within a specified directory using fd..."},
        {"name": "generate_image", "description": "Generate an image or edit existing images based on a text prompt..."},
        {"name": "grep_search", "description": "Use ripgrep to find exact pattern matches within files or directories..."},
        {"name": "invoke_subagent", "description": "Invokes one or more subagents by name with a single tool call..."},
        {"name": "list_dir", "description": "List the contents of a directory..."},
        {"name": "manage_subagents", "description": "Manage existing subagents..."},
        {"name": "read_url_content", "description": "Fetch content from a URL via HTTP request..."},
        {"name": "replace_file_content", "description": "Use this tool to edit an existing file..."},
        {"name": "run_command", "description": "PROPOSE a command to run on behalf of the user..."},
        {"name": "search_web", "description": "Performs a web search for a given query..."},
        {"name": "send_message", "description": "Send a message to another agent..."},
        {"name": "write_to_file", "description": "Use this tool to create new files..."},
        {"name": "view_file", "description": "View the contents of a file within the allowed directories..."}
      ]
    }
  ],
  "toolConfig": {
    "functionCallingConfig": {
      "mode": "AUTO"
    }
  },
  "sessionId": "-3750763034362895579"
}
```

### What the ACP Server Adds

The ACP server transforms the simple `"hi"` from Hop 1 into a full Gemini API request by adding:

| Field | Source | Size |
|---|---|---|
| `systemInstruction` | Hardcoded Antigravity identity prompt + workspace info | ~5KB |
| `contents[0].parts[0].text` | Wraps user message in `<USER_REQUEST>` tags + adds metadata (timestamp) | ~100B |
| `generationConfig` | Default config with thinking enabled (high level) | ~300B |
| `tools` | 15 function declarations (find, grep, edit, run_command, etc.) | ~38KB |
| `toolConfig` | Function calling mode: AUTO | ~50B |
| `sessionId` | Internal session tracking | ~20B |

The tools declarations account for ~86% of the 44KB request body.

---

## Hop 3: Local Gateway Proxy → Gemini Backend

**Transport**: HTTP POST (same Gemini Developer API format)

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.7-flash:streamGenerateContent?alt=sse&key=AIzaSyC7zMM1OC_HUa4K99nYmbaul-mOfizPE6o
```

### Headers

```
Content-Type: application/json
```

### Body

**Identical to Hop 2** — the proxy forwards the request body unchanged.

### What Changes Between Hop 2 and Hop 3

| Aspect | Hop 2 (Server → Proxy) | Hop 3 (Proxy → Gemini) |
|---|---|---|
| **URL host** | `localhost:8080` | `generativelanguage.googleapis.com` |
| **API key location** | `X-Goog-Api-Key` header | `key=` query parameter |
| **X-Goog-Api-Client** | Present (SDK version info) | Dropped |
| **User-Agent** | Present (Antigravity SDK info) | Dropped |
| **Accept-Encoding** | `gzip` | Dropped |
| **Request body** | Original | **Unchanged** (passed through) |

---

## Response Flow (Gemini → Proxy → ACP Server → Client)

```
Gemini Backend
    │  SSE stream (text/event-stream)
    │  data: {"candidates":[{"content":{"role":"model","parts":[{"text":"..."}]}}],...}
    ▼
Local Gateway Proxy
    │  SSE stream passthrough (unchanged)
    ▼
ACP Server
    │  Parses Gemini response, extracts text/tool_calls
    │  Sends JSON-RPC notifications over stdio:
    │    session/update (AgentMessageChunk with text)
    │    session/update (AgentThoughtChunk with thinking)
    ▼
ACP Client
    │  Renders text to terminal
    ▼
User sees: "Hello! How can I assist you today?"
```

---

## Summary: Request Body Transformation

```
Hop 1 (ACP Protocol):     {"prompt": [{"text": "hi"}]}                    ~100 bytes
                                      ↓
                           ACP Server adds system prompt, tools, config
                                      ↓
Hop 2 (Gemini API):       {"systemInstruction":..., "contents":...,       ~44,255 bytes
                            "tools":..., "generationConfig":...}
                                      ↓
                           Proxy forwards body unchanged
                                      ↓
Hop 3 (Gemini API):       Same body as Hop 2                              ~44,255 bytes
```

The gateway proxy is transparent for the request body — it only changes the URL and auth mechanism.
