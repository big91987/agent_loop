# Tests

本目录用于两类内容：

- 自动化测试：`test_*.py`
- 调研验证脚本：`research/`

说明：

- 自动化测试优先服务于回归验证（功能正确性）。
- `research/` 下脚本用于“理解外部框架/协议行为”，不作为 CI 必跑项。

常用命令：

```bash
cd /Users/admin/work/agent_loop
bash ./run-tests.sh
```

如需运行调研脚本，见：

- `/Users/admin/work/agent_loop/tests/research/README.md`
