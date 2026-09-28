# VirtualCourt 发言整理接口协议 V3

## 1. 职责边界

`POST /api/v3/integrations/virtual-court/transcript/generate` 不再让 AI 生成整份庭审笔录。

- VirtualCourt 负责案件基本信息、到庭人员、发言人、阶段、步骤、顺序、章节和最终文本渲染。
- MiniAgent 只整理每条已提交发言的 `text`。
- AI 不接收 `case_info` 和 `participants`；它只接收从请求提取的 `sequence + text`。
- 返回记录必须与请求逐条、同序对应，不能增加、遗漏、合并、拆分或改写 `sequence`。

## 2. 请求

顶层字段为 `state_version`、`case_info`、`participants`、`records`。

`case_info` 沿用 VirtualCourt 的 `CourtCaseInfo` 命名：

- `case_id`
- `case_number`
- `court_name`
- `procedure`
- `cause_of_action`
- `subject_matter`
- `is_simulated`
- `legal_effect_disclaimer`

`participants` 沿用 `CourtParticipant` 命名：

- `participant_id`
- `role`
- `display_name`
- `description`

`records` 沿用 `TrialSpeechRecord` 命名：

- `sequence`：严格递增的正整数；
- `step_id`：VirtualCourt 步骤 ID；
- `phase`：VirtualCourt 庭审阶段稳定值；
- `role`：`judge`、`clerk`、`plaintiff`、`defendant` 或 `system`；
- `text`：非空，最多 8000 个 Unicode 码点；
- `is_intervention`：是否为临时插问。

请求最多 512 条记录，全部字符串内容总量最多 64000 个 Unicode 码点，请求体最多 512 KiB。不得以摘要替换最终笔录所需的原始发言。

## 3. 响应

成功响应只包含：

```json
{
  "state_version": 42,
  "records": [
    {"sequence": 1, "text": "现在开庭。"}
  ]
}
```

服务端从请求注入可信 `state_version`。每项只包含 `sequence` 和整理后的 `text`。响应记录的数量、编号和顺序必须与请求完全一致。

## 4. AI 整理规则

AI 只可整理标点、明显语气词、口吃和不改变原意的口语重复。不得生成固定笔录信息，不得改变发言人、阶段、顺序或事实含义，不得新增主张、证据、法律依据或结论。

固定案件信息和人员信息由接口严格校验，但在调用 Agent 前剔除。模型输入只包含：

```json
{
  "records": [
    {"sequence": 1, "text": "现在，嗯，开庭。"}
  ]
}
```

## 5. 输出校验与错误

Agent 最终只能输出 `records`。MiniAgent 校验 JSON 结构、文本长度以及 sequence 的完整性和顺序，第一次失败时在同一总超时内纠正一次。仍失败则返回 `MODEL_RESPONSE_INVALID`。

鉴权、限流、超时、状态版本、日志脱敏和错误响应属于 V3 集成边界。
