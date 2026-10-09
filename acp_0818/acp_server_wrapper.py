#!/usr/bin/env python3
"""Wrapper that filters non-JSON-RPC lines from the ACP server's stdout.

The Antigravity ACP server's Node.js browser opener can write error messages
directly to stdout, corrupting the JSON-RPC channel. This wrapper sits between
the client and server, forwarding only valid JSON-RPC lines on stdout and
relaying stdin transparently.
"""

import asyncio
import os
import sys


async def main():
    server_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "agy-acp-server", "agy_acp_server.par")
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "UTF-8"
    env["BROWSER"] = ""
    env["DISPLAY"] = ""
    if os.environ.get("GOOGLE_GEMINI_BASE_URL"):
        env["GOOGLE_GEMINI_BASE_URL"] = os.environ["GOOGLE_GEMINI_BASE_URL"]
    if os.environ.get("GEMINI_API_KEY"):
        env["GEMINI_API_KEY"] = os.environ["GEMINI_API_KEY"]

    proc = await asyncio.create_subprocess_exec(
        server_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # inherit parent stderr
        cwd=os.path.dirname(server_path),
        env=env,
    )

    async def forward_stdin():
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                proc.stdin.write(line)
                await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if proc.stdin:
                proc.stdin.close()

    async def filter_stdout():
        stdout_fd = sys.stdout.buffer
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if text.startswith("{"):
                stdout_fd.write(line)
                stdout_fd.flush()
            else:
                print(f"[filtered] {text}", file=sys.stderr, flush=True)

    stdin_task = asyncio.create_task(forward_stdin())
    stdout_task = asyncio.create_task(filter_stdout())

    await proc.wait()
    stdin_task.cancel()
    stdout_task.cancel()
    sys.exit(proc.returncode or 0)


if __name__ == "__main__":
    asyncio.run(main())
