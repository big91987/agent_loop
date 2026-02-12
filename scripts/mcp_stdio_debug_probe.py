#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any


def build_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


async def read_frame(stream: asyncio.StreamReader, timeout_seconds: int) -> dict[str, Any]:
    header = await asyncio.wait_for(stream.readuntil(b"\r\n\r\n"), timeout=timeout_seconds)
    header_text = header.decode("ascii", errors="replace")
    length = None
    for line in header_text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length is None:
        raise RuntimeError("missing Content-Length")
    body = await asyncio.wait_for(stream.readexactly(length), timeout=timeout_seconds)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("response payload is not object")
    return data


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


async def run_probe(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    for item in args.env:
        if "=" not in item:
            print(f"invalid --env: {item} (expected KEY=VALUE)", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        env[k] = v

    log(f"spawn: {args.command} {' '.join(args.cmd_args)}")
    proc = await asyncio.create_subprocess_exec(
        args.command,
        *args.cmd_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        print("failed to open stdio pipes", file=sys.stderr)
        return 2

    async def pump_stderr() -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            print(f"[stderr] {line.decode('utf-8', errors='replace').rstrip()}")

    stderr_task = asyncio.create_task(pump_stderr())
    try:
        req_id = 1
        init_req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-probe", "version": "0.1.0"},
            },
        }
        log("send initialize")
        proc.stdin.write(build_frame(init_req))
        await proc.stdin.drain()
        init_resp = await read_frame(proc.stdout, args.timeout)
        log(f"recv initialize: {json.dumps(init_resp, ensure_ascii=False)}")

        req_id += 1
        tools_req = {"jsonrpc": "2.0", "id": req_id, "method": "tools/list", "params": {}}
        log("send tools/list")
        proc.stdin.write(build_frame(tools_req))
        await proc.stdin.drain()
        tools_resp = await read_frame(proc.stdout, args.timeout)
        log(f"recv tools/list: {json.dumps(tools_resp, ensure_ascii=False)}")

        req_id += 1
        res_req = {"jsonrpc": "2.0", "id": req_id, "method": "resources/list", "params": {}}
        log("send resources/list")
        proc.stdin.write(build_frame(res_req))
        await proc.stdin.drain()
        res_resp = await read_frame(proc.stdout, args.timeout)
        log(f"recv resources/list: {json.dumps(res_resp, ensure_ascii=False)}")
        return 0
    except TimeoutError:
        print(f"timeout waiting for MCP response ({args.timeout}s)", file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001
        print(f"probe failed: {err}", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="Debug probe for MCP stdio servers")
    parser.add_argument("--command", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--env", action="append", default=[], help="KEY=VALUE (repeatable)")
    parser.add_argument("cmd_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cmd_args = list(args.cmd_args)
    if cmd_args and cmd_args[0] == "--":
        cmd_args = cmd_args[1:]
    args.cmd_args = cmd_args
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main())
