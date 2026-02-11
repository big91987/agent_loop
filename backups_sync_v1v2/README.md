# Python Agent Loop Teaching Suite

教学目标：用最小代码从 `v1`（纯对话）走到 `v2`（对话+工具调用）。

## 目录

- `config.json`: 公共模型配置（OpenAI 风格）
- `cli.py`: 教学 CLI 入口
- `core/`: 配置、客户端抽象、工具定义
- `loops/agent_loop_v1_basic.py`: v1 基础 loop
- `loops/agent_loop_v2_tools.py`: v2 工具 loop
- `tests/`: v1/v2 测试

## 配置

`config.json` 字段：
- `provider`: 供应商标识（教学版仅做信息保留）
- `model_name`: 模型名
- `base_url`: OpenAI-compatible API 地址
- `api_key`: 可选，直接填写 API Key（教学环境可用，生产不建议）
- `api_key_env`: API Key 环境变量名（可选，默认 `OPENAI_API_KEY`）
- `timeout_seconds`: 请求超时
- `default_loop_version`: 默认 loop（`v1` 或 `v2`）

## 运行 CLI

```bash
cd /Users/zhaojiuzhou/work/pi-mono/python-agent-suite
python3 cli.py --config ./config.json --loop v1
python3 cli.py --config ./config.json --loop v1 --debug
```

交互命令：
- `/loop v1|v2`
- `/state`
- `/quit`

## 运行测试

```bash
cd /Users/zhaojiuzhou/work/pi-mono/python-agent-suite
bash ./run-tests.sh
```

## 版本说明

### v1
- 单轮：`user -> llm -> assistant`
- 不处理 tools

### v2
- 增加 tool 注册和调用闭环
- 流程：`user -> assistant(tool_call) -> execute tool -> toolResult -> assistant(final)`

## TODO（基于 PRD 的实现计划）

| 阶段 | 目标 | 关键内容 | 状态 |
|---|---|---|---|
| v1 | 最小可运行 loop | 单轮对话：`user -> llm -> assistant`，无 tools | 已完成 |
| v2 | 工具调用闭环 | tool 注册、tool_call 执行、toolResult 回填、再进 llm | 已完成 |
| v3 | 消息队列机制 | 增加 `steering` / `follow-up`，在 checkpoint 按优先级调度 | 待实现 |
| v4 | 中断机制 | 增加 `abort`（协作式取消）、工具取消 hook、超时兜底 | 待实现 |
| v5 | 运行时拆分 | `manager` 与 `agent_loop` 分协程，强化状态机与事件流 | 待实现 |
