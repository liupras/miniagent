# VirtualCourt → MiniAgent 独任审判员协议 V1.0

> 状态：冻结  
> 冻结日期：2026-08-29  
> 接口：`POST /api/v1/integrations/virtual-court/judge/decide`

## 1. 设计原则

协议只传递影响独任审判员智能体推理的内容，只返回 VirtualCourt 需要消费的决策结果。

- VirtualCourt 持有案件 ID、庭审会话 ID、恢复点和控制模式；
- MiniAgent 不保存或校验另一份庭审权威状态；
- 请求携带 `state_version`，响应原样回显，VirtualCourt 据此判断结果是否已经过期；
- HTTP 路径中的 `/api/v1` 已表示协议版本，请求体不再重复携带版本；
- 请求与响应的追踪由 HTTP 层处理，不进入模型上下文；
- 每次请求自包含，不传完整会话历史。

本协议只定义独任审判员动态决策。摘要和撰写能力应使用独立协议。

## 2. `state_version` 的用途

`state_version` 是协议安全字段，不是智能体推理内容。

VirtualCourt 发起请求时传入当前版本，MiniAgent 在响应中原样回显。VirtualCourt 收到响应后将其与当前权威状态版本比较，从而拒绝迟到结果。

VirtualCourt 应在本地处理：

```text
请求携带 state_version
→ 等待 MiniAgent 响应
→ 响应原样回显 state_version
→ 比较响应版本与 current_state_version
→ 相同才允许采用响应，不同则丢弃
```

同理，动态插入的恢复步骤、暂停前发言人和输入状态也由 VirtualCourt 本地保存。

## 3. 请求模型

模型：`JudgeDecisionRequest`

| 字段 | 类型 | 必填 | 推理用途 |
| --- | --- | --- | --- |
| `state_version` | integer | 是 | 协议安全字段；标记决策所基于的庭审状态版本，不进入模型提示词 |
| `current_stage` | string | 是 | 理解当前庭审阶段 |
| `current_step` | string | 是 | 理解当前冻结步骤和程序位置 |
| `trigger` | enum | 是 | 说明为什么调用智能体 |
| `task` | string | 是 | 本次唯一任务描述 |
| `current_speaker` | party/null | 否 | 确定当前发言人和提问对象 |
| `allowed_actions` | action[] | 是 | 限制智能体可建议的动作 |
| `allowed_targets` | party[] | 是 | 限制可提问或澄清的当事人 |
| `case_context` | object | 是 | 提供与判断有关的案情 |
| `stage_summaries` | object[] | 否 | 提供既往阶段的压缩上下文 |
| `recent_events` | object[] | 否 | 提供当前任务所需的近期庭审内容 |

请求禁止未定义字段。

### 3.1 已删除的请求字段

| 字段 | 删除原因 |
| --- | --- |
| `protocol_version` | URL 已使用 `/api/v1` |
| `request_id` | 属于 HTTP 追踪信息，不影响推理 |
| `case_id` | 案件身份不影响推理，案情由 `case_context` 提供 |
| `court_session_id` | 属于 VirtualCourt 会话管理 |
| `turn_id` | 属于 VirtualCourt 事件管理 |
| `control_mode` | MiniAgent 始终只返回建议，是否自动执行由 VirtualCourt 决定 |
| `script_guidance` | 与 `task` 重复，恢复点属于 VirtualCourt 内部状态 |
| `current_evidence` | 与 `task` 和 `recent_events` 重复；证据展示由 VirtualCourt 管理 |

### 3.2 触发类型

| 值 | 含义 |
| --- | --- |
| `LEGAL_QUESTION` | 回答知识产权法律问题 |
| `CLARIFICATION_NEEDED` | 要求当前发言人明确回答 |
| `SUPPLEMENTARY_QUESTION_NEEDED` | 生成一个受约束的补充问题 |
| `OFF_TOPIC_OR_VERBOSE` | 生成程序性提醒 |
| `SUMMARY_REQUESTED` | 中立归纳已确认内容 |
| `STAGE_READY` | 在允许范围内建议下一动作 |
| `MANUAL_ASSIST` | 为人工法官生成建议 |

### 3.3 动作类型

