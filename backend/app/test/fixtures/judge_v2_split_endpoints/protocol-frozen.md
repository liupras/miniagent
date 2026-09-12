# VirtualCourt → MiniAgent JudgeAPI 对接协议 V2

> 状态：双接口协议，待 MiniAgent 与 VirtualCourt 按本文实现和联调<br>
> 日期：2026-09-13<br>
> 适用阶段：法官询问与调查总结、法庭辩论

本文是当前唯一有效的 JudgeAPI V2 契约。旧端点 `POST /api/v2/integrations/virtual-court/judge/decide` 已废弃，不要求兼容。

本契约的 Schema、正反例、行为场景和完整性清单位于 [JudgeV2SplitEndpoints](../Tests/Fixtures/JudgeV2SplitEndpoints/README.md)，冻结修订为 `2026-09-13-split-endpoints`。静态契约通过不代表接口或模型行为已经实现。

| 用途 | 方法与路径 |
| --- | --- |
| 当事人发言完成后的法律检查 | `POST /api/v2/integrations/virtual-court/judge/law-check` |
| 到达明确流程决策点后的下一步动作 | `POST /api/v2/integrations/virtual-court/judge/next-action` |

## 1. 职责边界

- VirtualCourt 持有唯一权威庭审状态，负责发言顺序、争点顺序、轮次限制、播放、持久化、暂停、人工接管和阶段推进。
- VirtualCourt 不判断发言是否包含法律问题；每次原告或被告正式发言完成并入库后，固定调用法律检查接口。
- 法律检查接口只处理本次最新发言，必要时检索并解释法律，不推进流程。
- 到达调查或辩论的明确决策点后，VirtualCourt 单独调用下一步动作接口。
- 下一步动作接口不进行法律检查，不能返回 `EXPLAIN_LAW` 或 `NO_ACTION`。
- 每次调用无服务端会话记忆，请求必须自包含。
- JudgeAPI 不判断证据真伪、证据采信或证明力，不认定案件事实、责任或胜败，不生成实体裁判。

## 2. HTTP、鉴权与通用约定

| 项目 | 约定 |
| --- | --- |
| 请求、响应 | UTF-8 JSON，`Content-Type: application/json` |
| 鉴权 | `X-Integration-Key`，服务端使用 `VIRTUAL_COURT_API_KEY` |
| 追踪 | 可使用 `X-Request-ID`；只用于 HTTP 和日志 |
| 成功状态 | `200` |
| 客户端超时 | 建议 135 秒 |
| 服务端总预算 | 建议 120 秒 |

请求拒绝未知字段、重复 JSON 字段、非法枚举、超长字符串和过大请求体。密钥不得进入 URL、业务体或日志。

`state_version` 是非负 64 位整数，由 VirtualCourt 生成，MiniAgent 原样回填，不进入模型上下文。VirtualCourt 必须拒绝与当前版本不一致的响应。

## 3. 法律检查接口

### 3.1 调用条件

以下条件同时成立时调用：

1. 原告或被告的一段正式发言已经完成并入库；
2. 该 `state_version` 尚未完成法律检查；
3. 当前没有同版本法律检查请求在途；
4. 法官端处于 Agent 模式，庭审未暂停，也未进入人工接管。

不要对未确认的语音片段逐字调用。固定法官台词、法律解释、流程 Agent 发言和系统提示不触发法律检查。

### 3.2 请求 `JudgeLawCheckRequestV2`

```json
{
  "state_version": 101,
  "role": "PLAINTIFF",
  "text": "我方维持此前意见，没有法律问题需要解释。",
  "context": "当前争点：赔偿金额及维权费用是否合理。"
}
```

| 字段 | 类型 | 必填 | 约束与用途 |
| --- | --- | --- | --- |
| `state_version` | integer | 是 | 非负；本次发言对应的状态版本 |
| `role` | enum | 是 | 仅 `PLAINTIFF` 或 `DEFENDANT` |
| `text` | string | 是 | 非空，最多 8000 个 Unicode 码点；唯一允许触发法律解释的内容 |
| `context` | string | 否 | 默认 `""`，最多 16000 个 Unicode 码点；只用于确认法律问题后的指代理解、检索和解释 |

