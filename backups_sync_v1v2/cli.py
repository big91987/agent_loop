#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from core.client import OpenAICompatClient
from core.config import load_config
from loops.agent_loop_v1_basic import AgentStateV1, run_turn_v1
from loops.agent_loop_v2_tools import AgentStateV2, run_turn_v2
from tools.registry import get_default_tools


def main() -> int:
    parser = argparse.ArgumentParser(description="Teaching CLI for agent loop v1/v2")
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--loop", choices=["v1", "v2"], default=None)
    parser.add_argument("--debug", action="store_true", help="Print raw request/response payloads")
    args = parser.parse_args()

    cfg = load_config(args.config)
    loop_version = args.loop or cfg.default_loop_version
    if loop_version not in {"v1", "v2"}:
        raise ValueError(f"Unsupported loop version: {loop_version}")

    client = OpenAICompatClient(
        base_url=cfg.base_url,
        api_key_env=cfg.api_key_env,
        api_key=cfg.api_key,
        debug=args.debug,
    )
    tools = get_default_tools()

    state_v1 = AgentStateV1()
    state_v2 = AgentStateV2()

    print(f"agent-loop suite started | loop={loop_version} | model={cfg.model_name}")
    print("Commands: /quit, /loop v1|v2, /state")

    while True:
        user_input = input("> ").strip()
        if not user_input:
            continue
        if user_input == "/quit":
            return 0
        if user_input.startswith("/loop "):
            candidate = user_input.split(" ", 1)[1].strip()
            if candidate not in {"v1", "v2"}:
                print("Only v1/v2 are available in this stage.")
                continue
            loop_version = candidate
            print(f"Switched to {loop_version}")
            continue
        if user_input == "/state":
            state = state_v1.messages if loop_version == "v1" else state_v2.messages
            print(json.dumps(state, ensure_ascii=True, indent=2))
            continue

        if loop_version == "v1":
            text = run_turn_v1(
                state=state_v1,
                client=client,
                model_name=cfg.model_name,
                user_input=user_input,
                timeout_seconds=cfg.timeout_seconds,
            )
        else:
            text = run_turn_v2(
                state=state_v2,
                client=client,
                model_name=cfg.model_name,
                user_input=user_input,
                tools=tools,
                timeout_seconds=cfg.timeout_seconds,
            )

        print(text)


if __name__ == "__main__":
    raise SystemExit(main())