| 值 | 含义 |
| --- | --- |
| `NO_ACTION` | 不改变庭审状态 |
| `ASK_PARTY` | 向指定原告或被告提问 |
| `REQUEST_CLARIFICATION` | 要求指定当事人明确回答 |
| `SUMMARIZE` | 生成中立法庭归纳 |
| `PAUSE_SESSION` | 建议暂停演示 |
| `RESUME_SESSION` | 建议继续演示 |
| `END_CURRENT_SPEECH` | 建议结束当前发言 |
| `END_CURRENT_STAGE` | 建议结束当前阶段 |
| `ADVANCE_STEP` | 建议进入冻结的下一步骤 |
| `ADJOURN` | 建议按照冻结脚本休庭 |

`NO_ACTION` 始终隐式允许。其他动作必须属于 `allowed_actions`。

允许 `ASK_PARTY` 或 `REQUEST_CLARIFICATION` 时，`allowed_targets` 不得为空。返回目标必须属于该集合。

### 3.4 案情上下文

`case_context` 只保留：

| 字段 | 含义 |
| --- | --- |
| `cause_of_action` | 案由 |
| `procedure` | 审理程序 |
| `summary` | 冻结案情摘要 |
| `claims` | 原告诉请 |
| `defenses` | 被告抗辩 |
| `dispute_focuses` | 冻结争议焦点 |

案号、案件名称和法院名称属于展示或标识信息，不进入智能体推理请求。

### 3.5 阶段摘要和近期事件

阶段摘要：

```json
{
  "stage_id": "PARTY_STATEMENTS",
  "summary": "原告主张……；被告抗辩……"
}
```

近期事件：

```json
{
  "event_type": "PARTY_SPEECH_CONFIRMED",
  "actor": "DEFENDANT",
  "step_id": "INQUIRY-D-A",
  "content": "工作人员认为公开下载的图片可以使用。"
}
```

`recent_events` 数组必须由 VirtualCourt 按发生时间从旧到新排列。事件 ID 和序号不传给智能体。

## 4. 请求示例

```json
{
  "state_version": 18,
  "current_stage": "COURT_INVESTIGATION",
  "current_step": "INQUIRY-D-A",
  "trigger": "CLARIFICATION_NEEDED",
  "task": "要求被告明确说明使用图片前是否核验过商用授权。",
  "current_speaker": "DEFENDANT",
  "allowed_actions": [
    "NO_ACTION",
    "REQUEST_CLARIFICATION"
  ],
  "allowed_targets": [
    "DEFENDANT"
  ],
  "case_context": {
    "cause_of_action": "著作权侵权纠纷",
    "procedure": "民事一审简易程序",
    "summary": "原告主张被告未经许可将插画用于商业宣传。",
    "claims": [],
    "defenses": [],
    "dispute_focuses": [
      "被告使用涉案作品是否构成侵权"
    ]
  },
  "stage_summaries": [],
  "recent_events": [
    {
      "event_type": "PARTY_SPEECH_CONFIRMED",
      "actor": "DEFENDANT",
      "step_id": "INQUIRY-D-A",
      "content": "工作人员认为公开下载的图片可以使用。"
    }
  ]
}
```

## 5. 响应模型

模型：`JudgeDecisionResponse`

MiniAgent 内部分为两层：

- `JudgeAgentOutput`：约束大模型直接生成的 JSON，只包含 5 个业务字段；
- `JudgeDecisionResponse`：在校验通过后，由服务端把请求中的 `state_version` 注入 `JudgeAgentOutput` 得到。

大模型不得生成 `state_version`。这避免模型遗漏、改写或虚构状态版本。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| `state_version` | integer | 原样回显请求版本，供 VirtualCourt 拒绝迟到响应 |
| `speech` | object | VirtualCourt 可播报的候选法官发言 |
| `action` | object | 唯一候选动作 |
| `legal_citations` | object[] | 法律解释使用的可核验依据 |
| `confidence` | enum | `HIGH`、`LOW` 或 `INSUFFICIENT` |
| `warnings` | string[] | 依据不足或上下文冲突说明 |

模型必须只输出一个原始 JSON 对象，不得附加 Markdown 代码围栏、解释文字或前后缀。响应禁止未定义字段；5 个顶层字段全部必填，嵌套对象的字段也必须显式给出。无目标角色时输出 `"target_role": null`，空集合输出 `[]`。

### 5.1 已删除的响应字段

| 字段 | 删除原因 |
| --- | --- |
| `protocol_version` | URL 已包含版本 |
| `request_id` | 同步 HTTP 响应无需在业务体回显 |
| `decision_id` | MiniAgent 不执行状态变更，无需单独去重标识 |
| `case_id`、`court_session_id`、`turn_id` | 都是请求方内部标识 |
| `control_mode` | VirtualCourt 已持有控制模式 |
| `decision_basis` | 不影响执行且容易变成冗余推理文本 |
| `requires_human_review` | 与 `confidence` 和 `warnings` 重复；是否转人工由 VirtualCourt 的确定性规则决定 |
| `created_at` | HTTP 和服务日志已有时间记录 |

