#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json

from core.client import OpenAICompatClient
from core.config import load_config
from core.logging_utils import create_session_logger
from core.mcp_client import MCPManager
from loops.agent_loop_v1_basic import V1BasicLoop
from loops.agent_loop_v2_tools import V2ToolsLoop
from loops.agent_loop_v3_tools import V3ToolsLoop
from loops.agent_loop_v4_mcp_tools import V4MCPToolsLoop
from loops.agent_loop_v5_skill_tools import V5SkillToolsLoop


async def _read_line(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Teaching CLI for agent loop v1-v5")
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--loop", choices=["v1", "v2", "v3", "v4", "v5"], default=None)
    parser.add_argument("--debug", action="store_true", help="Reserved verbose flag (payload logs are always written)")
    parser.add_argument("--log-dir", default="./logs", help="Directory for session log files")
    args = parser.parse_args()

    cfg = load_config(args.config)
    loop_version = args.loop or cfg.default_loop_version
    if loop_version not in {"v1", "v2", "v3", "v4", "v5"}:
        raise ValueError(f"Unsupported loop version: {loop_version}")

    logger, log_path = create_session_logger(log_dir=args.log_dir, debug=args.debug)
    logger.info("startup loop=%s model=%s provider=%s", loop_version, cfg.model_name, cfg.provider)

    client = OpenAICompatClient(
        base_url=cfg.base_url,
        api_key_env=cfg.api_key_env,
        api_key=cfg.api_key,
        debug=args.debug,
        logger=logger,
    )
    mcp_manager = MCPManager(cfg.mcp_servers or []) if cfg.mcp_servers else None

    loops = {
        "v1": V1BasicLoop(client=client, model_name=cfg.model_name, timeout_seconds=cfg.timeout_seconds),
        "v2": V2ToolsLoop(
            client=client,
            model_name=cfg.model_name,
            timeout_seconds=cfg.timeout_seconds,
        ),
        "v3": V3ToolsLoop(
            client=client,
            model_name=cfg.model_name,
            timeout_seconds=cfg.timeout_seconds,
            default_tool_cwd=".",
        ),
        "v4": V4MCPToolsLoop(
            client=client,
            model_name=cfg.model_name,
            timeout_seconds=cfg.timeout_seconds,
            default_tool_cwd=".",
            mcp_manager=mcp_manager,
            mcp_enabled=bool(cfg.mcp_servers),
        ),
        "v5": V5SkillToolsLoop(
            client=client,
            model_name=cfg.model_name,
            timeout_seconds=cfg.timeout_seconds,
            default_tool_cwd=".",
            mcp_manager=mcp_manager,
            mcp_enabled=bool(cfg.mcp_servers),
            skills_dir=cfg.skills_dir,
        ),
    }

    print(f"agent-loop suite started | loop={loop_version} | model={cfg.model_name}")
    print(f"log file: {log_path}")
    print("Commands: /quit, /loop v1|v2|v3|v4|v5, /state")
    print("V4/V5 Commands: /mcp list|on|off|refresh")
    print("V5 Commands: /skill list|use <name>|off")

    while True:
        user_input = (await _read_line("> ")).strip()
        if not user_input:
            continue
        if user_input == "/quit":
            return 0
        if user_input.startswith("/loop "):
            candidate = user_input.split(" ", 1)[1].strip()
            if candidate not in {"v1", "v2", "v3", "v4", "v5"}:
                print("Only v1/v2/v3/v4/v5 are available in this stage.")
                continue
            loop_version = candidate
            logger.info("switch loop=%s", loop_version)
            print(f"Switched to {loop_version}")
            continue
        if user_input == "/state":
            print(json.dumps(loops[loop_version].get_messages(), ensure_ascii=True, indent=2))
            continue
        if user_input.startswith("/mcp "):
            loop = loops.get(loop_version)
            if not isinstance(loop, V4MCPToolsLoop):
                print("/mcp commands are only available in v4/v5")
                continue
            action = user_input.split(" ", 1)[1].strip()
            if action == "list":
                names = loop.list_mcp_tools()
                if names:
                    print("\n".join(names))
                else:
                    print("(no mcp tools)")
                continue
            if action == "on":
                await loop.set_mcp_enabled(True)
                print("MCP enabled")
                continue
            if action == "off":
                await loop.set_mcp_enabled(False)
                print("MCP disabled")
                continue
            if action == "refresh":
                await loop.refresh_mcp_tools()
                print("MCP tools refreshed")
                continue
            print("Usage: /mcp list|on|off|refresh")
            continue
        if user_input.startswith("/skill "):
            loop = loops.get(loop_version)
            if not isinstance(loop, V5SkillToolsLoop):
                print("/skill commands are only available in v5")
                continue
            action = user_input.split(" ", 1)[1].strip()
            if action == "list":
                names = loop.list_skills()
                print("\n".join(names) if names else "(no skills)")
                continue
            if action.startswith("use "):
                name = action.split(" ", 1)[1].strip()
                if not name:
                    print("Usage: /skill use <name>")
                    continue
                if loop.use_skill(name):
                    print(f"Skill enabled: {name}")
                else:
                    print(f"Skill not found: {name}")
                continue
            if action == "off":
                loop.disable_skill()
                print("Skill disabled")
                continue
            print("Usage: /skill list|use <name>|off")
            continue

        text = await loops[loop_version].run_turn(user_input)
        print(text)


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
