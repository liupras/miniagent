# 通用案件草案生成 API V1

接口：`POST /api/v1/integrations/virtual-court/case-drafts/generate`，仅供 VirtualCourt.Server 使用，以内部 Bearer Token 鉴权。

请求包含 `draftContract`、`documents`、`context`。`draftContract` 含 `contractId`、Draft 2020-12 的 `draftSchema` 和 `instructions`。材料含稳定 `sourceId`、`name`、`text`。MiniAgent 根据契约和可信上下文生成 `draft + issues`，并以传入的 `draftSchema` 校验 `draft`。本接口没有案件类型专属的字段模型或角色假设。

格式、大小和 Schema 边界以 VirtualCourt 的 `Docs/案件草案生成契约V1.md` 为准。请求最多 1 MiB，响应最多 512 KiB；仅允许本地 `$defs` 引用，拒绝远程、动态及循环引用。请求无效返回 `INVALID_REQUEST`（422），模型输出经一次修复仍无效返回 `MODEL_RESPONSE_INVALID`（502），服务不可用返回 `SERVICE_UNAVAILABLE`（503），超时返回 `UPSTREAM_TIMEOUT`（504）。

通用 Agent 名称为 `virtual_court_case_draft_generator`，无工具绑定；默认超时 300 秒，可用 `VIRTUAL_COURT_CASE_DRAFT_TIMEOUT_SECONDS` 配置。案件材料及文件名不可信，不能覆盖契约或上下文。日志只记录契约标识、材料数量、长度和问题数量，不记录材料或草案正文。

共享样例：`app/test/fixtures/case_draft_v1/civil-contract-v1.json`，与 VirtualCourt 的 `Tests/Fixtures/CaseDraftGeneration/civil-contract-v1.json` 逐字节相同。

```powershell
cd D:\miniagent\backend
.\.venv\Scripts\python.exe -m pytest -q app/test/test_case_draft_contract.py app/test/test_virtual_court_case_draft_api.py
```
