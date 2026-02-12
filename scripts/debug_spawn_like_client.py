#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import sys
import time
from typing import Any


def ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}")


def build_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


async def main_async(args: argparse.Namespace) -> int:
    cmd = [args.command, *args.cmd_args]
    env = dict(os.environ)
    for item in args.env:
        if "=" not in item:
            print(f"invalid --env value: {item} (expected KEY=VALUE)", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        env[k] = v

    log(f"spawn: {' '.join(shlex.quote(x) for x in cmd)}")
    log(f"cwd: {os.getcwd()}")
    log(f"PATH: {env.get('PATH', '')}")
    log(f"NPM_CONFIG_REGISTRY: {env.get('NPM_CONFIG_REGISTRY', '')}")
    log(f"npm_config_registry: {env.get('npm_config_registry', '')}")

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

    async def pump(stream: asyncio.StreamReader, label: str) -> None:
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                log(f"{label}: <EOF>")
                return
            preview = chunk.decode("utf-8", errors="replace")
            if len(preview) > 600:
                preview = preview[:600] + "...(truncated)"
            print(f"[{ts()}] {label} chunk({len(chunk)}): {preview!r}")

    stdout_task = asyncio.create_task(pump(proc.stdout, "stdout"))
    stderr_task = asyncio.create_task(pump(proc.stderr, "stderr"))

    try:
        if args.send_initialize:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "spawn-debug", "version": "0.1.0"},
                },
            }
            frame = build_frame(payload)
            log(f"send initialize frame bytes={len(frame)}")
            proc.stdin.write(frame)
            await proc.stdin.drain()

        try:
            rc = await asyncio.wait_for(proc.wait(), timeout=args.wait_seconds)
            log(f"process exited rc={rc}")
            return rc
        except TimeoutError:
            log(f"wait timeout after {args.wait_seconds}s; sending terminate")
            proc.terminate()
            try:
                rc = await asyncio.wait_for(proc.wait(), timeout=3)
                log(f"terminated rc={rc}")
            except TimeoutError:
                proc.kill()
                rc = await proc.wait()
                log(f"killed rc={rc}")
            return 124
    finally:
        for task in (stdout_task, stderr_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spawn a child process exactly like MCP stdio client and print captured outputs"
    )
    parser.add_argument("--command", default="npx", help="Executable command")
    parser.add_argument("--wait-seconds", type=int, default=40, help="How long to wait before terminate")
    parser.add_argument("--send-initialize", action="store_true", default=True, help="Send MCP initialize frame")
    parser.add_argument("--no-send-initialize", dest="send_initialize", action="store_false")
    parser.add_argument("--env", action="append", default=[], help="Env override KEY=VALUE (repeatable)")
    parser.add_argument("cmd_args", nargs=argparse.REMAINDER, help="Command args, usually after '--'")
    args = parser.parse_args()
    if args.cmd_args and args.cmd_args[0] == "--":
        args.cmd_args = args.cmd_args[1:]
    return args


def main() -> int:
    args = parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