### 5.2 发言与动作一致性

- `ASK_PARTY` 必须对应 `QUESTION`；
- `REQUEST_CLARIFICATION` 必须对应 `CLARIFICATION`；
- `SUMMARIZE` 必须对应 `SUMMARY`；
- 提问和澄清必须指定 `target_role`；
- 其他发言类型不能指定目标。

### 5.3 法律 Citation

```json
{
  "source": "中华人民共和国著作权法",
  "article_no": "第五十三条",
  "excerpt": "可选的支持性原文片段"
}
```

- `source` 必填；
- `article_no` 字段始终保留，无条文编号时为空字符串；
- `excerpt` 字段始终保留，无支持性原文时为 `null`；
- 法律解释没有 Citation 时，`confidence` 必须为 `INSUFFICIENT`，并提供 `warnings`。

## 6. 响应示例

```json
{
  "state_version": 18,
  "speech": {
    "type": "CLARIFICATION",
    "text": "被告，请明确回答：使用涉案图片前，你方是否核验过上传者身份、授权范围或者商用许可？",
    "target_role": "DEFENDANT"
  },
  "action": {
    "type": "REQUEST_CLARIFICATION",
    "target_role": "DEFENDANT"
  },
  "legal_citations": [],
  "confidence": "HIGH",
  "warnings": []
}
```

## 7. VirtualCourt 的本地校验

MiniAgent 首先按严格 Schema 解析模型输出，并检查动作和目标是否在请求允许范围内；解析或检查失败时返回 `MODEL_RESPONSE_INVALID`，不得把未经校验的模型文本作为业务响应。

响应模型校验通过后，VirtualCourt 仍必须检查：

1. 本次 HTTP 调用是否仍是当前有效调用；
2. 响应的 `state_version` 是否仍等于当前权威状态版本；
3. 除 `NO_ACTION` 外，返回动作是否属于请求的 `allowed_actions`；
4. 返回目标是否属于请求的 `allowed_targets`；
5. 当前步骤是否仍允许动态插入；
6. 人工法官模式下是否已经取得人工确认。

任一检查失败，响应不得改变庭审状态。

## 8. 错误响应

错误模型不进入智能体推理：

```json
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "MiniAgent is temporarily unavailable.",
    "retryable": true,
    "details": {}
  }
}
```

支持的错误代码：

- `INVALID_REQUEST`
- `AUTHENTICATION_FAILED`
- `PERMISSION_DENIED`
- `RATE_LIMITED`
- `MODEL_RESPONSE_INVALID`
- `SERVICE_UNAVAILABLE`
- `UPSTREAM_TIMEOUT`
- `INTERNAL_ERROR`

## 9. HTTP 层职责

以下内容可以由后续 HTTP 实现或日志中间件处理，但不得注入模型上下文：

- 请求追踪 ID；
- 调用方身份和鉴权；
- 请求时间、响应时间和耗时；
- 限流；
- 模型与工具调用审计。

MiniAgent 只生成候选决定，不执行 VirtualCourt 状态变更，因此不在 Judge 协议中实现业务幂等存储。

### 9.1 JudgeService 调用约束

`JudgeService` 固定调用 `virtual_court_solo_judge`，不接受调用方指定其他 Agent。每次调用都是无会话、无历史的独立推理：服务只把请求中的推理字段和 `JudgeAgentOutput` JSON Schema 交给 Agent，不传递 `state_version`，也不写入 MiniAgent 会话记录。

Agent 最终文本必须经过严格 Schema、动作权限和目标权限校验。只有全部通过后，服务才从原请求回填 `state_version` 并返回 `JudgeDecisionResponse`。服务不执行候选动作，也不自动重试无效输出。

## 10. 代码位置

```text
backend/app/api/integrations/virtual_court/PROTOCOL_V1.md
backend/app/schemas/integrations/virtual_court/common.py
backend/app/schemas/integrations/virtual_court/judge.py
backend/app/services/virtual_court/judge_service.py
backend/app/services/virtual_court/response_validator.py
```

## 11. 后续接口

摘要和撰写能力可以复用 `/api/v1/integrations/virtual-court` 命名空间、鉴权和错误处理，但必须使用自己的请求和响应模型，不能把 Judge 接口扩展成通用 LLM 调用接口。
