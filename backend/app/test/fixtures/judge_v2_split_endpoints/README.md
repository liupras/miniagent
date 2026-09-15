# JudgeAPI V2 双接口冻结契约

修订标识：`2026-09-13-split-endpoints`。本目录是 `/judge/law-check` 与 `/judge/next-action` 的共享契约源。旧 `JudgeV2` 和 `JudgeV2LegalExtension` 目录只保留历史记录，不再定义当前接口。

## 内容

- `protocol-frozen.md`：冻结时的协议快照。
- `schemas/`：四份 Draft 2020-12 请求/响应 Schema。
- `manifest.json` 与 `cases/`：合法、非法及请求绑定响应样例。
- `contexts/`：验证响应权限、目标和状态版本时使用的请求。
- `behavior-scenarios.json`：工具、模型语义、播放恢复和状态机验收要求。
- `limits.json`：字节、码点、超时和纠错边界。
- `integrity.json`：冻结文件的 SHA-256 清单。
- `verify_fixtures.py`：离线契约和完整性验证器。
- `build_fixtures.py`：显式重新冻结生成器，不调用应用、LLM 或检索服务。

## 接口边界

| 端点 | 请求重点 | 响应决策 |
| --- | --- | --- |
| `/api/v2/integrations/virtual-court/judge/law-check` | `state_version`、`role`、`text`、可选 `context` | `NO_ACTION`、`EXPLAIN_LAW`、`HANDOFF` |
| `/api/v2/integrations/virtual-court/judge/next-action` | 允许动作、案件上下文、完整相关记录 | `ASK/COMPLETE/HANDOFF` |

法律检查请求禁止完整 `records`，响应没有 `target`。流程请求和响应禁止 `EXPLAIN_LAW`、`NO_ACTION`。

静态 Schema 通过不证明真实模型正确理解普通陈述，也不证明工具调用和客户端恢复链已经实现；这些要求必须按 `behavior-scenarios.json` 另行验证。

## 验证

```powershell
python verify_fixtures.py
```

成功时退出码为 0，并报告全部样例与完整性检查通过。
