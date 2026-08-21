# Antigravity ACP Server Setup & Client Guide

Complete guide for setting up the Google Antigravity ACP Server with `agent-platform` authentication and calling it programmatically using the official ACP Python SDK.

## Prerequisites

- Python 3.10+ with `pip`
- Google Cloud project with Gemini Enterprise Agent Platform access
- Application Default Credentials (ADC) configured (`gcloud auth application-default login`)
- Linux x86_64 (adjust download URL for other platforms)

---

## Step 1: Configure Authentication

Create the settings directory and file:

```bash
mkdir -p ~/.gemini/antigravity-acp
```

Write the settings file at `~/.gemini/antigravity-acp/settings.json`:

```json
{
  "auth": {
    "type": "agent-platform"
  },
  "gcp": {
    "project": "<YOUR_GCP_PROJECT_ID>",
    "location": "<YOUR_GCP_REGION>"
  }
}
```

Replace `<YOUR_GCP_PROJECT_ID>` and `<YOUR_GCP_REGION>` with your values (e.g. `cloud-llm-preview1` and `global`).

### Authentication Options

| Auth Type | `auth.type` Value | Credentials |
|---|---|---|
| Google Account (personal) | `oauth-personal` | OAuth browser flow |
| Gemini Enterprise | `oauth-business` | OAuth + GCP project/location |
| Gemini API Key | `gemini-api-key` | `GEMINI_API_KEY` env var |
| Agent Platform (ADC) | `agent-platform` | ADC + GCP project/location |
| Agent Platform (API Key) | `agent-platform` | `GOOGLE_API_KEY` env var |

### Environment Variables (Optional Overrides)

| Variable | Purpose |
|---|---|
| `GEMINI_HOME` | Config directory (default: `~/.gemini/`) |
| `GOOGLE_API_KEY` | API key for agent-platform auth |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (overrides settings.json) |
| `GOOGLE_CLOUD_LOCATION` | GCP region (overrides settings.json) |
| `GEMINI_API_KEY` | Gemini API key (for `gemini-api-key` auth only) |

---

## Step 2: Download the Server Binary

Get the download URL from the ACP registry and extract:

```bash
mkdir -p agy-acp-server

# Linux x86_64
curl -L -o agy-acp-server.zip \
  "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_20260818_01_RC01-linux-x86_64.zip"

# macOS ARM (Apple Silicon)
# curl -L -o agy-acp-server.zip \
#   "https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-agy_acp_server_20260818_01_RC01-darwin-arm64.zip"

# Extract
unzip -o agy-acp-server.zip -d agy-acp-server
# Or if unzip is not available:
# python3 -c "import zipfile; zipfile.ZipFile('agy-acp-server.zip').extractall('agy-acp-server')"

chmod +x agy-acp-server/agy_acp_server.par
```

### Linux-Only Prerequisite

The server binary requires a `nobody` group. If it doesn't exist:

```bash
sudo groupadd nobody
```

### Verify the Binary

```bash
./agy-acp-server/agy_acp_server.par --help
```

You should see flags including `--debug` and `--notices`.

### Finding the Latest Version

The download URLs are in the ACP registry. To get the current version:

```bash
curl -s https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json | python3 -m json.tool | grep -A 20 antigravity
```

Or browse: https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json

---

## Step 3: Install the ACP Python SDK

```bash
python3 -m venv venv
source venv/bin/activate
pip install agent-client-protocol httpx
```

---

## Step 4: Create the ACP Client

Save the following as `acp_client.py`:

