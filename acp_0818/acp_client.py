#!/usr/bin/env python3
"""ACP test client for the Antigravity ACP Server using the official Python SDK."""

import asyncio
import asyncio.subprocess as aio_subprocess
import contextlib
import json
import logging
import os
import sys
from typing import Any

from aiohttp import web, ClientSession, ClientTimeout

from acp import PROTOCOL_VERSION, connect_to_agent, text_block
from acp.core import ClientSideConnection
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ClientCapabilities,
    CreateElicitationResponse,
    DeclineElicitationResponse,
    ElicitationMode,
    Implementation,
    KillTerminalResponse,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    PermissionOption,
    TerminalOutputResponse,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
    CreateTerminalResponse,
    EnvVariable,
    TextContentBlock,
    ImageContentBlock,
    AudioContentBlock,
    ResourceContentBlock,
    EmbeddedResourceContentBlock,
)
from acp import RequestError


class TestClient(Client):
    """Minimal ACP client that prints agent responses and auto-approves permissions."""

    async def request_permission(
        self, session_id: str, tool_call: ToolCallUpdate, options: list[PermissionOption], **kwargs: Any
    ) -> RequestPermissionResponse:
        print(f"\n[permission] Agent requests permission for tool call")
        print(f"  Tool: {tool_call}")
        return RequestPermissionResponse(outcome={"outcome": "approved"})

    async def write_text_file(
        self, session_id: str, path: str, content: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        print(f"\n[fs/write] {path} ({len(content)} bytes)")
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(
        self, session_id: str, path: str, line: int | None = None, limit: int | None = None, **kwargs: Any
    ) -> ReadTextFileResponse:
        print(f"\n[fs/read] {path}")
        raise RequestError.method_not_found("fs/read_text_file")

    async def create_terminal(
        self,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        env: list[EnvVariable] | None = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def create_elicitation(self, message: str, mode: ElicitationMode, **kwargs: Any) -> CreateElicitationResponse:
        print(f"\n[elicitation] Agent asks: {message}")
        return DeclineElicitationResponse(action="decline")

    async def complete_elicitation(self, elicitation_id: str, **kwargs: Any) -> None:
        pass

    async def session_update(self, session_id: str, update, **kwargs: Any) -> None:
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
            title = getattr(update, 'title', None) or getattr(update, 'name', 'unknown')
            kind = getattr(update, 'kind', '')
            print(f"\n[tool: {title} ({kind})]", flush=True)
        elif isinstance(update, ToolCallProgress):
            pass

    async def ext_method(self, method: str, params: dict) -> dict:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict) -> None:
        pass


class HeaderInjectionSidecar:
    """Lightweight reverse proxy that injects custom headers and forwards to the gateway."""

    def __init__(self, gateway_url: str, inject_headers: dict[str, str]):
        self.gateway_url = gateway_url.rstrip("/")
        self.inject_headers = inject_headers
        self.session: ClientSession | None = None
        self.runner: web.AppRunner | None = None
        self.port: int = 0

    async def start(self) -> int:
        self.session = ClientSession(timeout=ClientTimeout(total=300))
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self._proxy)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        if self.session:
            await self.session.close()
        if self.runner:
            await self.runner.cleanup()

    async def _proxy(self, request: web.Request) -> web.StreamResponse:
        target_url = f"{self.gateway_url}/{request.path_qs.lstrip('/')}"
        body = await request.read()

        headers = dict(request.headers)
        headers.pop("Host", None)
        headers.pop("x-goog-api-key", None)
        headers.pop("X-Goog-Api-Key", None)
        headers.update(self.inject_headers)

        log = logging.getLogger("sidecar")
        log.info("→ %s %s", request.method, target_url)
        log.info("  Injected headers: %s", self.inject_headers)

        resp = await self.session.request(
            request.method, target_url, data=body, headers=headers,
        )

        if "text/event-stream" in (resp.content_type or ""):
            response = web.StreamResponse(
                status=resp.status,
                headers={"Content-Type": resp.content_type, "Cache-Control": "no-cache"},
            )
            await response.prepare(request)
            async for chunk in resp.content.iter_any():
                await response.write(chunk)
            await response.write_eof()
            return response

        resp_body = await resp.read()
        return web.Response(
            status=resp.status,
            content_type=resp.content_type or "application/json",
            body=resp_body,
        )


async def read_console(prompt: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def interactive_loop(conn: ClientSideConnection, session_id: str) -> None:
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
    parser = argparse.ArgumentParser(description="ACP Test Client for Antigravity ACP Server")
    parser.add_argument("--server", default="./agy-acp-server/agy_acp_server.par",
                        help="Path to ACP server binary")
    parser.add_argument("--message", "-m", default=None,
                        help="Single message to send (otherwise interactive mode)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--gateway-url", default=None,
                        help="Gateway proxy URL (e.g. http://localhost:8080)")
    parser.add_argument("--header", action="append", default=[],
                        help="Custom header to inject: 'Name: Value' (repeatable)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "UTF-8"
    env["GEMINI_HOME"] = os.path.expanduser("~/.gemini")

    sidecar = None
    if args.gateway_url:
        inject_headers = {}
        for h in args.header:
            name, _, value = h.partition(":")
            inject_headers[name.strip()] = value.strip()

        sidecar = HeaderInjectionSidecar(args.gateway_url, inject_headers)
        sidecar_port = await sidecar.start()
        sidecar_url = f"http://127.0.0.1:{sidecar_port}"

        env["GOOGLE_GEMINI_BASE_URL"] = sidecar_url
        if not env.get("GEMINI_API_KEY"):
            env["GEMINI_API_KEY"] = "sidecar-managed"

        print(f"Sidecar proxy started on {sidecar_url}")
        print(f"  Gateway: {args.gateway_url}")
        print(f"  Injected headers: {inject_headers}")
        print(f"  x-goog-api-key: stripped from outgoing requests")

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
        print("Error: Server process does not expose stdio pipes", file=sys.stderr)
        return 1

    # Log stderr in background
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
        client_info=Implementation(name="acp-test-client", title="ACP Test Client", version="0.1.0"),
    )
    print(f"Connected to: {init_result.agent_info.name} v{init_result.agent_info.version}")
    print(f"Protocol version: {init_result.protocol_version}")
    if init_result.auth_methods:
        print(f"Auth methods: {[m.id if hasattr(m, 'id') else str(m) for m in init_result.auth_methods]}")

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
    if sidecar:
        await sidecar.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
