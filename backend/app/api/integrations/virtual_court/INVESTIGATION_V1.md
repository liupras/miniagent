# 统一法庭调查 MiniAgent V1

这组接口独立于旧 Judge API V2 和 Party Reply API V1。它们只返回建议或文本；VirtualCourt.Server 校验轮次、修订号和角色后才修改房间。法庭调查期间不调用旧调查法官或旧当事人回复 Agent。

| POST 路径（统一前缀 `/api/v3/integrations/virtual-court`） | Agent | 输出 |
| --- | --- | --- |
| `/investigation/participant/intent` | `virtual_court_investigation_participant_intent` | `request` 或 `pass` |
| `/investigation/participant/speech` | `virtual_court_investigation_participant_speech` | 当前 `turn_id` 的发言 |
| `/investigation/judge/next-action` | `virtual_court_investigation_judge_dispatch` | 一项法官动作或 `handoff` |

请求与响应形状以 VirtualCourt 的 `Docs/Contracts/investigation-v1.schema.json` 中 `participantIntent*`、`participantSpeech*`、`judgeNextAction*` 定义为准。使用 UTF-8 JSON、内部 Bearer 令牌，拒绝重复字段和未知字段；请求上限 512 KiB，记录最多 512 项。响应必须原样回填 `investigation_id` 以及本次 `decision_revision` 或 `turn_id`。可选关联 ID 在申请和动作中按契约显式使用 `null`。错误按现有集成接口格式返回：422 为输入契约或模型上下文问题，502 为模型输出无效，503 为配置或上游不可用，504 为超时。失败不会产生 `pass`、拒绝申请或结束调查的动作。

三名 Agent 均无工具绑定。各次调用共享一个超时预算，输出失败最多修复一次；修复仍失败则报错。请求包含完整案件摘要、各方立场、事项、证据目录及可读取材料、调查状态和有序记录，不静默截断。提示词把材料与庭审发言视作数据，禁止虚构材料、认定事实和评价证据证明力。

启动时种子配置把新 Agent 的提示词同步至 SQLite；旧 Agent 保持原有名称和提示词。当前数据库也应存在三个启用的新 Agent。

验证：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider app/test/test_virtual_court_investigation_v3.py
```
