# OpenViking 深度调研报告（Case13 真实验证）

## 0. README/论文亮点（先看这个）

基于 OpenViking README 与源码，memory 相关主张可归纳为：
- `Context DB`：memory / resource / skill 统一在 `viking://` 范式
- `Session-to-memory`：会话提交后自动抽取长期记忆，不是只做即时检索
- `多类别抽取`：按 profile / preferences / entities / events / ... 组织
- `抽取后处理`：包含 merge / dedup / enqueue vectorization 等流程

本文后续映射：
- 组件定位对应 `1`
- 机制对应 `2`
- 真实验证对应 `3-5`

术语先读：
- `docs/memory/memory_terms_compare.md`（本系统对应：最小单位=`memory file`，按 profile/preferences/entities/events 等分层）

## 1. 组件定位（What）

OpenViking 是“上下文数据库”形态，memory 只是其子模块之一。

本次只验证 memory 子链路：
1. 会话消息写入
2. 提交会话触发抽取
3. 记忆落盘到 `viking://user/default/memories`
4. 对 memories 路径执行检索

### 1.1 本系统术语与对象模型（OpenViking 原生）

- 最小对象名词：`memory file`（URI 形态为 `viking://.../memories/...`）
- 组织方式：路径/目录分层（如 `profile/preferences/entities/events`）
- 检索对象：memory URI 对应的文件内容

说明：OpenViking 是路径空间 + 文件分层模型，不是 item/type/category 模型。

### 1.2 围绕模型管理记忆（OpenViking）

典型交互节奏：
1. 会话提交后触发 memory extraction，生成 `viking://.../memories/...` 文件。
2. 文件入索引后，对模型当前 query 执行 `search/find`。
3. 命中的 memory 文件内容回注给模型，支持后续推理。

关键点：OpenViking 把 memory 放在统一路径空间里管理，模型侧通过检索接口按需取回。

## 2. 机制（How）

### 2.1 抽取
- 入口：`commit_session(...)`
- 行为：从 session 消息提取候选长期记忆，日志可见 `Extracted N candidate memories`

### 2.2 存储
- 抽取后写入 memory 文件（profile/preferences/entities/events）
- 同时 enqueue 向量化，进入检索后端

### 2.3 检索
- 本次调用：
  - `search(target_uri="viking://user/default/memories")`
  - `find(target_uri="viking://user/default/memories")`

## 3. 测试验证（论文主张 ↔ 实测结果对齐）

### 3.0 本轮最终口径（以 clean env 复测为准）

为避免 `py312` 环境里的依赖污染，本轮最终结论以专用环境 `openviking-clean` 下的真实复测为准。

最终确认：
- `写入`：通。真实 `.md` 记忆文件已经落到 `workspace_case13_1773479686/viking/...`。
- `检索`：通。`glob/search/find/read` 都能返回和读取真实 memory URI。
- `问题焦点`：不是“没落盘”，也不是“完全检索异常”，而是**检索排序和 abstract 质量一般**。

### 3.1 目标1：了解原理是否可观测

| 主张 | 可观测信号 | 实测 | 结论 |
|---|---|---|---|
| 会话可抽取长期记忆 | 日志里出现 `Extracted N candidate memories` | 出现：`Extracted 9 candidate memories` | 抽取链路生效 |
| 记忆会被持久化 | memory 文件 URI 被创建，且本地 `.md` 可见 | 真实文件存在于 `workspace_case13_1773479686/viking/default/user/default/memories/...` | 落盘链路生效 |
| 可对 memory 范围检索 | `search/find/read` 返回 `memories` URI 且可读正文 | `glob` 列出 9 个 memory URI，`read(uri)` 可读正文 | 检索链路生效 |

### 3.2 目标2：Case13 最终提取了什么、怎么存

实测提取到的核心内容（来自抽取日志 + memory 文件内容）：
- 身份：李明、星云科技、产品经理、北京迁上海
- 偏好：讨厌香菜；喝咖啡从冰美式换拿铁；飞机偏好靠窗
- 实体：奶油（布偶猫）、小雨（女友）
- 事件：内部机器学习分享、计划带女友去云南

