# Party Reply API V1

接口：`POST /api/v2/integrations/virtual-court/party/reply`。

接口使用内部 Bearer Token 和 UTF-8 严格 JSON。请求只包含 `state_version`、`role`、`question`、`case_context`、`records`；响应只包含 `state_version`、`speech`。

`role` 只允许 `PLAINTIFF`、`DEFENDANT`。`case_context` 和 `records` 与 Judge API `next-action` 的同名结构保持一致。响应版本必须等于请求版本。

VirtualCourt.Server 负责决定是否调用：自动回复时先匹配 `demoScript` 预设回答，匹配成功禁止调用 Party Reply；未匹配才调用。人工模式禁止调用。模式切换、人工抢先回答、步骤或房间轮次变化会使在途结果过期。

Party Reply 只生成贴近案情、逻辑清晰、明确回答当前问题的当事人发言，不随机选择肯定或否定，不决定庭审流程。

统一错误映射：请求错误 422、模型输出无效 502、配置或上游不可用 503、上游超时 504。
