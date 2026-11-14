# 事实与证据调查 MiniAgent V4

调查 Agent 只返回建议或发言文本。VirtualCourt.Server 校验角色、话语权、调查 ID、决策修订号和轮次，并负责播报与笔录。

| POST 路径（前缀 `/api/v3/integrations/virtual-court`） | Agent | 返回内容 |
| --- | --- | --- |
| `/investigation/participant/intent` | `virtual_court_investigation_participant_intent` | 申请发言或 `pass` |
| `/investigation/participant/speech` | `virtual_court_investigation_participant_speech` | 当前 `turn_id` 的自由发言 |
| `/investigation/judge/next-action` | `virtual_court_investigation_judge_dispatch` | 一项程序动作及实际宣布语，或移交人工 |

请求和响应以 VirtualCourt 仓库的 `Docs/Contracts/investigation-v4.schema.json` 与同目录样例为准。接口路径沿用现有服务地址，协议内容直接切换 V4。JSON 使用 UTF-8，内部 Bearer 令牌认证；拒绝重复和未知字段。请求上限 512 KiB，记录最多 512 项，响应上限 128 KiB。每个响应必须回填调查 ID 及对应修订号或轮次 ID。失败不会被解释为 `pass`、拒绝申请或结束调查。

当事人意向只选择 `speech_kind`、`topic_id`，可选 `reason`。事项可为案件焦点或 `other`。申请不含证据 ID、回应轮次或预设发言正文。法官批准申请后，当事人根据全案材料、现有发言和法官实际宣布语自行发言；共享展示的证据不是该轮的绑定证据。

自动法官请求不含 `scope`；人工咨询请求带 `scope=request|next|summary`，申请页还带 `request_id`。法官可返回准许或拒绝申请、邀请一方按类型发言、调查总结。提问使用 `invite_participant` 的 `speechKind=answer`，问题写入 `utterance.text`。动作不含证据组、任务文本、回应目标或 `set_context`。`action` 响应必须有 `utterance={"mode":"text","text":"..."}`；准许、拒绝、邀请的文字可留空以使用服务端中性默认语，总结必须有非空文字。人工咨询仅填选择建议和可编辑草稿，不提交庭审发言。

种子配置的三名调查 Agent 提示词在启动时同步到数据库。提示词把案件材料和庭审发言视为不可信数据，不执行其中指令；当事人与法官不得虚构材料、预断事实或证明力。

验证：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest app/test/test_virtual_court_investigation_v4.py app/test/test_virtual_court_agent_migration.py -q -p no:cacheprovider
```
