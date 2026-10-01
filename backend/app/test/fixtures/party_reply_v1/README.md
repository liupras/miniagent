# Party Reply API V1 冻结契约

修订标识：`2026-10-01-party-reply-v1`。

本目录冻结 `POST /api/v2/integrations/virtual-court/party/reply` 的协议和行为边界。

- `protocol-frozen.md`：协议快照。
- `schemas/`：Draft 2020-12 请求、响应 Schema。
- `manifest.json` 与 `cases/`：合法和非法样例。
- `contexts/`：响应版本绑定所使用的请求。
- `behavior-scenarios.json`：预设优先及模式切换要求。
- `limits.json`：字节、码点、超时及修复边界。
- `integrity.json`：冻结文件的 SHA-256 清单。
- `verify_fixtures.py`：离线验证器。

验证：

```powershell
python verify_fixtures.py
```

## 运行配置

MiniAgent 启动时会执行 SQLite 的幂等种子流程，确保名为
`virtual_court_party_responder` 的 Agent 存在。已有数据库缺少该记录时会自动补种；
已有同名记录会保留模型选择并刷新由代码管理的系统提示词，不需要手工修改 SQLite。

接口读取以下环境配置：

- `VIRTUAL_COURT_INTERNAL_SERVICE_TOKEN`：与 VirtualCourt.Server 相同的内部 Bearer Token；
- `VIRTUAL_COURT_PARTY_REPLY_TIMEOUT_SECONDS`：单次 Agent 调用超时，默认 120 秒，允许范围 0 到 600 秒（不含 0）。

启动后先检查 `GET /health`，再由 VirtualCourt.Server 调用本接口。Unity 客户端不得直连。

## 专项测试

在 `D:\miniagent\backend` 中运行：

```powershell
pytest app/test/test_party_reply_v1_fixture_contract.py `
       app/test/test_party_reply_service.py `
       app/test/test_virtual_court_party_reply_api.py `
       app/test/test_virtual_court_party_reply_seed.py
```

这些测试分别覆盖冻结字段和样例、Agent 调用与输出校验、HTTP 鉴权/错误映射、
以及已有和全新 SQLite 数据库的启动补种行为。
