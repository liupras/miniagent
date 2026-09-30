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
