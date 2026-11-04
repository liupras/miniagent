# TranscriptAPI V3 配置名称接口验收

`POST /api/v3/integrations/virtual-court/transcript/generate` 使用当前唯一协议：记录携带 `stage_name`、`step_name`、`segment_name`。系统尚未发布，不保留旧实例池、旧字段或版本兼容通道。

## 启动前检查

1. VirtualCourt 与 MiniAgent 同步使用名称字段；`phase` 和 `step_id` 请求返回 422。
2. SQLite 中 `virtual_court_transcript_writer` 存在、启用且无工具绑定。启动时种子流程将其提示词同步为 `agent.json` 中的当前内容。
3. Agent 对应模型可用；`VIRTUAL_COURT_INTERNAL_SERVICE_TOKEN` 与 VirtualCourt 一致。
4. 修改代码或 SQLite 提示词后重启 MiniAgent，重新建立缓存的 AgentRunner。

## 自动化验证

在 MiniAgent backend 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest app/test/test_transcript_v3_fixture_contract.py `
  app/test/test_transcript_v3_models.py `
  app/test/test_transcript_validator.py `
  app/test/test_transcript_service.py `
  app/test/test_virtual_court_transcript_seed.py `
  app/test/test_virtual_court_transcript_api.py `
  app/test/test_transcript_execution.py -q
```

覆盖名称字段必填、空白及长度限制、自定义阶段名称、不同步骤同名环节、拒绝旧字段、严格 JSON、一次纠错、完整输入不截断、sequence 同序对应及状态版本可信回填。使用确定性模型，不调用外部模型。

## 两端联调

VirtualCourt 的 `Tests/Integration/Test-MiniAgentRuntime.ps1` 调用真实法官、原告、被告和笔录接口。笔录请求根据样板配置关联阶段、步骤、环节名称。

完整庭审请求可由 `Tests/TranscriptServer` 使用 `--request-output <文件>` 导出。将该请求发送至 MiniAgent 后，使用 `--response-input <响应文件>` 交回 VirtualCourt 校验并渲染。章节标题及所属步骤始终来自原始请求，AI 只接收并整理 `sequence + text`，不得增减或调整记录顺序。
