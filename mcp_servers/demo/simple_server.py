#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict


def read_frame() -> Dict[str, Any] | None:
    content_length: int | None = None

    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("ascii", errors="replace").strip()
        if text.lower().startswith("content-length:"):
            content_length = int(text.split(":", 1)[1].strip())

    if content_length is None:
        raise ValueError("Missing Content-Length header")

    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload")
    return payload


def write_frame(payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def ok(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def err(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_initialize(request_id: Any) -> Dict[str, Any]:
    return ok(
        request_id,
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "agent-loop-simple-mcp",
                "version": "0.1.0",
            },
        },
    )


def handle_tools_list(request_id: Any) -> Dict[str, Any]:
    return ok(
        request_id,
        {
            "tools": [
                {
                    "name": "calculate",
                    "description": "Evaluate a basic arithmetic expression and return the result.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                        },
                        "required": ["expression"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "get_current_time",
                    "description": "Return current UTC timestamp in ISO-8601 format.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            ],
        },
    )


def handle_tools_call(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    name = str(params.get("name", "")).strip()
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    if name == "calculate":
        expression = str(arguments.get("expression", "")).strip()
        if not expression:
            return err(request_id, -32602, "Missing required argument: expression")
        try:
            parsed = ast.parse(expression, mode="eval")
            allowed_nodes = (
                ast.Expression,
                ast.BinOp,
                ast.UnaryOp,
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.FloorDiv,
                ast.Mod,
                ast.Pow,
                ast.USub,
                ast.UAdd,
                ast.Constant,
                ast.Load,
            )
            for node in ast.walk(parsed):
                if not isinstance(node, allowed_nodes):
                    return err(request_id, -32602, f"Unsupported syntax: {type(node).__name__}")
            result = eval(compile(parsed, filename="<calc>", mode="eval"), {"__builtins__": {}}, {})
        except Exception as ex:  # noqa: BLE001
            return err(request_id, -32602, f"Invalid expression: {ex}")
        return ok(request_id, {"content": [{"type": "text", "text": str(result)}]})

    if name == "get_current_time":
        result = datetime.now(timezone.utc).isoformat()
        return ok(request_id, {"content": [{"type": "text", "text": result}]})

    return err(request_id, -32601, f"Unknown tool: {name}")


def handle_resources_list(request_id: Any) -> Dict[str, Any]:
    return ok(
        request_id,
        {
            "resources": [
                {
                    "uri": "simple://about",
                    "name": "about",
                    "description": "Basic description of this simple MCP server.",
                    "mimeType": "text/plain",
                },
                {
                    "uri": "simple://usage",
                    "name": "usage",
                    "description": "Quick usage guide for demo resources/tools.",
                    "mimeType": "text/plain",
                },
            ],
        },
    )


def handle_resources_read(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    uri = str(params.get("uri", "")).strip()
    if uri == "simple://about":
        return ok(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": "simple_server provides calculate/get_current_time tools and sample resources.",
                    }
                ]
            },
        )
    if uri == "simple://usage":
        return ok(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Use resources/list then resources/read(uri) to fetch context before tool calls.",
                    }
                ]
            },
        )
    return err(request_id, -32602, f"Unknown resource uri: {uri}")


def main() -> int:
    while True:
        request = read_frame()
        if request is None:
            return 0

        request_id = request.get("id")
        method = str(request.get("method", "")).strip()
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}

        if method == "initialize":
            write_frame(handle_initialize(request_id))
            continue
        if method == "tools/list":
            write_frame(handle_tools_list(request_id))
            continue
        if method == "tools/call":
            write_frame(handle_tools_call(request_id, params))
            continue
        if method == "resources/list":
            write_frame(handle_resources_list(request_id))
            continue
        if method == "resources/read":
            write_frame(handle_resources_read(request_id, params))
            continue

        write_frame(err(request_id, -32601, f"Unknown method: {method}"))


if __name__ == "__main__":
    raise SystemExit(main())
