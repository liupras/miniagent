# TranscriptAPI V2 冻结契约

修订标识：`2026-09-17-transcript-v2`。本目录是 `/api/v2/integrations/virtual-court/transcript/generate` 的离线契约基线，不表示接口或专用 Agent 已经实现。

## 内容

- `protocol-frozen.md`：冻结时的协议快照。
- `schemas/`：Draft 2020-12 请求和响应 Schema。
- `manifest.json` 与 `cases/`：合法、非法以及边界样例。
- `contexts/`：校验响应 `state_version` 时使用的请求。
- `behavior-scenarios.json`：模型语义、状态和安全验收要求。
- `limits.json`：字节、码点、记录数量和纠错边界。
- `integrity.json`：冻结文件的 SHA-256 清单。
- `verify_fixtures.py`：离线契约和完整性验证器。
- `build_fixtures.py`：显式重新冻结生成器，不导入应用或调用模型。

## 最小接口边界

| 方向 | 字段 |
| --- | --- |
| 请求 | `state_version`、`case_context`、`records` |
| 响应 | `state_version`、`transcript` |

`records` 允许 `SPEECH` 和 `SUMMARY`。摘要只能作为摘要处理，不能恢复或伪造逐字发言。

静态 Schema 通过不证明模型能够忠实生成笔录；相关要求必须按 `behavior-scenarios.json` 另行验证。

## 验证

```powershell
python verify_fixtures.py
```

成功时退出码为 0，并报告全部样例与完整性检查通过。
