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

    raw_mcp_servers = raw.get("mcp_servers", [])
    mcp_servers: List[MCPServerConfig] = []
    if isinstance(raw_mcp_servers, list):
        for item in raw_mcp_servers:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            command = str(item.get("command", "")).strip()
            if not name or not command:
                continue
            args_raw = item.get("args", [])
            args = [str(part) for part in args_raw] if isinstance(args_raw, list) else []
            env_raw = item.get("env", {})
            env: Dict[str, str] = {}
            if isinstance(env_raw, dict):
                env = {str(k): str(v) for k, v in env_raw.items()}
            timeout = int(item.get("timeout_seconds", 30))
            mcp_servers.append(
                MCPServerConfig(
                    name=name,
                    command=command,
                    args=args,
                    env=env,
                    timeout_seconds=timeout,
                ),
            )

    skills_dir_raw = raw.get("skills_dir")
    skills_dir = str(skills_dir_raw).strip() if skills_dir_raw is not None else None
    if skills_dir == "":
        skills_dir = None

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
    )
