# 民事案件草稿生成 API V1

`POST /api/v2/integrations/virtual-court/cases/civil/draft/generate`

只供 VirtualCourt.Server 使用，沿用 VirtualCourt 集成接口的内部 Bearer Token。请求体为 UTF-8 JSON：`plaintiffComplaint`、`defendantAnswer` 是已解析的正文；`otherMaterials` 为零到多份 `{name, text}`。MiniAgent 不接收上传原件、案件 ID、材料数据库 ID 或流程标识。请求与响应的准确字段见 `CivilCaseDraftGenerateRequestV1`、`CivilCaseDraftGenerateResponseV1`。

响应仅有 `draft`（待审阅的民事语义草稿）和 `issues`（`blocking`/`warning` 缺失或矛盾提示）。服务端校验结构和金额分项合计；材料与草稿的对应关系由审核者结合上传文件审阅。生成结果不含系统 ID、法官固定台词或动态问答，也不能直接发布或开庭。VirtualCourt 后续负责草稿编译、人工审阅、批准和发布。

Agent 名称为 `virtual_court_civil_draft_generator`，随 MiniAgent 的既有数据库种子流程幂等补种；已选模型保留，系统提示词随代码更新。该 Agent 不绑定工具。默认单次请求超时 300 秒，可用 `VIRTUAL_COURT_CIVIL_DRAFT_TIMEOUT_SECONDS` 配置。模型输出最多修复一次；仍无效时返回 `MODEL_RESPONSE_INVALID`，不返回未经校验的文本。

请求错误返回 `INVALID_REQUEST`（422），无效模型结果为 `MODEL_RESPONSE_INVALID`（502），上游不可用或 Agent 配置错误为 `SERVICE_UNAVAILABLE`（503），超时为 `UPSTREAM_TIMEOUT`（504）。已有集成鉴权规则不变。日志只记录材料数量、长度和结果计数，不记录上传正文、证据摘录或生成内容。

测试：

```powershell
cd D:\miniagent\backend
.\.venv\Scripts\python.exe -m pytest -q app/test/test_civil_case_draft_v1_contract.py app/test/test_virtual_court_civil_draft_api.py
```

本阶段没有接通 VirtualCourt 管理端；四份演示材料的完整 AI 生成质量仍需在配置真实模型后按 `D:\project\VirtualCourt\Tests\Fixtures\CivilCaseGeneration\acceptance-v1.json` 人工验收。
