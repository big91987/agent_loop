# Config Profiles

- `default.json`: default local profile (no MCP server).
- `v4_mcp_simple.json`: enables a simple MCP server at `./mcp_servers/demo/simple_server.py`.

Usage:

```bash
python3 cli.py --config ./configs/default.json --loop v3
python3 cli.py --config ./configs/v4_mcp_simple.json --loop v4
```
