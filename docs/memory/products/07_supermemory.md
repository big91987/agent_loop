# Supermemory 调研报告（Case13 状态版）

## 0. README亮点（先看这个）
- `API-first memory platform`：以平台 API 形式提供记忆能力。
- `MCP / 多客户端`：强调工具接入与产品化能力。
- `项目/容器隔离`：工程侧多空间管理。

## 1. 组件定位与对象模型
- 仓库: `https://github.com/supermemoryai/supermemory`
- 本地代码: `/tmp/memory_scan_round2/supermemory`
- 本轮目标: 使用共享 `case13` 跑真实写入/检索。

核心对象（平台侧）：
- `memory/document`：平台资源对象。
- `project/container`：隔离与组织边界。

## 2. 怎么用（最小调用）
典型使用方式：
1. 通过 Supermemory API 写入 memory/document
2. 调用 search 接口检索
3. 上层 agent 回注检索结果

## 3. 原理（抽取/存储/检索/注入）
- 抽取：由平台后端执行（仓库内不提供等价本地离线记忆引擎）。
- 存储：平台侧托管存储与索引。
- 检索：平台 API 搜索。
- 注入：由客户端/agent 自行回注。

## 4. Case13 效果验证（当前状态）
- 本地仓库可读到 SDK/工具封装。
- 但完整 `case13` 真实链路依赖 Supermemory 在线 API 凭证；当前环境未提供 `SUPERMEMORY_API_KEY`。
- 因此本轮对 Supermemory 的 `case13` 结果状态是：`未完成（凭证缺失）`。

## 5. 结论
- Supermemory 更偏“平台化记忆服务”，而非本地可完全离线复现的记忆组件。
- 在缺少平台凭证时，只能完成接口与对象模型分析，不能完成 case13 实测。
- 下一步要完成 case13：补齐 API key 后跑统一脚本并输出完整原文。
