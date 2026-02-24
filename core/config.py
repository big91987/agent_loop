from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .mcp_client import MCPServerConfig


@dataclass(frozen=True)
class AppConfig:
    provider: str
    model_name: str
    base_url: str
    api_key_env: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 60
    default_loop_version: str = "v1"
    mcp_servers: List[MCPServerConfig] | None = None
    skills_dir: str | None = None
    memory_compact_ratio: float = 0.8
    memory_context_window_tokens: int = 128000
    pricing_currency: str = "CNY"
    pricing_input_per_million: float | None = None
    pricing_output_per_million: float | None = None
    pricing_cache_read_per_million: float | None = None
    pricing_cache_write_per_million: float | None = None


_ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_env_var_name(value: str) -> bool:
    return bool(_ENV_NAME_PATTERN.match(value))


def load_config(path: str) -> AppConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    api_key_raw = raw.get("api_key")
    api_key = str(api_key_raw).strip() if api_key_raw is not None else None
    if api_key == "":
        api_key = None

    api_key_env_raw = raw.get("api_key_env")
    api_key_env: str | None = None
    if api_key_env_raw is not None:
        candidate = str(api_key_env_raw).strip()
        if candidate:
            if _is_env_var_name(candidate):
                api_key_env = candidate
            elif api_key is None:
                # Backward compatibility: if api_key_env contains a literal key, treat it as api_key.
                api_key = candidate

    if api_key_env is None:
        api_key_env = "OPENAI_API_KEY"

    raw_mcp_servers = raw.get("mcpServers", {})
    mcp_servers: List[MCPServerConfig] = []
    supported_mcp_types = {"stdio", "sse", "streamable_http"}
    supported_stdio_msg_formats = {"auto", "line", "content-length"}
    if isinstance(raw_mcp_servers, dict):
        for key, value in raw_mcp_servers.items():
            name = str(key).strip()
            item = value if isinstance(value, dict) else {}
            if not name:
                continue

            mcp_type_raw = item.get("type")
            mcp_type = str(mcp_type_raw).strip().lower() if mcp_type_raw is not None else ""
            if mcp_type and mcp_type not in supported_mcp_types:
                continue

            command = str(item.get("command", "")).strip()
            args_raw = item.get("args", [])
            args = [str(part) for part in args_raw] if isinstance(args_raw, list) else []
            env_raw = item.get("env", {})
            env: Dict[str, str] = {}
            if isinstance(env_raw, dict):
                env = {str(k): str(v) for k, v in env_raw.items()}
            headers_raw = item.get("headers", {})
            headers: Dict[str, str] = {}
            if isinstance(headers_raw, dict):
                headers = {str(k): str(v) for k, v in headers_raw.items()}
            url_raw = item.get("url")
            url = str(url_raw).strip() if url_raw is not None else None
            if url == "":
                url = None
            message_url_raw = item.get("message_url")
            message_url = str(message_url_raw).strip() if message_url_raw is not None else None
            if message_url == "":
                message_url = None
            stdio_msg_format_raw = item.get("stdio_msg_format", "auto")
            stdio_msg_format = str(stdio_msg_format_raw).strip().lower() or "auto"
            if stdio_msg_format not in supported_stdio_msg_formats:
                stdio_msg_format = "auto"
            timeout = int(item.get("timeout_seconds", 30))

            # v4 uses explicit/legacy stdio behavior; v4.1 may infer later in mcp_client_v4_1.
            if mcp_type == "stdio" and not command:
                continue
            if mcp_type in {"sse", "streamable_http"} and not url:
                continue
            if not mcp_type and not command and not url:
                continue

            mcp_servers.append(
                MCPServerConfig(
                    name=name,
                    type=mcp_type,
                    command=command,
                    args=args,
                    env=env,
                    url=url,
                    message_url=message_url,
                    headers=headers,
                    stdio_msg_format=stdio_msg_format,
                    timeout_seconds=timeout,
                ),
            )

    skills_dir_raw = raw.get("skills_dir")
    skills_dir = str(skills_dir_raw).strip() if skills_dir_raw is not None else None
    if skills_dir == "":
        skills_dir = None

    ratio_raw = raw.get("memory_compact_ratio", 0.8)
    try:
        memory_compact_ratio = float(ratio_raw)
    except (TypeError, ValueError):
        memory_compact_ratio = 0.8
    if memory_compact_ratio <= 0:
        memory_compact_ratio = 0.8
    if memory_compact_ratio > 1:
        memory_compact_ratio = 1.0

    context_window_raw = raw.get("memory_context_window_tokens", 128000)
    try:
        memory_context_window_tokens = int(context_window_raw)
    except (TypeError, ValueError):
        memory_context_window_tokens = 128000
    memory_context_window_tokens = max(1000, memory_context_window_tokens)

    def _to_float_or_none(value: object) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed < 0:
            return None
        return parsed

    pricing_currency_raw = str(raw.get("pricing_currency", "CNY")).strip().upper() or "CNY"
    pricing_input_per_million = _to_float_or_none(raw.get("pricing_input_per_million"))
    pricing_output_per_million = _to_float_or_none(raw.get("pricing_output_per_million"))
    pricing_cache_read_per_million = _to_float_or_none(raw.get("pricing_cache_read_per_million"))
    pricing_cache_write_per_million = _to_float_or_none(raw.get("pricing_cache_write_per_million"))

    return AppConfig(
        provider=str(raw["provider"]),
        model_name=str(raw["model_name"]),
        base_url=str(raw["base_url"]),
        api_key_env=api_key_env,
        api_key=api_key,
        timeout_seconds=int(raw.get("timeout_seconds", 60)),
        default_loop_version=str(raw.get("default_loop_version", "v1")),
        mcp_servers=mcp_servers,
        skills_dir=skills_dir,
        memory_compact_ratio=memory_compact_ratio,
        memory_context_window_tokens=memory_context_window_tokens,
        pricing_currency=pricing_currency_raw,
        pricing_input_per_million=pricing_input_per_million,
        pricing_output_per_million=pricing_output_per_million,
        pricing_cache_read_per_million=pricing_cache_read_per_million,
        pricing_cache_write_per_million=pricing_cache_write_per_million,
    )
