#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


async def _read_frame(stream: asyncio.StreamReader, timeout_s: int) -> dict[str, Any]:
    header = await asyncio.wait_for(stream.readuntil(b"\r\n\r\n"), timeout=timeout_s)
    header_text = header.decode("ascii", errors="replace")
    length = None
    for line in header_text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length is None:
        raise RuntimeError("Missing Content-Length in response header")
    body = await asyncio.wait_for(stream.readexactly(length), timeout=timeout_s)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Response JSON is not an object")
    return data


async def _run(timeout_s: int, api_key: str) -> int:
    env = {**os.environ, "AMAP_MAPS_API_KEY": api_key}
    cmd = ["npx", "-y", "@amap/amap-maps-mcp-server"]
    _log(f"spawn: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        print("failed to open stdio pipes", file=sys.stderr)
        return 2

    stderr_tail: list[str] = []

    async def _pump_stderr() -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if len(stderr_tail) >= 50:
                stderr_tail.pop(0)
            stderr_tail.append(text)
            print(f"[stderr] {text}")

    stderr_task = asyncio.create_task(_pump_stderr())
    try:
        req_id = 1
        initialize = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "amap-stdio-test", "version": "0.1.0"},
            },
        }
        _log("send initialize")
        proc.stdin.write(_frame(initialize))
        await proc.stdin.drain()
        init_resp = await _read_frame(proc.stdout, timeout_s)
        _log(f"initialize ok: {json.dumps(init_resp, ensure_ascii=False)}")

        req_id += 1
        tools_list = {"jsonrpc": "2.0", "id": req_id, "method": "tools/list", "params": {}}
        _log("send tools/list")
        proc.stdin.write(_frame(tools_list))
        await proc.stdin.drain()
        tools_resp = await _read_frame(proc.stdout, timeout_s)
        tools = tools_resp.get("result", {}).get("tools", []) if isinstance(tools_resp.get("result"), dict) else []
        tool_names = [str(t.get("name", "")) for t in tools if isinstance(t, dict)]
        _log(f"tools/list ok: count={len(tool_names)} names={tool_names}")
        return 0
    except TimeoutError:
        print(f"timeout: no MCP frame within {timeout_s}s", file=sys.stderr)
        if stderr_tail:
            print("stderr tail:", file=sys.stderr)
            for line in stderr_tail[-10:]:
                print(f"  {line}", file=sys.stderr)
        else:
            print("stderr tail: (empty)", file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001
        print(f"probe failed: {err}", file=sys.stderr)
        if stderr_tail:
            print("stderr tail:", file=sys.stderr)
            for line in stderr_tail[-10:]:
                print(f"  {line}", file=sys.stderr)
        return 1
    finally:
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test AMap MCP stdio initialize/tools-list handshake")
    parser.add_argument("--timeout", type=int, default=30, help="Per-response timeout in seconds")
    parser.add_argument(
        "--api-key",
        default=os.getenv("AMAP_MAPS_API_KEY", "").strip(),
        help="AMAP_MAPS_API_KEY value (defaults to current env)",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("missing api key: pass --api-key or set AMAP_MAPS_API_KEY", file=sys.stderr)
        return 2

    return asyncio.run(_run(args.timeout, args.api_key))


if __name__ == "__main__":
    raise SystemExit(main())