该请求不包含 `phase`、`records`、`allowed_decisions`、`allowed_targets`、完整 `case_context` 或 `current_issue`。

VirtualCourt 可不借助 LLM，将当前争点和简要案情机械拼接为 `context`。MiniAgent 必须把 `text` 作为唯一决策对象；`context` 即使含法律争议、法条或问句，也不能单独触发法律解释。

### 3.3 状态版本与去重

V2 不另设 `speech_id`，VirtualCourt 必须保证：

- 每次当事人正式发言提交后立即产生新的 `state_version`；
- 一个 `state_version` 只能对应一条待检查发言；
- 法律检查结果被消费前不得提交下一条正式发言；
- 同一版本的重试必须携带完全相同的 `role`、`text` 和 `context`；
- 同一版本的 `EXPLAIN_LAW` 最多保存、播放一次；
- 版本变化、暂停或人工接管后，旧响应和旧播放回调失效。

### 3.4 响应 `JudgeLawCheckResponseV2`

```json
{
  "state_version": 101,
  "decision": "NO_ACTION",
  "speech": "",
  "pending_points": []
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `state_version` | integer | 从请求原样回填 |
| `decision` | enum | `NO_ACTION`、`EXPLAIN_LAW` 或 `HANDOFF` |
| `speech` | string | `NO_ACTION` 必须为 `""`；其他决策必须非空，最多 4000 个 Unicode 码点 |
| `pending_points` | string[] | 最多 30 项；`NO_ACTION` 必须为空，`HANDOFF` 至少一项 |

法律检查响应没有 `target`。

| 决策 | 含义 | VirtualCourt 动作 |
| --- | --- | --- |
| `NO_ACTION` | 最新发言没有需要解释的新法律问题 | 标记该版本已检查，不播放，恢复原流程 |
| `EXPLAIN_LAW` | 最新发言明确提出法律问题，且本次检索取得充分依据 | 保存并播放解释，成功后恢复原流程 |
| `HANDOFF` | 工具不可用、检索失败、依据不足或无法安全处理 | 保存原因和事项，停止自动推进并等待人工 |

否定、拒绝、转述、引用、举例、反问、重复已回答问题，或仅出现“法律”“解释”“依据”等词语，均不能触发 `EXPLAIN_LAW`。例如“我方维持此前意见，没有法律问题需要解释。”必须返回 `NO_ACTION`，且不能调用检索工具。

最新发言明确提出法律问题时，MiniAgent 才能调用 `intellectual_property_law_search`。检索 query 必须直接对应 `text` 中的问题。没有本次有效检索依据时不能返回 `EXPLAIN_LAW`。

明确法律问题示例：

```json
{
  "state_version": 102,
  "role": "DEFENDANT",
  "text": "图片可以公开下载，为什么不能用于商业宣传？法律依据是什么？",
  "context": "当前争点：涉案图片的商业使用是否构成侵权。"
}
```

## 4. 下一步动作接口

### 4.1 调用条件

| 决策点 | 调用条件 |
| --- | --- |
| `INQUIRY-ENTRY` | 证据阶段结束，进入法官询问阶段 |
| `INQUIRY-EXIT` | 一轮询问和指定当事人回答已完成，且该回答的法律检查已消费 |
| `DEBATE-EXIT` | 当前轮原、被告均已完成发言，且两条发言的法律检查均已消费 |

法律检查完成不等于必须立即请求下一步动作。VirtualCourt 先恢复原发言顺序，只有状态机进入上述决策点时才调用。

### 4.2 请求 `JudgeNextActionRequestV2`

```json
{
  "state_version": 120,
  "phase": "INVESTIGATION",
  "allowed_actions": ["ASK", "COMPLETE", "HANDOFF"],
  "allowed_targets": ["PLAINTIFF", "DEFENDANT"],
  "case_context": {
    "summary": "原告主张被告未经许可将插画用于商业宣传；被告主张图片来自公开素材平台。",
    "claims": ["停止使用涉案图片并赔偿损失。"],
    "defenses": ["图片来自公开素材平台。"],
    "dispute_focuses": ["涉案使用行为是否构成侵权。"]
  },
  "current_issue": null,
  "records": []
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `state_version` | integer | 当前状态版本，服务端原样回填 |
| `phase` | enum | `INVESTIGATION` 或 `DEBATE` |
| `allowed_actions` | string[] | 当前允许的流程动作，无重复项，必须包含 `HANDOFF` |
| `allowed_targets` | string[] | 当前可被 `ASK` 的角色；允许 `ASK` 时必须非空 |
| `case_context` | object | 案情摘要、请求、抗辩、争点，以及辩论所需的调查总结 |
| `current_issue` | object/null | 调查为 `null`；辩论必须是当前争点 |
| `records` | object[] | 按时间从旧到新排列的相关记录 |

| `phase` | 动作全集 |
| --- | --- |
| `INVESTIGATION` | `ASK`、`COMPLETE`、`HANDOFF` |
| `DEBATE` | `CONTINUE`、`COMPLETE`、`HANDOFF` |

`allowed_actions` 必须是对应动作全集的非空子集，不得包含 `EXPLAIN_LAW` 或 `NO_ACTION`。

调查时 `case_context` 包含 `summary`、`claims`、`defenses` 和 `dispute_focuses`，省略 `investigation_summary`。辩论时必须增加非空 `investigation_summary`，并提供：

```json
{
  "id": "FOCUS-02",
  "question": "赔偿金额及维权费用是否合理。"
}
```

`records` 每项固定为：

```json
{
  "type": "SPEECH",
  "role": "DEFENDANT",
  "text": "图片来自某素材平台，没有另行取得授权。"
}
```

`type` 为 `SPEECH` 或 `SUMMARY`；`SPEECH.role` 必须非空，`SUMMARY.role` 必须为 `null`。达到上下文预算时可压缩较早记录，但不得静默截断最新完整问答或当前争点本轮双方发言，也不得把主张改写为已查明事实。

### 4.3 响应 `JudgeNextActionResponseV2`

```json
{
  "state_version": 120,
  "decision": "ASK",
  "target": "DEFENDANT",
  "speech": "被告，请说明下载涉案图片时页面展示的授权范围。",
  "pending_points": ["图片来源及授权范围"]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `state_version` | integer | 从请求原样回填 |
| `decision` | enum | 必须属于请求的 `allowed_actions` |
| `target` | string/null | 仅 `ASK` 必须属于 `allowed_targets`；其他决策为 `null` |
| `speech` | string | 非空，最多 4000 个 Unicode 码点 |
| `pending_points` | string[] | 最多 30 项；`CONTINUE`、`HANDOFF` 至少一项 |

- `ASK`：调查阶段向指定一方提出一个新问题或追问。
- `CONTINUE`：辩论阶段要求双方围绕具体缺失事项再补充一轮。
- `COMPLETE`：当前调查或争点已经充分表达；`speech` 是需要保存和播放的总结，不代表事实成立或意见一致。
- `HANDOFF`：自动流程无法安全继续，需要人工处理。

下一步动作 Agent 不绑定法律检索工具。即使历史记录含法律问题，也不能返回法律解释。

## 5. VirtualCourt 执行时序

### 5.1 发言后检查

```text
发言确认并入库
→ 递增 state_version
→ 保存恢复位置、原发言人和轮次状态
→ 暂缓后续自动播放
→ 调用 /judge/law-check
    NO_ACTION     → 标记版本已检查 → 恢复原流程
    EXPLAIN_LAW   → 保存解释 → 播放一次 → 标记版本已检查 → 恢复原流程
    HANDOFF       → 保存原因 → 停止自动推进 → 等待人工
```

解释播放失败、取消、暂停或人工接管时不得推进。恢复时优先处理已保存但未成功播放的解释，不重新生成。

### 5.2 调查

```text
INQUIRY-ENTRY → /judge/next-action → ASK → 保存并播放问题
→ 开放 target 发言 → 回答完成 → /judge/law-check
→ 检查消费完成 → INQUIRY-EXIT → /judge/next-action
```

`COMPLETE` 时先保存并播放调查总结，成功后由本地程序进入辩论。

### 5.3 辩论

```text
程序选择争点并启动本轮
→ 原告发言完成 → /judge/law-check → 恢复
→ 被告发言完成 → /judge/law-check → 恢复
→ DEBATE-EXIT → /judge/next-action
    CONTINUE → 保存并播放引导语 → 创建下一轮
    COMPLETE → 保存并播放争点总结 → 按本地顺序切换争点
    HANDOFF  → 等待人工
```

单方发言的法律检查不得结束争点、切换争点或新增轮次。法律解释不计入询问或辩论轮次。

## 6. 错误处理

错误响应沿用统一结构：

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "请求不符合 JudgeAPI V2 契约。",
    "retryable": false,
    "details": {}
  }
}
```

| HTTP | `code` | 客户端处理 |
| ---: | --- | --- |
| 401 | `AUTHENTICATION_FAILED` | 检查密钥，不无限重试 |
| 422 | `INVALID_REQUEST` | 保持状态，修复请求构造 |
| 429 | `RATE_LIMITED` | 有界退避，版本变化后丢弃旧请求 |
| 502 | `MODEL_RESPONSE_INVALID` | 保持状态，人工重试或接管 |
| 503 | `SERVICE_UNAVAILABLE` | 有界重试，不重复消费成功结果 |
| 504 | `UPSTREAM_TIMEOUT` | 有界重试或人工接管 |

错误响应不得包含模型原文、密钥、内部提示词、工具私密诊断或堆栈。

## 7. Agent 与工具配置

| Agent | 职责 | 法律检索工具 |
| --- | --- | ---: |
| `virtual_court_law_check_judge` | 判断最新发言、检索并解释法律 | 绑定 |
| `virtual_court_investigation_judge` | 调查流程决策 | 不绑定 |
| `virtual_court_debate_judge` | 辩论流程决策 | 不绑定 |

法律检查 Agent 同时完成判断和解释，不拆成意图判断 Agent 与解释 Agent。普通陈述应直接返回 `NO_ACTION`；只有明确法律问题才调用工具。

## 8. 最低验收要求

法律检查：

- 普通陈述返回 `NO_ACTION`，工具调用 0 次；
- `context` 含法律问题但 `text` 是普通陈述时仍返回 `NO_ACTION`；
- 最新明确法律问题先检索后返回 `EXPLAIN_LAW`；
- 无有效检索依据不能返回 `EXPLAIN_LAW`；
- 同一版本不重复播放；过期、暂停后和人工接管后的响应不执行。

下一步动作：

- 调查只能返回 `ASK`、`COMPLETE`、`HANDOFF`；
- 辩论只能返回 `CONTINUE`、`COMPLETE`、`HANDOFF`；
- 两个流程 Agent 均无法律工具；
- 历史法律内容不能产生 `EXPLAIN_LAW` 或 `NO_ACTION`；
- 单方尚未完成时不能请求辩论下一步动作；
- 轮次和争点顺序仍由 VirtualCourt 控制。

## 9. 已废弃设计

- 统一 `/judge/decide` 端点；
- 通过 `allowed_decisions` 是否包含 `NO_ACTION` 区分用途；
- 推进请求允许 `EXPLAIN_LAW`；
- 法律检查请求携带完整 `records`；
- 调查和辩论 Agent 绑定法律检索工具；
- 发言结束且到达决策点时合并检查与流程决策。

VirtualCourt 必须先消费法律检查结果，再根据本地状态决定是否调用下一步动作接口。