```python
#!/usr/bin/env python3
"""ACP test client for the Antigravity ACP Server using the official Python SDK."""

import asyncio
import asyncio.subprocess as aio_subprocess
import contextlib
import logging
import os
import sys
from typing import Any

from acp import PROTOCOL_VERSION, connect_to_agent, text_block
from acp.core import ClientSideConnection
from acp.interfaces import Client
from acp import RequestError
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ClientCapabilities,
    CreateElicitationResponse,
    CreateTerminalResponse,
    DeclineElicitationResponse,
    ElicitationMode,
    EnvVariable,
    Implementation,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalOutputResponse,
    TextContentBlock,
    ImageContentBlock,
    AudioContentBlock,
    ResourceContentBlock,
    EmbeddedResourceContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)


class TestClient(Client):
    """ACP client that prints agent responses and auto-approves permissions."""

    async def request_permission(
        self, session_id: str, tool_call: ToolCallUpdate,
        options: list[PermissionOption], **kwargs: Any
    ) -> RequestPermissionResponse:
        print(f"\n[permission] Agent requests permission for tool call")
        return RequestPermissionResponse(outcome={"outcome": "approved"})

    async def write_text_file(
        self, session_id: str, path: str, content: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(
        self, session_id: str, path: str, line: int | None = None,
        limit: int | None = None, **kwargs: Any
    ) -> ReadTextFileResponse:
        raise RequestError.method_not_found("fs/read_text_file")

    async def create_terminal(
        self, session_id: str, command: str,
        args: list[str] | None = None,
        env: list[EnvVariable] | None = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None, **kwargs: Any,
    ) -> CreateTerminalResponse:
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def create_elicitation(
        self, message: str, mode: ElicitationMode, **kwargs: Any
    ) -> CreateElicitationResponse:
        print(f"\n[elicitation] Agent asks: {message}")
        return DeclineElicitationResponse(action="decline")

    async def complete_elicitation(
        self, elicitation_id: str, **kwargs: Any
    ) -> None:
        pass

    async def session_update(
        self, session_id: str, update, **kwargs: Any
    ) -> None:
        if isinstance(update, AgentMessageChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                print(content.text, end="", flush=True)
            elif isinstance(content, ImageContentBlock):
                print("<image>", end="", flush=True)
            elif isinstance(content, AudioContentBlock):
                print("<audio>", end="", flush=True)
            elif isinstance(content, (ResourceContentBlock, EmbeddedResourceContentBlock)):
                print("<resource>", end="", flush=True)
        elif isinstance(update, AgentThoughtChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                print(f"[thought] {content.text}", flush=True)
        elif isinstance(update, ToolCallStart):
            print(f"\n[tool: {update.name} ({update.kind})]", flush=True)
        elif isinstance(update, ToolCallProgress):
            pass

    async def ext_method(self, method: str, params: dict) -> dict:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict) -> None:
        pass


async def read_console(prompt: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def interactive_loop(
    conn: ClientSideConnection, session_id: str
) -> None:
    while True:
        try:
            line = await read_console("\nYou: ")
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            break
        try:
            print("\nAgent: ", end="", flush=True)
            await conn.prompt(
                session_id=session_id,
                prompt=[text_block(line)],
            )
            print()
        except Exception as exc:
            logging.error("Prompt failed: %s", exc)


async def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="ACP Test Client for Antigravity ACP Server"
    )
    parser.add_argument(
        "--server", default="./agy-acp-server/agy_acp_server.par",
        help="Path to ACP server binary"
    )
    parser.add_argument(
        "--message", "-m", default=None,
        help="Single message (otherwise interactive mode)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "UTF-8"
    env["GEMINI_HOME"] = os.path.expanduser("~/.gemini")

    server_path = os.path.abspath(args.server)
    server_dir = os.path.dirname(server_path)

    print(f"Starting ACP server: {server_path}")
    proc = await asyncio.create_subprocess_exec(
        server_path,
        stdin=aio_subprocess.PIPE,
        stdout=aio_subprocess.PIPE,
        stderr=aio_subprocess.PIPE,
        cwd=server_dir,
        env=env,
    )

    if proc.stdin is None or proc.stdout is None:
        print("Error: Server process does not expose stdio pipes",
              file=sys.stderr)
        return 1

    async def log_stderr():
        while proc.stderr:
            line = await proc.stderr.readline()
            if not line:
                break
            sys.stderr.write(f"[server] {line.decode()}")
            sys.stderr.flush()

    stderr_task = asyncio.create_task(log_stderr())

    client_impl = TestClient()
    conn = connect_to_agent(client_impl, proc.stdin, proc.stdout)

    print("Initializing ACP connection...")
    init_result = await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(),
        client_info=Implementation(
            name="acp-test-client",
            title="ACP Test Client",
            version="0.1.0",
        ),
    )
    print(f"Connected to: {init_result.agent_info.name} "
          f"v{init_result.agent_info.version}")
    print(f"Protocol version: {init_result.protocol_version}")

    print("Creating session...")
    session = await conn.new_session(mcp_servers=[], cwd=os.getcwd())
    print(f"Session: {session.session_id}")

    if args.message:
        print(f"\nYou: {args.message}")
        print("\nAgent: ", end="", flush=True)
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block(args.message)],
        )
        print()
    else:
        print("\nInteractive mode. Type 'quit' to exit.\n")
        await interactive_loop(conn, session.session_id)

    print("\nCleaning up...")
    if proc.returncode is None:
        proc.terminate()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
    stderr_task.cancel()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

---

## Step 5: Run the Client

Activate the virtual environment first:

```bash
source venv/bin/activate
```

### Send a Single Message

```bash
python acp_client.py -m "Hello, what can you do?"
```

### Interactive Chat

```bash
python acp_client.py
```

Type messages at the `You:` prompt. Type `quit` to exit.

### Debug Mode

```bash
python acp_client.py --debug -m "Hello"
```

### Custom Server Path

```bash
python acp_client.py --server /path/to/agy_acp_server.par -m "Hello"
```

---

## How It Works

### Architecture

```
┌──────────────┐    stdio (JSON-RPC 2.0)    ┌────────────────────┐
│  ACP Client  │ ◄────────────────────────► │  agy_acp_server    │
│  (Python)    │   stdin/stdout pipes        │  (.par binary)     │
└──────────────┘                             └────────┬───────────┘
                                                      │ ADC / API Key
                                                      ▼
                                             ┌────────────────────┐
                                             │  Google Cloud      │
                                             │  Agent Platform    │
                                             └────────────────────┘
