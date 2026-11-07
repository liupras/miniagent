# 民事案件草稿生成 API

`POST /api/v2/integrations/virtual-court/cases/civil/draft/generate`

只供 VirtualCourt.Server 使用，采用内部 Bearer Token。本次直接更新现有 civil 接口，不保留逐证据组正文的旧契约。请求体为 UTF-8 JSON，包含 `documents` 和 `procedure`。`documents` 是 1～22 份 `{name, text}`；`procedure` 按阶段、步骤、环节列出需要生成的案件专属固定正文。步骤 `type` 只能是 `sequence`；环节 `contentSource` 只能是 `case`，`speakerRole` 只能是 `judge`、`plaintiff` 或 `defendant`。不接收 `evidenceGroupLoop`、`caseEvidence` 或调查控制环节。

响应仅含 `draft` 和 `issues`。draft 包含双方身份与立场、诉请、争议焦点、证据组、每份证据材料的来源和可读摘录，以及与 procedure 逐项对应的 `segmentContents`。证据组是后续统一调查使用的案件材料，不生成固定的举证、质证、回应、法官问题或 `demoScript`。材料不足仍须返回全部固定正文要求；无法安全生成的正文可为空，但必须附 `blocking` 问题。生成结果只供人工审阅，不能直接发布或开庭。

Agent 名称为 `virtual_court_civil_draft_generator`，随 MiniAgent 的既有数据库种子流程幂等补种；已选模型保留，系统提示词随代码更新。该 Agent 不绑定工具。默认单次请求超时 300 秒，可用 `VIRTUAL_COURT_CIVIL_DRAFT_TIMEOUT_SECONDS` 配置。模型输出最多修复一次；仍无效时返回 `MODEL_RESPONSE_INVALID`，不返回未经校验的文本。

请求错误返回 `INVALID_REQUEST`（422），无效模型结果为 `MODEL_RESPONSE_INVALID`（502），上游不可用或 Agent 配置错误为 `SERVICE_UNAVAILABLE`（503），超时为 `UPSTREAM_TIMEOUT`（504）。已有集成鉴权规则不变。日志只记录材料数量、长度和结果计数，不记录上传正文、证据摘录或生成内容。

测试：

```powershell
cd D:\miniagent\backend
.\.venv\Scripts\python.exe -m pytest -q app/test/test_civil_case_draft_v1_contract.py app/test/test_virtual_court_civil_draft_api.py
```

双方共享的请求和响应样例见 `app/test/fixtures/civil_draft_v2/contract.json` 与 VirtualCourt 的 `Tests/Fixtures/CivilCaseGeneration/contract-v2.json`。四份演示材料的完整 AI 生成质量仍需在配置真实模型后按 `D:\project\VirtualCourt\Tests\Fixtures\CivilCaseGeneration\acceptance-v1.json` 人工验收。