存储形态：
- workspace：`backups/memory/openviking_runtime/workspace_case13_<ts>`
- 记忆路径：`viking://user/default/memories/...`
- 文件分层：`profile.md` + `preferences/*.md` + `entities/*.md` + `events/*.md`

本轮最终确认到的真实内容层路径（相对 `workspace_case13_1773479686/`）：
- `viking/default/user/default/memories/profile.md`
- `viking/default/user/default/memories/preferences/*.md`
- `viking/default/user/default/memories/entities/*.md`
- `viking/default/user/default/memories/events/*.md`

索引层路径：
- `vectordb/store/*`
- `vectordb/context/index/default/versions/*`

说明：
- `viking/...` 存**可读正文**
- `vectordb/...` 存**检索索引**

### 3.3 目标3：抽取/检索效果与不足分析

抽取效果：
- 关键记忆点覆盖度较好，Case13 的主事实都进入 memory 文件。

检索效果：
- 检索接口本身是通的：`search`、`find`、`read` 都能工作。
- 例如 query `给我推荐个咖啡。` 时，Top1 能命中咖啡偏好文件：
  - `viking://user/default/memories/preferences/mem_68e75dee-5bb8-4d5d-9292-9ee74111d658.md`
- 但后续高位结果仍混入：
  - 王家卫剧偏好
  - 靠窗座位偏好
  - 香菜偏好
- 这说明当前问题在**排序不够干净**，不是“搜不到”。

不足原因（本次可见层面）：
- 检索目标路径是整个 memories 根目录，当前更偏宽召回。
- 输出层没有明显按 query 强约束收敛到少量最相关记忆。
- `abstract` 字段质量一般，出现过长摘要和 `<think>` 风格噪声；但底层 `.md` 正文是正常的。

## 4. 学生证据清单（已摘好）

原始输出：
- `backups/memory/openviking_case13_output.txt`
- `backups/memory/openviking_runtime/workspace_case13_1773479686`

关键证据：
- 抽取触发：`Extracted 9 candidate memories (language=zh-CN)`
- 持久化（clean env 最终实物）：
  - `workspace_case13_1773479686/viking/default/user/default/memories/profile.md`
  - `workspace_case13_1773479686/viking/default/user/default/memories/preferences/mem_68e75dee-5bb8-4d5d-9292-9ee74111d658.md`
  - `workspace_case13_1773479686/viking/default/user/default/memories/entities/mem_5e8166c3-d33b-4d10-9f3b-aca5b5106d19.md`
  - `workspace_case13_1773479686/viking/default/user/default/memories/events/mem_7893f66e-77e6-4b46-9cb9-fd2ca10e2a4c.md`
- 抽取内容示例：
  - `饮食偏好：不喜欢香菜`
  - `饮品偏好：喜欢拿铁，不喝冰美式`
  - `出行偏好：坐飞机喜欢靠窗座位`
  - `奶油：用户养的布偶猫`
  - `小雨：用户的女朋友`
- 检索触发与命中（clean env 直接 reopen）：
  - `glob('**/*.md', 'viking://user/default/memories') -> 9 个 URI`
  - `search('给我推荐个咖啡。') -> Top1 命中咖啡偏好文件`
  - `read(uri)` 能读出真实正文
- 存储路径：
  - `workspace_case13_<ts>`
  - `=== STORAGE PATHS ===`

## 5. 最终判断（针对 Case13）

- 原理链路：通了（会话 -> 抽取 -> 落盘 -> 检索 -> 读取正文）。
- 抽取质量：好（关键长期信息基本覆盖）。
- 检索质量：中等（能召回，Top1 常可命中，但排序偏宽，abstract 质量不稳）。

教学定位：
- 适合讲“上下文数据库型 memory”的完整链路。
- 也适合讲“抽取得好 ≠ 检索精排就足够好”。
