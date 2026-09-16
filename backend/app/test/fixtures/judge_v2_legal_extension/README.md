# JudgeAPI V2 法律解释扩展：冻结契约 M0-E

修订标识：`2026-09-12-legal-extension`。本目录是下一阶段实现的共享契约源；原 `Tests/Fixtures/JudgeV2/` 继续用于当前契约校验。

## 内容与范围

- `protocol-frozen.md`：生成本次契约时的协议文本快照。
- `manifest.json`：102 个静态用例及预期接受/拒绝结果，包含原 55 个场景和 47 个扩展场景；原场景的推进请求按新协议授权 EXPLAIN_LAW。
- `schemas/`：请求、模型输出和 HTTP 响应的 Draft 2020-12 Schema。
- `limits.json`：原始字节、累计内容、超时与纠错边界。
- `behavior-scenarios.json`：14 个待实施的工具和流程验收场景。它们不是已通过的自动化测试。
- `integrity.json`：本目录文件 SHA-256 冻结清单。
- `verify_fixtures.py`：离线 Schema、请求权限、版本及完整性校验。
- `probe_current_backend.py`：只读观察当前后端与新契约的差距，不调用模型、不修改数据库。

请求仍为七字段，HTTP 响应仍为五字段；不增加 `legal_question`，法律问题在 `records` 中。模型输出仍不含 `state_version`。

## 新约束

| 项目 | 冻结要求 |
| --- | --- |
| 调查决策全集 | ASK、COMPLETE、HANDOFF、EXPLAIN_LAW、NO_ACTION |
| 辩论决策全集 | CONTINUE、COMPLETE、HANDOFF、EXPLAIN_LAW、NO_ACTION |
| allowed_decisions | 最多 5 项，无重复且包含 HANDOFF；具体调用还受下列规则限制 |
| 包含 NO_ACTION | 必须恰为 EXPLAIN_LAW、NO_ACTION、HANDOFF 的集合，顺序不限 |
| 普通推进调用 | 不允许 NO_ACTION；按需允许 EXPLAIN_LAW |
| NO_ACTION | target=null、speech=""、pending_points=[]，不播放 |
| EXPLAIN_LAW | target=null，speech 非空，pending_points 可空；必须先检索再依据结果解释 |
| 其他决策 | speech 非空；CONTINUE/HANDOFF 至少一条 pending_points |

数组上限 5 不代表全部五种阶段决策可以同时授权：五项全集含 NO_ACTION，会违反检查集合规则，必须拒绝。本次包含这种边界反例。

未变的边界：请求 512 KiB、响应 128 KiB、累计内容 64000 码点、records 最多 512 条、speech 最多 4000 码点；详细嵌套字段边界见 Schema。长度使用 Unicode 码点，非 UTF-16 单元。只有 NO_ACTION 的空字符串是发言例外，空白字符串仍非法。

服务端总预算 120 秒，包含法律检索、生成和最多一次输出纠错；客户端计划 135 秒。实际模型上下文预算还需计入工具描述、工具调用和返回结果、系统提示及输出预留。不能通过统一拒绝工具或静默截断庭审记录来满足预算。

## 验证与复用

在 VirtualCourt 根目录执行：

```powershell
D:/miniagent/backend/.venv/Scripts/python.exe -B Tests/Fixtures/JudgeV2LegalExtension/verify_fixtures.py
```

后端 M1-E 和客户端 M2 应消费同一 manifest；迁移时核对冻结文件哈希，不按各自实现重新生成期望结果。本次仅冻结在共享工作区，不替换后端仍用于初版 M1 回归的旧样例。

普通验证不会重新生成文件。仅在批准修改契约时运行 `build_fixtures.py`；它读取本目录协议快照，避免当前文档继续修订导致旧冻结结果漂移。更新后需要显式维护完整性清单。

检索样例的“测试条文 A”是明确的虚构测试资料，用于后续验证输出是否依据工具返回，不是可播放到真实庭审的法律依据。静态样例接受 EXPLAIN_LAW 不能证明 Agent 真正调用过检索；实际调用轨迹、失败处理及播放恢复由 `behavior-scenarios.json` 定义，留待实现后验证。

`markdown-fence`、`duplicate-key` 是故意非法的 JSON 文本；字节边界文件带合法尾部空白。不能先重新序列化这些文件再测试原始请求大小。

## 基线说明

本次现有后端 161 项、Unity 191 项测试通过，只代表扩展前状态。5 个新契约合法输入的只读探测均被现有后端拒绝；当前还存在拒绝配置工具的检查，流程 Judge 的种子和数据库工具绑定均为空。

详情见 `Docs/judge_protocol_v2_legal_baseline.md`。工具恢复、业务代码修改、真实模型和 Unity 法律解释联调均未在 M0-E 执行。
