# Config Profiles

- `default.json`: default local profile (no MCP server).
- `v4_mcp_simple.json`: enables a simple MCP server at `./mcp_servers/demo/simple_server.py`.
- `v4_1_mcp_simple.json`: same simple MCP server, with `default_loop_version` set to `v4.1` (includes MCP resource bridge tools).
- `v4_1_mcp_playwright.json`: Playwright MCP profile for browser automation in `v4.1`.
- `v4_1_mcp_amap_node.json`: AMap MCP profile using Node.js I/O (`npx` + stdio) for `v4.1`.
- `v5_skill_pi_style.json`: v5 profile using pi-mono style skill progressive disclosure with `~/.claude/skills`.
- `v6_1_short_memory.json`: v6.1 profile for session + short-memory compaction.
  - `memory_compact_ratio`: compact trigger ratio (e.g. `0.8`)
  - `memory_context_window_tokens`: model context window size used to derive threshold
  - effective threshold: `memory_context_window_tokens * memory_compact_ratio`
  - billing (optional):
    - `pricing_currency`: display currency code (`CNY`/`USD`)
    - `pricing_input_per_million`: input token unit price (per 1,000,000 tokens)
    - `pricing_output_per_million`: output token unit price (per 1,000,000 tokens)
    - `pricing_cache_read_per_million`: cache-read token unit price (reserved field)
    - `pricing_cache_write_per_million`: cache-write token unit price (reserved field)
- `v6_2_memory_simplemem.json`: v6.2 profile for short-memory + long-memory tools.
  - `workspace_path` (optional): workspace root; relative `sessions/logs/history/memory` paths are resolved under it
  - when `workspace_path` is not set, paths stay relative to current working directory (`pwd`)
  - `memory_user_id`: logical memory owner id (for isolation)
  - `memory_store_path_template`: long-memory store template; supports `{user}` or `{memory_user_id}`
  - `memory_store_path`: fixed long-memory store path (used when template is not provided)
- `v7_memory_simplemem.json`: v7 profile for `Phase 01 / Runtime Kernel`, preserving the v6.3 `simplemem` memory runtime baseline.
  - `memory_backend`: `simplemem`
  - `memory_system_dir`: `/Users/admin/work/agent_loop/memory_systems/v6_3_simplemem`
  - `memory_artifact_dir`: relative artifact root, resolved under workspace if `workspace_path` is set
  - `runtime_env`: optional per-config env injection, supported only by `cli_v7.py`; non-empty values are loaded into the current process before config parsing
- `v7_memory_evermemos.json`: v7 profile for `Phase 01 / Runtime Kernel`, using the `evermemos` backend.
  - `memory_backend`: `evermemos`
  - `memory_system_dir`: `/Users/admin/work/agent_loop/memory_systems/v6_3_evermemos`
  - `memory_artifact_dir`: `./memory/evermemos`
  - `repo_root`: `/Users/admin/work/EverMemOS`
  - `runtime_env`: optional per-config env injection, supported only by `cli_v7.py`; typical keys are `MINIMAX_API_KEY`, `ZHIPU_API_KEY`, `MONGODB_HOST`

`mcpServers.<name>.type` supported values:
- `stdio`: use `command` + `args` + `env`
- `sse`: use `url` (optional `message_url`) + `headers`
- `streamable_http`: use `url` + `headers`

`mcpServers.<name>.stdio_msg_format` (for `type=stdio`):
- `auto` (default): try `line` first, fallback to `content-length`
- `line`: newline-delimited JSON-RPC
- `content-length`: Content-Length framed JSON-RPC

Usage:

```bash
python3 cli.py --config ./configs/default.json --loop v3
python3 cli.py --config ./configs/v4_mcp_simple.json --loop v4
python3 cli.py --config ./configs/v4_1_mcp_simple.json --loop v4.1
python3 cli.py --config ./configs/v4_1_mcp_playwright.json --loop v4.1
python3 cli.py --config ./configs/v4_1_mcp_amap_node.json --loop v4.1
python3 cli.py --config ./configs/v5_skill_pi_style.json --loop v5
python3 cli_v6_1.py --config ./configs/v6_1_short_memory.json
python3 cli_v6_2.py --config ./configs/v6_2_memory_simplemem.json
python3 cli_v6_2.py --config ./configs/v6_2_memory_simplemem.json --workspace-path /tmp/demo_workspace
python3 cli_v7.py --config ./configs/v7_memory_simplemem.json
python3 cli_v7.py --config ./configs/v7_memory_evermemos.json
```

Notes:

- `runtime_env` is currently implemented only in `cli_v7.py`.
- Empty `runtime_env` values are ignored; fill in the keys you actually want the v7 process to load.
