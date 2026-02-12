# MCP Servers

- `demo/simple_server.py`: simple MCP server for v4/v4.1/v5 validation and demos.
  - tools: `calculate`, `get_current_time`
  - resources: `simple://about`, `simple://usage`

Run manually (optional):

```bash
python3 ./mcp_servers/demo/simple_server.py
```

## MCP -> 模型 Function Call 转换（高德示例）

下面用一个特定 server（`amap`）说明“tools/resources 如何转换为模型可调用函数”。

假设 `amap` MCP server 暴露：
- tools: `geocode`, `route_drive`, `weather_now`
- resources: `amap://city_codes`, `amap://poi_categories`, `amap://quota_status`

### 1. tools 的转换

`tools/list` 返回的每个 tool，直接映射为一个 function tool：
- `mcp.amap.geocode`
- `mcp.amap.route_drive`
- `mcp.amap.weather_now`

参数 schema 直接复用 MCP tool 的 `inputSchema`。

### 2. resources 的转换

工程上通常不把每个 resource 写成一个固定函数，而是用两个桥接函数：
- `mcp.amap.resource_list`
- `mcp.amap.resource_read`

这样模型可以先列资源，再按 URI 读取，避免每增加一个 resource 都要改一套函数定义。

### 3. 运行时调用链（完整一轮）

1. 模型先调用：
   - `mcp.amap.resource_list({})`
2. loop 将其转换为 MCP 请求：
   - `resources/list`
3. 返回资源列表后，模型再调用：
   - `mcp.amap.resource_read({"uri":"amap://poi_categories"})`
4. loop 转换为 MCP 请求：
   - `resources/read`（`uri=amap://poi_categories`）
5. 读取结果以 `tool` message 回填给模型。
6. 模型再决定是否调用业务 tool，例如：
   - `mcp.amap.route_drive({...})`
7. loop 转换为：
   - `tools/call(name="route_drive", arguments={...})`

### 4. 为什么这样做

- 对 server 扩展友好：resource 数量变化时无需重写大量 function 定义。
- 对模型可控：模型仍可自主选择“先读哪个 resource，再调哪个 tool”。
- 对工程可控：权限、白名单、审计仍可在 loop 层统一拦截。
