#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import shlex
from typing import Any


def content_length_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def line_frame(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


async def read_content_length_frame(
    stream: asyncio.StreamReader, timeout: int
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        header = await asyncio.wait_for(stream.readuntil(b"\r\n\r\n"), timeout=timeout)
    except TimeoutError:
        return None, "timeout waiting header"

    header_text = header.decode("ascii", errors="replace")
    content_length: int | None = None
    for line in header_text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break
    if content_length is None:
        return None, f"missing Content-Length in header: {header_text!r}"

    try:
        body = await asyncio.wait_for(stream.readexactly(content_length), timeout=timeout)
    except TimeoutError:
        return None, f"timeout waiting body length={content_length}"

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception as err:  # noqa: BLE001
        return None, f"invalid JSON body: {err}"
    if not isinstance(data, dict):
        return None, f"invalid payload type: {type(data).__name__}"
    return data, None


async def read_line_frame(stream: asyncio.StreamReader, timeout: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        line = await asyncio.wait_for(stream.readline(), timeout=timeout)
    except TimeoutError:
        return None, "timeout waiting line-delimited JSON-RPC response"
    if not line:
        return None, "stdout closed before line-delimited JSON-RPC response"
    try:
        data = json.loads(line.decode("utf-8", errors="replace"))
    except Exception as err:  # noqa: BLE001
        return None, f"invalid JSON line: {err}; line={line!r}"
    if not isinstance(data, dict):
        return None, f"invalid payload type: {type(data).__name__}"
    return data, None


async def run_once(args: argparse.Namespace, protocol: str) -> int:
    cmd = [args.command, *args.cmd_args]
    print("[CMD]", " ".join(shlex.quote(part) for part in cmd), f"| protocol={protocol}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        print("[ERROR] failed to open stdio pipes")
        return 2

    async def pump_stderr() -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            print("[STDERR]", line.decode("utf-8", errors="replace").rstrip())

    stderr_task = asyncio.create_task(pump_stderr())

    async def read_response(expected_id: int) -> tuple[dict[str, Any] | None, str | None]:
        # Some servers may emit replies to notifications (id=null) or out-of-band frames.
        for _ in range(8):
            resp, err = await read_resp(proc.stdout, timeout=args.timeout)
            if err:
                return None, err
            resp_id = resp.get("id")
            if resp_id != expected_id:
                print(f"[SKIP RESP] id={resp_id} payload={json.dumps(resp, ensure_ascii=False)}")
                continue
            return resp, None
        return None, f"did not receive response with id={expected_id}"

    try:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "stdio-debug", "version": "0.1.0"},
            },
        }
        print("[STEP] send initialize")
        if protocol == "line":
            proc.stdin.write(line_frame(init_req))
            read_resp = read_line_frame
        else:
            proc.stdin.write(content_length_frame(init_req))
            read_resp = read_content_length_frame
        await proc.stdin.drain()

        init_resp, init_err = await read_response(expected_id=1)
        if init_err:
            print("[INIT ERROR]", init_err)
            return 1
        print("[INIT RESP]", json.dumps(init_resp, ensure_ascii=False))

        initialized_notice = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        print("[STEP] send notifications/initialized")
        if protocol == "line":
            proc.stdin.write(line_frame(initialized_notice))
        else:
            proc.stdin.write(content_length_frame(initialized_notice))
        await proc.stdin.drain()

        tools_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        print("[STEP] send tools/list")
        if protocol == "line":
            proc.stdin.write(line_frame(tools_req))
        else:
            proc.stdin.write(content_length_frame(tools_req))
        await proc.stdin.drain()

        tools_resp, tools_err = await read_response(expected_id=2)
        if tools_err:
            print("[TOOLS ERROR]", tools_err)
            return 1
        print("[TOOLS RESP]", json.dumps(tools_resp, ensure_ascii=False))
        return 0
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass
        print("[RC]", proc.returncode)


async def main_async(args: argparse.Namespace) -> int:
    msg_format = args.stdio_msg_format
    if msg_format in {"line", "content-length"}:
        return await run_once(args, msg_format)

    print("[INFO] stdio-msg-format=auto: try line first, fallback to content-length")
    rc_line = await run_once(args, "line")
    if rc_line == 0:
        return 0
    print("[INFO] line protocol failed, retry with content-length")
    return await run_once(args, "content-length")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug MCP stdio handshake (initialize/tools-list)")
    parser.add_argument("--command", default="npx")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--stdio-msg-format",
        choices=["auto", "line", "content-length"],
        default="auto",
        help="stdio message framing format",
    )
    parser.add_argument(
        "--protocol",
        choices=["auto", "line", "content-length"],
        default=None,
        help="deprecated alias of --stdio-msg-format",
    )
    parser.add_argument(
        "cmd_args",
        nargs=argparse.REMAINDER,
        help="command args; default is -y @playwright/mcp@latest if omitted",
    )
    args = parser.parse_args()
    if args.protocol is not None and args.stdio_msg_format == "auto":
        args.stdio_msg_format = args.protocol
    if args.cmd_args and args.cmd_args[0] == "--":
        args.cmd_args = args.cmd_args[1:]
    if not args.cmd_args:
        args.cmd_args = ["-y", "@playwright/mcp@latest"]
    return args


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
