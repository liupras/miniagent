# JudgeAPI V2 双接口协议

当前只提供以下两个接口：

- `POST /api/v2/integrations/virtual-court/judge/law-check`
- `POST /api/v2/integrations/virtual-court/judge/next-action`

旧接口 `POST /api/v2/integrations/virtual-court/judge/decide` 已删除，不提供兼容入口。

两个接口均使用 `X-Integration-Key` 鉴权，接受 UTF-8 JSON。请求体上限为 512 KiB，拒绝未知字段、重复 JSON 字段、非法枚举和超长内容。服务端总超时预算默认为 120 秒。

## 法律检查

法律检查请求只包含 `state_version`、`role`、`text` 和可选 `context`。Agent 只能接收 `latest_speech` 与 `reference_context`，不能接收完整庭审记录。

响应决策仅允许 `NO_ACTION`、`EXPLAIN_LAW`、`HANDOFF`。`EXPLAIN_LAW` 必须具有本次调用产生的有效法律检索证据；检索失败、空结果或工具不可用时返回 `HANDOFF`。只有 `virtual_court_law_check_judge` 绑定 `intellectual_property_law_search`。

## 下一步动作

下一步动作接口只在调查阶段调用。请求包含允许动作、允许目标、案件上下文和相关记录，不再携带 `phase`。

- 调查阶段仅允许 `ASK`、`COMPLETE`、`HANDOFF`。
- 不允许 `NO_ACTION` 或 `EXPLAIN_LAW`。
- `ASK.target` 必须属于请求的 `allowed_targets`，其他动作的 `target` 必须为 `null`。

该接口固定使用 `virtual_court_investigation_judge`，且不绑定法律检索工具。

## 响应与错误

`state_version` 不进入模型上下文，由服务端从请求原样注入响应。每次执行不复用此前模型上下文、输出修复记录或检索证据。

错误使用统一 `IntegrationErrorResponse`：请求契约错误为 422，模型输出无效为 502，配置或上游不可用为 503，上游超时为 504。日志和审计记录使用不同的 `LawCheckV2`、`NextActionV2` 或路由名称区分调用，且不记录请求正文、模型原文、工具私密诊断、密钥或系统提示词。

冻结 Schema 和样例位于 `app/test/fixtures/judge_v2_split_endpoints/`。
