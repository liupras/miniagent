# TranscriptAPI V2 集成测试与灰度接入

本说明用于 `/api/v2/integrations/virtual-court/transcript/generate` 的部署验收和灰度放量，不修改已冻结的 V2 请求、响应协议。

## 1. 灰度边界

应用内不设置布尔功能开关。当前协议只有一个 VirtualCourt 调用方和一套集成密钥，服务内开关只能全开或全关，不能表达有效的灰度人群，并会增加部署配置状态。

灰度由部署和接入层负责：

- 先将新版本部署到独立实例池，由网关仅把获准的测试流量路由至该实例池；
- 若网关支持调用方身份或固定请求来源白名单，使用这些可信属性选择灰度流量；
- 不使用客户端自行提供的请求头决定灰度资格；
- 未进入灰度的生产流量继续访问旧实例池；出现异常时摘除新实例池即可回退。

## 2. 上线前验证

在代码根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest app/test/test_transcript_v2_fixture_contract.py `
  app/test/test_transcript_v2_models.py `
  app/test/test_transcript_validator.py `
  app/test/test_transcript_service.py `
  app/test/test_virtual_court_transcript_seed.py `
  app/test/test_virtual_court_transcript_api.py `
  app/test/test_transcript_execution.py -q
```

测试覆盖冻结样例、严格 JSON、模型输出校验、真实 `AgentRunner/AgentLLM` 边界、禁止工具、一次纠错、完整上下文不截断、状态版本可信注入和请求隔离。测试使用确定性假模型，不产生外部模型费用。

部署环境还需核对：

1. SQLite 中 `virtual_court_transcript_writer` 存在、启用且无工具绑定。
2. 该 Agent 对应的 LLM 可用，输出上限符合部署配置。
3. `VIRTUAL_COURT_API_KEY` 已配置，日志中不打印密钥、庭审正文或模型原文。
4. 网关已配置灰度实例池、可信流量选择条件和快速摘流方案。

## 3. 灰度顺序

1. 先在测试环境开启，使用 `SPEECH`、`SUMMARY`、空记录、长输入和提示注入样例验收。
2. 将新版本部署到独立灰度实例池，确认 JudgeAPI 回归正常，生产流量仍访问旧实例池。
3. 只允许内部测试调用方进入灰度实例池；先观察错误率、P95/P99 延迟、超时率、纠错率和输出长度。
4. 按调用方或可信流量比例逐批扩大灰度实例池流量。每批至少覆盖一个完整业务观察窗口，再决定下一批。
5. 全量稳定后把生产流量切换到新版本实例池。

## 4. 验收与回退

业务验收需人工抽检笔录是否保持记录顺序、是否把 `SUMMARY` 标成摘要、是否出现输入之外的事实，以及旧 `state_version` 响应是否被 VirtualCourt 丢弃。

出现以下任一情况应停止放量：持续 5xx/超时上升、模型无效响应或纠错率异常、疑似素材截断、顺序错乱、摘要伪造成逐字发言、敏感正文进入日志。

回退时由网关摘除灰度实例池，并把流量恢复到旧版本实例池。该操作不需要修改应用配置、冻结协议或数据库数据。
