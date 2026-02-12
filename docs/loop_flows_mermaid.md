# Agent Loop Flows (Mermaid)

本文档用于教学展示 `v1/v2/v3/v4/v4.1` 的执行流程差异。  
建议用支持 Mermaid 的 Markdown 工具查看（如 GitHub、Typora Mermaid 插件、VSCode Mermaid 预览插件）。  
若当前编辑器不支持 Mermaid，可直接查看同目录下已渲染的 SVG：
- `docs/diagrams/v1.svg`
- `docs/diagrams/v2.svg`
- `docs/diagrams/v3.svg`
- `docs/diagrams/v4.svg`
- `docs/diagrams/v4_1.svg`

## v1: Basic Chat Loop

![v1 flow](./diagrams/v1.svg)

```mermaid
flowchart LR
    U["User Input"] --> M["Append user message"]
    M --> L["Call LLM (no tools)"]
    L --> A["Append assistant message"]
    A --> O["Return assistant text"]
```

## v2: Teaching Tools Loop

![v2 flow](./diagrams/v2.svg)

```mermaid
flowchart LR
    U["User Input"] --> M["Append user message"]
    M --> L1["Call LLM with v2 tools"]
    L1 --> C{"Has tool_calls?"}
    C -- "No" --> A1["Append assistant final"]
    A1 --> O["Return final text"]
    C -- "Yes" --> T["Run teaching tool (calculate/get_current_time)"]
    T --> R["Append tool result message"]
    R --> L2["Call LLM again"]
    L2 --> C
```

## v3: CLI Tools Loop

![v3 flow](./diagrams/v3.svg)

```mermaid
flowchart LR
    U["User Input"] --> M["Append user message"]
    M --> L1["Call LLM with v3 tools"]
    L1 --> C{"Has tool_calls?"}
    C -- "No" --> A1["Append assistant final"]
    A1 --> O["Return final text"]
    C -- "Yes" --> N["Inject default cwd if missing"]
    N --> T["Run local tool (read/write/edit/grep/find/ls)"]
    T --> R["Append tool result message"]
    R --> L2["Call LLM again"]
    L2 --> C
```

## v4: MCP Tools Loop

![v4 flow](./diagrams/v4.svg)

```mermaid
flowchart LR
    U["User Input"] --> M["Append user message"]
    M --> L1["Call LLM with v3 + MCP tools"]
    L1 --> C{"Has tool_calls?"}
    C -- "No" --> A1["Append assistant final"]
    A1 --> O["Return final text"]
    O --> N2["Next turn"]
    N2 --> U
    C -- "Yes" --> K{"Tool source?"}
    K -- "Local" --> N["Inject default cwd if missing"]
    N --> T["Run local tool (read/write/edit/grep/find/ls)"]
    K -- "MCP" --> MT["Print MCP call and run mcp.<server>.<tool>"]
    T --> R["Append tool result message"]
    MT --> R
    R --> L2["Call LLM again"]
    L2 --> C
```

## v4.1: MCP + Resource Bridge Loop

![v4.1 flow](./diagrams/v4_1.svg)

```mermaid
flowchart LR
    U["User Input"] --> M["Append user message"]
    M --> L1["Call LLM with v3 + MCP + resource bridge tools"]
    L1 --> C{"Has tool_calls?"}
    C -- "No" --> A1["Append assistant final"]
    A1 --> O["Return final text"]
    O --> N2["Next turn"]
    N2 --> U
    C -- "Yes" --> K{"Tool source?"}
    K -- "Local" --> N["Inject default cwd if missing"]
    N --> T["Run local tool (read/write/edit/grep/find/ls)"]
    K -- "MCP tool" --> MT["Print MCP call and run mcp.<server>.<tool>"]
    K -- "MCP resource" --> MR["Print MCP call and run resource_list/resource_read"]
    T --> R["Append tool result message"]
    MT --> R
    MR --> R
    R --> L2["Call LLM again"]
    L2 --> C
```