```

### ACP Protocol Flow

The Agent Client Protocol uses **JSON-RPC 2.0 over stdio**. The message sequence is:

1. **`initialize`** — Client sends protocol version and capabilities, server responds with agent info and supported auth methods.
2. **`session/new`** — Client creates a conversation session, receives a `sessionId`.
3. **`session/prompt`** — Client sends user content (text, images, etc.) to the agent.
4. **`session/update`** (notification) — Server streams back agent responses: text chunks, thought chunks, tool call updates.
5. **`session/close`** — Client ends the session.

The server may also send requests to the client for:
- `session/request_permission` — ask permission before executing a tool
- `fs/read_text_file` / `fs/write_text_file` — file system access
- `terminal/create` — execute shell commands
- `elicitation/create` — ask the user a structured question

### Key SDK Components

| Component | Purpose |
|---|---|
| `connect_to_agent()` | Wires stdin/stdout pipes into ACP JSON-RPC framing |
| `Client` (base class) | Subclass to handle server-to-client requests/notifications |
| `session_update()` | Receives streamed agent output (text, thoughts, tool calls) |
| `text_block()` | Helper to create text content blocks for prompts |
| `PROTOCOL_VERSION` | Current ACP protocol version constant |

---

## Troubleshooting

### "Group nobody not found"

Linux only. Create the group:

```bash
sudo groupadd nobody
```

### Server produces no output

Ensure environment variables are set:

```bash
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=UTF-8
```

The server binary is ~1.5GB and may take 30-60 seconds to initialize on first run.

### Authentication errors

For `agent-platform` with ADC, ensure credentials are set up:

```bash
gcloud auth application-default login
```

Verify your project has Agent Platform access:

```bash
gcloud config set project <YOUR_GCP_PROJECT_ID>
```

### "'PROVISIONED_THROUGHPUT' is not a valid ServiceTier"

This is a non-fatal server warning. The agent response is still delivered correctly.

### Monitor server stderr

```bash
python acp_client.py --debug -m "test" 2>/tmp/acp_stderr.log
cat /tmp/acp_stderr.log
```

---

## References

- [ACP Protocol Specification](https://github.com/agentclientprotocol/agent-client-protocol)
- [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk)
- [ACP Python SDK Quickstart](https://agentclientprotocol.github.io/python-sdk/quickstart/)
- [ACP Registry](https://github.com/agentclientprotocol/registry)
- [Antigravity ACP Server Public Docs](https://antigravity.google/docs/ide/extensions)
