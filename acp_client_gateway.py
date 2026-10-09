#!/usr/bin/env python3
"""ACP Client using Antigravity's native gateway support (AGY_LLM_GATEWAY_* env vars).

No sidecar needed — the ACP server natively handles custom gateway URL, headers,
and API key via environment variables.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from typing import Any

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
)

DEFAULT_SERVER_DIR = "./agy-acp-server-v1.3.0"
DEFAULT_SERVER_PATH = f"{DEFAULT_SERVER_DIR}/agy_acp_server.par"
DEFAULT_HARNESS_PATH = f"{DEFAULT_SERVER_DIR}/localharness_external"


class SimpleAcpClient(Client):
    """Minimal ACP client that prints streamed agent responses."""

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: Any,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        option_id = options[0].option_id if options else "allow"
        return RequestPermissionResponse(
            outcome=AllowedOutcome(option_id=option_id, outcome="selected")
        )

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        if isinstance(update, AgentMessageChunk):
            if isinstance(update.content, TextContentBlock):
                print(update.content.text, end="", flush=True)
        elif isinstance(update, AgentThoughtChunk):
            if isinstance(update.content, TextContentBlock):
                print(f"[thought] {update.content.text}", flush=True)
        elif isinstance(update, ToolCallStart):
            print(f"\n[tool: {update.title}]", flush=True)


def get_gcloud_token(cmd: str) -> str:
    try:
        return subprocess.check_output(
            ["gcloud", "auth", cmd], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""


def build_gateway_env(gateway_url: str, model: str, headers: list[str], api_key: str = "") -> dict[str, str]:
    """Configure AGY_LLM_GATEWAY_* env vars for native gateway support."""
    if not api_key:
        api_key = get_gcloud_token("print-identity-token")

    settings_dir = os.path.expanduser("~/.gemini/antigravity-acp")
    os.makedirs(settings_dir, exist_ok=True)
    with open(os.path.join(settings_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"auth": {"type": "gateway"}}, f, indent=2)

    env = os.environ.copy()

    harness_path = os.path.abspath(DEFAULT_HARNESS_PATH)
    if os.path.exists(harness_path):
        env["ANTIGRAVITY_HARNESS_PATH"] = harness_path

    env["AGY_LLM_GATEWAY_URL"] = gateway_url
    env["AGY_LLM_GATEWAY_API_KEY"] = api_key
    env["AGY_LLM_GATEWAY_HEADERS"] = ", ".join(headers)
    env["AGY_LLM_GATEWAY_MODELS"] = model

    return env


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Antigravity ACP Client with Native Gateway Support"
    )
    parser.add_argument(
        "--server", default=DEFAULT_SERVER_PATH, help="Path to agy_acp_server.par"
    )
    parser.add_argument(
        "--gateway-url", default="http://localhost:8080/",
        help="Gateway URL (default: http://localhost:8080/)"
    )
    parser.add_argument(
        "--model", default="gemini-3.7-flash",
        help="Model to use (default: gemini-3.7-flash)"
    )
    parser.add_argument(
        "--header", action="append", default=[],
        help="Custom header: 'Name: Value' (repeatable)"
    )
    parser.add_argument(
        "--api-key", default="",
        help="Gateway API key (default: gcloud identity token)"
    )
    parser.add_argument(
        "-m", "--message", default=None, help="Single prompt message to send"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    headers = args.header if args.header else [
        "x-adapter-source: antigravity",
        "sso-email: zhangsan@xxxx.com",
    ]

    env = build_gateway_env(args.gateway_url, args.model, headers, args.api_key)
    server_path = os.path.abspath(args.server)

    print(f"Gateway URL:   {env['AGY_LLM_GATEWAY_URL']}")
    print(f"Gateway Model: {env['AGY_LLM_GATEWAY_MODELS']}")
    print(f"Headers:       {env['AGY_LLM_GATEWAY_HEADERS']}")
    print(f"API Key:       {env['AGY_LLM_GATEWAY_API_KEY'][:20]}...")
    print(f"Harness:       {env.get('ANTIGRAVITY_HARNESS_PATH', 'not found')}")
    print(f"Server:        {server_path}")
    print()

    async with spawn_agent_process(
        SimpleAcpClient(),
        server_path,
        env=env,
        cwd=os.path.dirname(server_path),
        transport_kwargs={"limit": 16 * 1024 * 1024},
    ) as (conn, _proc):
        await conn.initialize(protocol_version=PROTOCOL_VERSION)
        session = await conn.new_session(cwd=os.getcwd(), mcp_servers=[])
        print(f"ACP Session:   {session.session_id}\n")

        if args.message:
            print(f"You: {args.message}\nAgent: ", end="", flush=True)
            await conn.prompt(
                session_id=session.session_id,
                prompt=[text_block(args.message)],
            )
            print()
        else:
            print("Interactive mode. Type 'quit' to exit.\n")
            while True:
                try:
                    line = input("\nYou: ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line or line.lower() in ("quit", "exit", "q"):
                    break
                print("Agent: ", end="", flush=True)
                await conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(line)],
                )
                print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
