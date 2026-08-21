# Antigravity ACP Server: Complete Setup & Client Guide

Complete step-by-step guide for setting up the Google Antigravity ACP Server and calling it programmatically using the official ACP Python SDK. This guide uses `agent-platform` authentication with Application Default Credentials (ADC).

---

## Table of Contents

1. [Quick Start (TL;DR)](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Step 1: Set Up Google Cloud Authentication](#step-1-set-up-google-cloud-authentication)
4. [Step 2: Configure the Antigravity ACP Server](#step-2-configure-the-antigravity-acp-server)
5. [Step 3: Download the Server Binary](#step-3-download-the-server-binary)
6. [Step 4: Verify the Server Binary](#step-4-verify-the-server-binary)
7. [Step 5: Install the ACP Python SDK](#step-5-install-the-acp-python-sdk)
8. [Step 6: Create the ACP Client](#step-6-create-the-acp-client)
9. [Step 7: Run the Client (Which Starts the Server)](#step-7-run-the-client)
10. [How It Works](#how-it-works)
11. [All Authentication Options](#all-authentication-options)
12. [All Platform Download URLs](#all-platform-download-urls)
13. [Troubleshooting](#troubleshooting)
14. [References](#references)

---

## Quick Start

For experienced users — run these commands in order:

```bash
# 1. Auth
gcloud auth application-default login

# 2. Config
mkdir -p ~/.gemini/antigravity-acp
cat > ~/.gemini/antigravity-acp/settings.json << 'EOF'
{
  "auth": { "type": "agent-platform" },
  "gcp": { "project": "<YOUR_GCP_PROJECT_ID>", "location": "<YOUR_GCP_REGION>" }
}
EOF

# 3. Download server (Linux x86_64)
mkdir -p agy-acp-server
curl -L -o agy-acp-server.zip "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_20260818_01_RC01-linux-x86_64.zip"
unzip -o agy-acp-server.zip -d agy-acp-server && chmod +x agy-acp-server/agy_acp_server.par
sudo groupadd nobody 2>/dev/null  # Linux only

# 4. Install SDK
python3 -m venv venv && source venv/bin/activate
pip install agent-client-protocol

# 5. Run (downloads acp_client.py from this repo first)
python acp_client.py -m "Hello, what can you do?"
```

Read on for the full detailed walkthrough.

---

## Prerequisites

Before you begin, make sure you have the following installed on your machine.

### 1. Python 3.10 or later

Check your Python version:

```bash
python3 --version
```

If you see `Python 3.10.x` or later, you're good. If not, install Python from your package manager.

On Debian/Ubuntu, also install the `venv` module (it's not always included by default):

```bash
sudo apt install python3-venv
```

### 2. Google Cloud SDK (`gcloud` CLI)

You need the `gcloud` CLI to set up Application Default Credentials. Check if it's installed:

```bash
gcloud --version
```

If not installed, follow Google's instructions: https://cloud.google.com/sdk/docs/install

### 3. `curl` and `unzip`

These are needed to download and extract the server binary:

```bash
# Debian/Ubuntu
sudo apt install curl unzip

# If unzip is unavailable, the guide includes a Python fallback
```

### 4. Google Cloud Access

You need:
- A **Google Cloud Project ID** with Gemini Enterprise Agent Platform access.
- A **GCP region** where the Agent Platform is available (e.g. `us-central1`, or `global`).
- Ask your GCP administrator if you don't have these.

---

## Step 1: Set Up Google Cloud Authentication

The Antigravity ACP Server needs credentials to call the Google Cloud Agent Platform on your behalf. With `agent-platform` auth, you have two options:

### Option A: Application Default Credentials (ADC) — Recommended

ADC uses your Google Cloud login. Run this command and follow the browser-based login flow:

```bash
gcloud auth application-default login
```

After logging in, credentials are stored locally at `~/.config/gcloud/application_default_credentials.json`. The ACP server reads these automatically.

Also set your project (so `gcloud` commands know which project to use):

```bash
gcloud config set project <YOUR_GCP_PROJECT_ID>
```

### Option B: Google API Key

Alternatively, you can use a Google API key instead of ADC. Generate one in the Google Cloud Console, then set it as an environment variable:

```bash
export GOOGLE_API_KEY="your-api-key-here"
```

If you use an API key, you do NOT need to run `gcloud auth application-default login`.

---

## Step 2: Configure the Antigravity ACP Server

The server reads its configuration from a JSON file in `~/.gemini/antigravity-acp/`.

### Create the config directory

```bash
mkdir -p ~/.gemini/antigravity-acp
```

### Create the settings file

Create the file `~/.gemini/antigravity-acp/settings.json` with the following content:

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

**Replace the placeholders:**
- `<YOUR_GCP_PROJECT_ID>` — your Google Cloud project ID (e.g. `cloud-llm-preview1`)
- `<YOUR_GCP_REGION>` — the region for Agent Platform (e.g. `global` or `us-central1`)

**Example with real values:**

```json
{
  "auth": {
    "type": "agent-platform"
  },
  "gcp": {
    "project": "cloud-llm-preview1",
    "location": "global"
  }
}
```

You can create this file with a single command:

```bash
cat > ~/.gemini/antigravity-acp/settings.json << 'EOF'
{
  "auth": {
    "type": "agent-platform"
  },
  "gcp": {
    "project": "cloud-llm-preview1",
    "location": "global"
  }
}
EOF
```

### Verify the config file

```bash
cat ~/.gemini/antigravity-acp/settings.json
```

You should see the JSON you just wrote.

---

## Step 3: Download the Server Binary

The Antigravity ACP Server is distributed as a pre-built binary. Download URLs are published in the [ACP Registry](https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json).

### Create a directory for the server

```bash
mkdir -p agy-acp-server
```

### Download the binary for your platform

**Linux x86_64** (most common for cloud VMs and desktops):

```bash
curl -L -o agy-acp-server.zip \
  "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_20260818_01_RC01-linux-x86_64.zip"
```

**macOS ARM (Apple Silicon — M1/M2/M3/M4):**

```bash
curl -L -o agy-acp-server.zip \
  "https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-agy_acp_server_20260818_01_RC01-darwin-arm64.zip"
```

See [All Platform Download URLs](#all-platform-download-urls) for Linux ARM64, Windows x86_64, and Windows ARM64.

### Extract the archive

Using `unzip`:

```bash
unzip -o agy-acp-server.zip -d agy-acp-server
```

If `unzip` is not available, use Python instead:

```bash
python3 -c "import zipfile; zipfile.ZipFile('agy-acp-server.zip').extractall('agy-acp-server')"
```

### Make the binary executable

```bash
chmod +x agy-acp-server/agy_acp_server.par
```

On macOS, you may also need to remove quarantine attributes:

```bash
xattr -cr agy-acp-server/
```

### Linux only: create the `nobody` group

The server binary requires a system group called `nobody`. On some Linux distributions (e.g. Debian), this group doesn't exist by default. **If you skip this, the server will crash on startup** with the error `Group nobody not found`.

Check if it exists:

```bash
grep nobody /etc/group
```

If there's no output, create it:

```bash
sudo groupadd nobody
```

### Clean up the zip file (optional)

```bash
rm -f agy-acp-server.zip
```

---

## Step 4: Verify the Server Binary

After extracting, your directory should look like this:

```
agy-acp-server/
├── agy_acp_server.par    # The server binary (~1.5 GB)
└── localharness_external  # Supporting binary
```

Verify the binary runs:

```bash
./agy-acp-server/agy_acp_server.par --help
```

**Expected output:**

```
Entry point for the AGY ACP Server.
flags:

/path/to/agy_acp_server.par:
  --[no]debug: Enable debug logging.
    (default: 'false')
  --[no]notices: Print licenses and exit.
    (default: 'false')
...
```

If you see this, the binary is working.

> **Important:** You do NOT start the server manually in a terminal. The ACP server uses **stdio transport** — the client spawns it as a subprocess and communicates over stdin/stdout pipes. This is explained in [How It Works](#how-it-works).

---

## Step 5: Install the ACP Python SDK

### Create a Python virtual environment

```bash
python3 -m venv venv
```

### Activate the virtual environment

```bash
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### Install the official ACP SDK

```bash
pip install agent-client-protocol
```

**Expected output (last line):**

```
Successfully installed agent-client-protocol-0.12.1 ...
```

### Verify the installation

```bash
python -c "import acp; print(f'ACP SDK version: {acp.__version__}')"
```

---

## Step 6: Create the ACP Client

Create a file called `acp_client.py` in your project directory. This client:

1. **Spawns** the ACP server binary as a child process.
2. **Connects** to it over stdin/stdout using JSON-RPC 2.0.
3. **Initializes** the ACP protocol handshake.
4. **Creates a session** and sends your prompt.
5. **Prints** the agent's streamed response in real time.
6. **Cleans up** the server process when done.

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
    """ACP client that prints agent responses and auto-approves permissions.

    The ACP protocol is bidirectional: the server can send requests TO the client
    (e.g., asking to read a file or run a terminal command). This class implements
    all required handler methods. In this test client:
      - session_update: prints agent text, thoughts, and tool call info
      - request_permission: auto-approves all tool calls
      - file/terminal operations: rejected (not implemented in this test client)
    """

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

    # --- 1. Set up environment variables for the server process ---
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"        # Prevent output buffering
    env["PYTHONIOENCODING"] = "UTF-8"    # Ensure UTF-8 encoding
    env["GEMINI_HOME"] = os.path.expanduser("~/.gemini")

    server_path = os.path.abspath(args.server)
    server_dir = os.path.dirname(server_path)

    # --- 2. Spawn the ACP server as a child process ---
    # The server communicates over stdio (stdin/stdout), NOT over HTTP.
    # The client spawns it and connects via pipes.
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

    # Log server stderr in background (for debugging)
    async def log_stderr():
        while proc.stderr:
            line = await proc.stderr.readline()
            if not line:
                break
            sys.stderr.write(f"[server] {line.decode()}")
            sys.stderr.flush()

    stderr_task = asyncio.create_task(log_stderr())

    # --- 3. Connect to the server using ACP protocol ---
    client_impl = TestClient()
    conn = connect_to_agent(client_impl, proc.stdin, proc.stdout)

    # --- 4. ACP handshake (initialize) ---
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

    # --- 5. Create a session ---
    print("Creating session...")
    session = await conn.new_session(mcp_servers=[], cwd=os.getcwd())
    print(f"Session: {session.session_id}")

    # --- 6. Send prompt(s) ---
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

    # --- 7. Clean up ---
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

## Step 7: Run the Client

> **Key concept:** You do NOT start the server separately. The client script spawns the server as a subprocess automatically. When you run `python acp_client.py`, it:
> 1. Launches `agy_acp_server.par` as a child process
> 2. Connects to it via stdin/stdout pipes (JSON-RPC 2.0)
> 3. Performs the ACP handshake
> 4. Sends your message and prints the response
> 5. Terminates the server when done

### Activate the virtual environment

Every time you open a new terminal, activate the venv first:

```bash
source venv/bin/activate
```

You should see `(venv)` in your prompt.

### Send a single message

```bash
python acp_client.py -m "Hello, what can you do?"
```

**Expected output:**

```
Starting ACP server: /path/to/agy-acp-server/agy_acp_server.par
Initializing ACP connection...
Connected to: antigravity-acp vagy_acp_server_20260818_01_RC01
Protocol version: 1
Creating session...
Session: 27028f04-4788-428c-bcde-8777a6b2600f

You: Hello, what can you do?

Agent: [thought] **Exploring Capabilities**
...

Hello! I am **Antigravity**, an agentic AI assistant developed by Google DeepMind.

Here is a summary of what I can help you with:
* **Software Development & Refactoring**: Read, search, navigate, create, and edit code.
* **Command Execution & Debugging**: Run terminal commands, test suites, builds, scripts.
* **Planning & Architecture**: Draft implementation plans, generate architecture diagrams.
* **Research & Web Search**: Search documentation, fetch live web resources.
...

Cleaning up...
```

> **Note:** The first run may take 30-60 seconds before you see `Initializing ACP connection...` because the 1.5 GB server binary needs to unpack itself.

### Interactive chat mode

Run without `-m` to enter an interactive conversation:

```bash
python acp_client.py
```

You'll see a `You:` prompt. Type your messages and press Enter. Type `quit` to exit.

```
Interactive mode. Type 'quit' to exit.

You: Explain what ACP is in one sentence.

Agent: ACP (Agent Client Protocol) is an open protocol that enables any code
editor or developer tool to connect to any AI coding agent through a
standardized communication interface.

You: quit

Cleaning up...
```

### Debug mode

To see detailed JSON-RPC messages and server logs:

```bash
python acp_client.py --debug -m "Hello"
```

### Custom server path

If your server binary is in a different location:

```bash
python acp_client.py --server /path/to/agy_acp_server.par -m "Hello"
```

### Redirect server logs to a file

```bash
python acp_client.py -m "Hello" 2>/tmp/acp_server.log
cat /tmp/acp_server.log
```

---

## How It Works

### Why There Is No "Start the Server" Step

Unlike traditional HTTP APIs, the Antigravity ACP Server does NOT listen on a network port. Instead, it uses **stdio transport**:

- The **client** spawns the server binary as a **child process**.
- Communication happens over **stdin/stdout pipes** using **JSON-RPC 2.0** messages.
- This is the same pattern used by LSP (Language Server Protocol) in code editors.

This means:
- There is no URL or port to connect to.
- You don't run the server in a separate terminal.
- The client manages the server's lifecycle (start, communicate, stop).

### Architecture

```
┌──────────────────┐       stdin (JSON-RPC 2.0)       ┌────────────────────────┐
│                  │  ──────────────────────────────►  │                        │
│   ACP Client     │                                   │   agy_acp_server.par   │
│   (Python)       │  ◄──────────────────────────────  │   (Server Binary)      │
│                  │       stdout (JSON-RPC 2.0)       │                        │
└──────────────────┘                                   └───────────┬────────────┘
                                                                   │
                                                                   │ ADC or API Key
                                                                   ▼
                                                       ┌────────────────────────┐
                                                       │   Google Cloud         │
                                                       │   Agent Platform       │
                                                       └────────────────────────┘
```

### ACP Protocol Flow

The conversation between client and server follows this sequence:

```
Client                              Server
  │                                    │
  │──── initialize ───────────────────►│   1. Handshake: exchange protocol
  │◄─── init result (agent info) ─────│      version and capabilities
  │                                    │
  │──── session/new ──────────────────►│   2. Create a conversation session
  │◄─── session id ───────────────────│
  │                                    │
  │──── session/prompt ───────────────►│   3. Send user message
  │◄─── session/update (streaming) ───│   4. Receive agent response chunks
  │◄─── session/update (streaming) ───│      (text, thoughts, tool calls)
  │◄─── session/update (streaming) ───│
  │◄─── prompt result ────────────────│   5. Response complete
  │                                    │
  │──── session/close ────────────────►│   6. End session
  │                                    │
```

**Bidirectional requests:** During step 4, the server may also send requests TO the client:

| Server Request | Purpose | Our Client's Response |
|---|---|---|
| `session/request_permission` | Ask before executing a tool | Auto-approve |
| `fs/read_text_file` | Read a file from disk | Rejected (not implemented) |
| `fs/write_text_file` | Write a file to disk | Rejected (not implemented) |
| `terminal/create` | Run a shell command | Rejected (not implemented) |
| `elicitation/create` | Ask the user a structured question | Declined |

### Key SDK Components

| Component | What It Does |
|---|---|
| `connect_to_agent(client, stdin, stdout)` | Wires stdin/stdout pipes into ACP JSON-RPC framing |
| `Client` (base class) | Subclass this to handle server-to-client requests and notifications |
| `conn.initialize(...)` | Performs the ACP handshake with the server |
| `conn.new_session(...)` | Creates a new conversation session |
| `conn.prompt(session_id, prompt)` | Sends a user message to the agent |
| `session_update(session_id, update)` | Called when the agent streams response chunks back |
| `text_block("...")` | Helper to create a text content block for prompts |
| `PROTOCOL_VERSION` | The current ACP protocol version constant |

### Project Directory Structure

After completing all steps, your directory should look like this:

```
your-project/
├── agy-acp-server/
│   ├── agy_acp_server.par          # Server binary (~1.5 GB) — NOT committed to git
│   └── localharness_external        # Supporting binary
├── venv/                            # Python virtual environment — NOT committed to git
├── acp_client.py                    # Your ACP client script
├── settings.json                    # (Optional) local copy of your config
├── GUIDE.md                         # This guide
└── .gitignore                       # Excludes venv/ and agy-acp-server/
```

The server config lives separately at `~/.gemini/antigravity-acp/settings.json`.

---

## All Authentication Options

The Antigravity ACP Server supports four authentication methods. Change the `auth.type` in `settings.json` to switch.

### 1. Agent Platform with ADC (used in this guide)

```json
{
  "auth": { "type": "agent-platform" },
  "gcp": {
    "project": "<YOUR_GCP_PROJECT_ID>",
    "location": "<YOUR_GCP_REGION>"
  }
}
```

Requires: `gcloud auth application-default login`

### 2. Agent Platform with Google API Key

```json
{
  "auth": { "type": "agent-platform" },
  "gcp": {
    "project": "<YOUR_GCP_PROJECT_ID>",
    "location": "<YOUR_GCP_REGION>"
  }
}
```

Requires: `export GOOGLE_API_KEY="your-key"`

### 3. Google Account (Personal, OAuth)

```json
{
  "auth": { "type": "oauth-personal" }
}
```

The server handles the OAuth browser flow on first use. No GCP project needed.

**Requirements:**
- A personal Google account (not a managed/enterprise account)
- The account must be eligible for the Google AI free tier
- If you see `User is ineligible for free-tier`, try a different personal Google account

**Tested behavior:** The server opens a browser for Google sign-in. After authenticating, credentials are cached in `~/.gemini/` for future sessions.

### 4. Gemini Enterprise (OAuth)

```json
{
  "auth": { "type": "oauth-business" },
  "gcp": {
    "project": "<YOUR_GCP_PROJECT_ID>",
    "location": "<YOUR_GCP_REGION>"
  }
}
```

**Requirements:**
- A Google Workspace account with Gemini Enterprise subscription
- The GCP project must have an active Gemini Enterprise license
- If you see `No valid Gemini Enterprise license for the configured project`, your project does not have a Gemini Enterprise subscription — contact your Google Cloud administrator

**Tested behavior:** The OAuth browser flow works the same as `oauth-personal`. After sign-in, the server validates the Gemini Enterprise license for the configured project before creating a session.

### 5. Gemini API Key

```json
{
  "auth": { "type": "gemini-api-key" }
}
```

Requires: `export GEMINI_API_KEY="your-key"` (from Google AI Studio)

### Important: OAuth Methods on Remote VMs

The `oauth-personal` and `oauth-business` methods use a browser-based OAuth flow. The server starts a **local HTTP callback listener** (on a random port like `55693`) and opens a browser for sign-in. After authentication, Google redirects the browser to `http://localhost:<port>/callback?code=...`.

**This causes problems on remote VMs:** The browser opens on your local machine, but the callback server is listening on the remote VM. When Google redirects to `localhost`, it hits your local machine (where nothing is listening) instead of the VM.

**Workarounds for remote VMs:**

1. **Port forwarding (recommended):** Forward the callback port from the VM to your local machine. In VS Code Remote, check the **Ports** tab — it may auto-forward. Or use SSH:
   ```bash
   # Run on your LOCAL machine (not the VM):
   ssh -L <PORT>:localhost:<PORT> user@your-vm-ip
   ```
   Then reload the failed redirect URL in your browser.

2. **Replay the redirect URL:** After sign-in, your browser will show a failed page at `http://localhost:<PORT>/callback?code=...&scope=...`. Copy the full URL from the address bar and run it on the VM:
   ```bash
   curl "http://localhost:<PORT>/callback?code=4/0A...&scope=..."
   ```

3. **Use `agent-platform` instead:** If you have a GCP project with Agent Platform access, use `agent-platform` with ADC. The `gcloud auth application-default login` command handles remote auth properly (it gives you a URL to visit and a code to paste back).

**Once OAuth succeeds**, credentials are cached in `~/.gemini/` and subsequent runs won't need the browser flow again.

### Environment Variable Overrides

These override values in `settings.json`:

| Variable | Purpose |
|---|---|
| `GEMINI_HOME` | Config directory (default: `~/.gemini/`) |
| `GOOGLE_API_KEY` | API key for agent-platform auth |
| `GOOGLE_CLOUD_PROJECT` | Overrides `gcp.project` in settings.json |
| `GOOGLE_CLOUD_LOCATION` | Overrides `gcp.location` in settings.json |
| `GEMINI_API_KEY` | API key for gemini-api-key auth |

---

## All Platform Download URLs

| Platform | Download URL |
|---|---|
| Linux x86_64 | `https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_20260818_01_RC01-linux-x86_64.zip` |
| Linux ARM64 | `https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_20260818_01_RC01-linux-arm64.zip` |
| macOS ARM64 | `https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-agy_acp_server_20260818_01_RC01-darwin-arm64.zip` |
| Windows x86_64 | `https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-agy_acp_server_20260818_01_RC01-windows-x86_64.zip` |
| Windows ARM64 | `https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-agy_acp_server_20260818_01_RC01-windows-arm64.zip` |

Binary filenames:
- macOS / Linux: `agy_acp_server.par`
- Windows: `agy_acp_server.exe`

To find the latest version, check the ACP registry:

```bash
curl -s https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(a['name'],a.get('version','')) for a in d.get('agents',[]) if 'antigravity' in a.get('id','')]"
```

Or browse: https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json

---

## Troubleshooting

### "Group nobody not found" (Linux only)

**Symptom:** Server crashes immediately with:
```
Check failed: LookupGIDByGroupName(groupname, &new_gid) Group nobody not found
```

**Fix:**
```bash
sudo groupadd nobody
```

### Server takes a long time to start

The server binary is ~1.5 GB. On first run, it may take 30-60 seconds to unpack and initialize. Subsequent runs may be faster. This is normal — wait for the `Initializing ACP connection...` message.

### No output at all / client hangs

Make sure the environment variables are set. The client sets these automatically, but if running the server manually for debugging:

```bash
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=UTF-8
export GEMINI_HOME="$HOME/.gemini"
```

### Authentication errors

**For ADC:** Make sure you've logged in:
```bash
gcloud auth application-default login
```

**Verify your project has access:**
```bash
gcloud config set project <YOUR_GCP_PROJECT_ID>
```

**Check the settings file is correct:**
```bash
cat ~/.gemini/antigravity-acp/settings.json
```

### "'PROVISIONED_THROUGHPUT' is not a valid ServiceTier"

This is a non-fatal server warning that appears in stderr after the response is delivered. Your agent response is still correct. You can safely ignore it.

### "Agent execution error"

Check server stderr for details:
```bash
python acp_client.py -m "test" 2>/tmp/acp_debug.log
cat /tmp/acp_debug.log
```

### `python3-venv` not found (Debian/Ubuntu)

```bash
sudo apt install python3-venv
# or for a specific version:
sudo apt install python3.13-venv
```

### "No valid Gemini Enterprise license" (oauth-business)

**Symptom:**
```
No valid Gemini Enterprise license for the configured project 'my-project' / location 'global'.
```

**Cause:** The `oauth-business` auth type requires an active Gemini Enterprise subscription linked to the GCP project. This is a licensing issue, not an authentication issue — the OAuth sign-in succeeded.

**Fix:** Use a project with Gemini Enterprise, or switch to `agent-platform` or `oauth-personal` auth.

### "User is ineligible for free-tier" (oauth-personal)

**Symptom:**
```
Onboarding failed: User is ineligible for free-tier. Your current account is not eligible for Antigravity.
```

**Cause:** Managed/enterprise Google accounts may not be eligible for the personal free tier.

**Fix:** Sign in with a different personal Google account, or use `agent-platform` auth instead.

### OAuth hangs on remote VM

**Symptom:** Browser opens on your laptop, you sign in, then the page hangs at "localhost refused to connect."

**Cause:** The OAuth callback server listens on `localhost` on the remote VM, but the browser redirect goes to `localhost` on your laptop.

**Fix:** See [Important: OAuth Methods on Remote VMs](#important-oauth-methods-on-remote-vms) in the Authentication Options section.

### macOS: "agy_acp_server.par cannot be opened because it is from an unidentified developer"

Remove the quarantine attribute:
```bash
xattr -cr agy-acp-server/
```

---

## References

- [ACP Protocol Specification](https://github.com/agentclientprotocol/agent-client-protocol) — the full protocol spec
- [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk) — official Python SDK source
- [ACP Python SDK Quickstart](https://agentclientprotocol.github.io/python-sdk/quickstart/) — SDK getting started guide
- [ACP Registry](https://github.com/agentclientprotocol/registry) — registry of all ACP agents with download URLs
- [Antigravity Docs](https://antigravity.google/docs/ide/extensions) — official Google Antigravity documentation
- [ACP Python SDK Examples](https://github.com/agentclientprotocol/python-sdk/tree/main/examples) — client.py, echo_agent.py, etc.
