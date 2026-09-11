# JudgeAPI V2 法律解释扩展（2026-09-12）

仅提供 POST `/api/v2/integrations/virtual-court/judge/decide`；不保留 V1。
鉴权 `X-Integration-Key`。请求七字段、HTTP 响应五字段、模型最终输出四字段，版本由服务回填。

共享冻结样例：`app/test/fixtures/judge_v2_legal_extension/manifest.json`，102 个契约用例；同目录 integrity.json 校验冻结文件。初版样例保留为历史证据。
完整协议源：VirtualCourt `Docs/judge_protocol_v2.md`。

调查决策：ASK、COMPLETE、HANDOFF、EXPLAIN_LAW、NO_ACTION；辩论将 ASK 替换为 CONTINUE。
包含 NO_ACTION 的 allowed_decisions 必须恰为 EXPLAIN_LAW、NO_ACTION、HANDOFF，不能混入推进决策。
NO_ACTION 必须 target=null、speech=""、pending_points=[]；其他 speech 非空。法律问题由 records 提供，不新增 legal_question。

EXPLAIN_LAW 先调用 intellectual_property_law_search，再依据结果解释。无本次有效检索的解释、检索异常或空资料转为 HTTP 200 HANDOFF。是否有待回答问题、资料是否相关和足够，由阶段 Agent 推理；不能用静态结构校验代替真实模型验收。
Judge 复用 AgentFactory → AgentRunner.execute → ToolReActAgent，通过 agent_tool_relations 和 tools 中的 smart_router 配置加载检索工具。execute(preserve_context=True) 不加载隐式会话记忆、不截断上下文，返回最终文本及本次工具轨迹；原 invoke() 保持文本返回和原有会话行为。JudgeService 使用 law_policy 检查检索轨迹，不在通用运行时处理 Judge 决策；工具观察回调在失败或空法律资料时中止执行并转 HANDOFF。没有 Judge 专用工具循环。工具描述、调用、返回结果计入每次模型调用前的预算；超限返回 422，不截断记录。

请求上限 512 KiB、累计内容 64000 码点，响应上限 128 KiB，不接受重复 JSON 字段。
默认服务端总预算 120 秒，涵盖 Agent 加载、检索、生成、预算检查及最多一次格式纠错；客户端计划 135 秒。错误沿用统一 error 外壳。

## 升级

两个名称仍为 virtual_court_investigation_judge、virtual_court_debate_judge。
提示词不包含版本标记，运行时不检查文本版本。正常初始化保留已有提示词、ID、启用状态、模型及参数，幂等恢复缺失法律检索绑定，不删除其他绑定。
重复初始化保留已有扩展提示词的人工微调。定向升级：`python -B scripts/upgrade_judge_v2.py`，显式同步两个 Agent 的种子提示词，事务内检查提示词内容及工具绑定；缺失工具则回滚。
升级后重启服务清除缓存。运行时不再拒绝没有版本标记的提示词；数据库更新后仍需重启服务加载缓存。

自动化测试包括 test_judge_legal_execution 以及协议、响应、Service、API、种子和迁移回归。检索执行测试使用确定性的模型和工具边界，真实模型、实际知识库质量及 Unity 播放恢复在后续联调验收。

## 提示词维护

输出格式、字段限制和阶段规则统一维护在两个 Agent 的系统提示词中。JudgeService._build_agent_query 仅序列化本次请求数据（按协议不向模型传入 state_version），不再附加输出 Schema 或固定输出指令；一次纠错仅追加校验诊断。种子和本地 SQLite 提示词已同步，服务重启后加载。普通初始化保留已有人工微调，不应以 force 全量覆盖模型参数。
