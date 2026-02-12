# Config Profiles

- `default.json`: default local profile (no MCP server).
- `v4_mcp_simple.json`: enables a simple MCP server at `./mcp_servers/demo/simple_server.py`.
- `v4_1_mcp_simple.json`: same simple MCP server, with `default_loop_version` set to `v4.1` (includes MCP resource bridge tools).
- `v4_1_mcp_playwright.json`: Playwright MCP profile for browser automation in `v4.1`.

`mcp_servers[].type` supported values:
- `stdio`: use `command` + `args` + `env`
- `sse`: use `url` (optional `message_url`) + `headers`
- `streamable_http`: use `url` + `headers`

Usage:

```bash
python3 cli.py --config ./configs/default.json --loop v3
python3 cli.py --config ./configs/v4_mcp_simple.json --loop v4
python3 cli.py --config ./configs/v4_1_mcp_simple.json --loop v4.1
python3 cli.py --config ./configs/v4_1_mcp_playwright.json --loop v4.1
```
