# Config Profiles

- `default.json`: default local profile (no MCP server).
- `v4_mcp_simple.json`: enables a simple MCP server at `./mcp_servers/demo/simple_server.py`.
- `v4_1_mcp_simple.json`: same simple MCP server, with `default_loop_version` set to `v4.1` (includes MCP resource bridge tools).
- `v4_1_mcp_playwright.json`: Playwright MCP profile for browser automation in `v4.1`.
- `v4_1_mcp_amap_node.json`: AMap MCP profile using Node.js I/O (`npx` + stdio) for `v4.1`.
- `v5_skill_pi_style.json`: v5 profile using pi-mono style skill progressive disclosure with `~/.claude/skills`.

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
```
