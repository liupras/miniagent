"""Build the frozen split-endpoint JudgeAPI V2 contract fixtures.

This generator is an offline contract tool. It does not call either application,
an LLM, or a law-retrieval service.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


REVISION = "2026-09-13-split-endpoints"
LAW_PATH = "/api/v2/integrations/virtual-court/judge/law-check"
ACTION_PATH = "/api/v2/integrations/virtual-court/judge/next-action"
ROOT = Path(__file__).resolve().parent


def save(path: str, value) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def string(maximum: int, minimum: int = 1):
    schema = {"type": "string", "minLength": minimum, "maxLength": maximum}
    if minimum:
        schema["pattern"] = r"\S"
    return schema


def array(item, maximum: int, minimum: int = 0):
    return {
        "type": "array",
        "items": item,
        "minItems": minimum,
        "maxItems": maximum,
    }


def obj(properties, required=None):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties) if required is None else required,
    }


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


VERSION = {"type": "integer", "minimum": 0, "maximum": 9223372036854775807}
ROLE = string(64)
PARTY_ROLE = {"enum": ["PLAINTIFF", "DEFENDANT"]}
POINTS = array(string(1000), 30)

LAW_REQUEST = obj(
    {
        "state_version": VERSION,
        "role": PARTY_ROLE,
        "text": string(8000),
        "context": string(16000, 0),
    },
    ["state_version", "role", "text"],
)

LAW_RESPONSE = obj(
    {
        "state_version": VERSION,
        "decision": {"enum": ["NO_ACTION", "EXPLAIN_LAW", "HANDOFF"]},
        "speech": string(4000, 0),
        "pending_points": POINTS,
    }
)
LAW_RESPONSE["allOf"] = [
    {
        "if": {"properties": {"decision": {"const": "NO_ACTION"}}},
        "then": {
            "properties": {
                "speech": {"const": ""},
                "pending_points": {"maxItems": 0},
            }
        },
        "else": {"properties": {"speech": string(4000)}},
    },
    {
        "if": {"properties": {"decision": {"const": "HANDOFF"}}},
        "then": {"properties": {"pending_points": {"minItems": 1}}},
    },
]

CASE_CONTEXT = obj(
    {
        "summary": string(16000),
        "claims": array(string(4000), 30),
        "defenses": array(string(4000), 30),
        "dispute_focuses": array(string(1000), 20),
        "investigation_summary": string(16000),
    },
    ["summary", "claims", "defenses", "dispute_focuses"],
)
ISSUE = obj({"id": string(64), "question": string(1000)})
RECORD = obj(
    {
        "type": {"enum": ["SPEECH", "SUMMARY"]},
        "role": nullable(ROLE),
        "text": string(16000),
    }
)
RECORD["allOf"] = [
    {
        "if": {"properties": {"type": {"const": "SPEECH"}}},
        "then": {"properties": {"role": ROLE, "text": string(8000)}},
        "else": {"properties": {"role": {"type": "null"}}},
    }
]
ALLOWED_ACTIONS = {
    **array({"enum": ["ASK", "CONTINUE", "COMPLETE", "HANDOFF"]}, 3, 1),
    "uniqueItems": True,
    "contains": {"const": "HANDOFF"},
}
NEXT_REQUEST = obj(
    {
        "state_version": VERSION,
        "phase": {"enum": ["INVESTIGATION", "DEBATE"]},
        "allowed_actions": ALLOWED_ACTIONS,
        "allowed_targets": {**array(ROLE, 32), "uniqueItems": True},
        "case_context": CASE_CONTEXT,
        "current_issue": nullable(ISSUE),
        "records": array(RECORD, 512),
    }
)
NEXT_REQUEST["allOf"] = [
    {
        "if": {"properties": {"phase": {"const": "INVESTIGATION"}}},
        "then": {
            "properties": {
                "allowed_actions": {
                    "items": {"enum": ["ASK", "COMPLETE", "HANDOFF"]}
                },
                "current_issue": {"type": "null"},
                "case_context": {"not": {"required": ["investigation_summary"]}},
            }
        },
        "else": {
            "properties": {
                "allowed_actions": {
                    "items": {"enum": ["CONTINUE", "COMPLETE", "HANDOFF"]}
                },
                "current_issue": {"type": "object"},
                "case_context": {"required": ["investigation_summary"]},
            }
        },
    },
    {
        "if": {
            "properties": {
                "allowed_actions": {"contains": {"const": "ASK"}}
            }
        },
        "then": {"properties": {"allowed_targets": {"minItems": 1}}},
    },
]

NEXT_RESPONSE = obj(
    {
        "state_version": VERSION,
        "decision": {"enum": ["ASK", "CONTINUE", "COMPLETE", "HANDOFF"]},
        "target": nullable(ROLE),
        "speech": string(4000),
        "pending_points": POINTS,
    }
)
NEXT_RESPONSE["allOf"] = [
    {
        "if": {"properties": {"decision": {"const": "ASK"}}},
        "then": {"properties": {"target": ROLE}},
        "else": {"properties": {"target": {"type": "null"}}},
    },
    {
        "if": {
            "properties": {
                "decision": {"enum": ["CONTINUE", "HANDOFF"]}
            }
        },
        "then": {"properties": {"pending_points": {"minItems": 1}}},
    },
]


def write_schemas() -> None:
    schemas = {
        "law-check-request": LAW_REQUEST,
        "law-check-response": LAW_RESPONSE,
        "next-action-request": NEXT_REQUEST,
        "next-action-response": NEXT_RESPONSE,
    }
    for name, schema in schemas.items():
        schema = copy.deepcopy(schema)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:virtual-court:judge-v2:{name}:{REVISION}"
        schema["title"] = "JudgeV2-" + name
        save(f"schemas/{name}.schema.json", schema)


BASE_CONTEXT = {
    "summary": "原告主张被告未经许可将其插画用于商业宣传；被告主张图片来自公开素材平台。",
    "claims": ["停止使用涉案图片并赔偿经济损失及维权支出。"],
    "defenses": ["图片来自公开素材平台，未另行取得授权。"],
    "dispute_focuses": ["涉案使用行为是否构成侵权。", "赔偿金额及维权费用是否合理。"],
}
INVESTIGATION_REQUEST = {
    "state_version": 120,
    "phase": "INVESTIGATION",
    "allowed_actions": ["ASK", "COMPLETE", "HANDOFF"],
    "allowed_targets": ["PLAINTIFF", "DEFENDANT"],
    "case_context": BASE_CONTEXT,
    "current_issue": None,
    "records": [
        {"type": "SPEECH", "role": "JUDGE", "text": "被告，请说明图片来源和授权范围。"},
        {"type": "SPEECH", "role": "DEFENDANT", "text": "图片来自公开素材平台，没有另行取得授权。"},
    ],
}
DEBATE_REQUEST = {
    "state_version": 220,
    "phase": "DEBATE",
    "allowed_actions": ["CONTINUE", "COMPLETE", "HANDOFF"],
    "allowed_targets": ["PLAINTIFF", "DEFENDANT"],
    "case_context": {
        **BASE_CONTEXT,
        "investigation_summary": "双方已说明作品来源、使用方式和授权主张，对责任与赔偿仍有分歧。",
    },
    "current_issue": {"id": "FOCUS-02", "question": "赔偿金额及维权费用是否合理。"},
    "records": [
        {"type": "SPEECH", "role": "PLAINTIFF", "text": "律师费属于为本案支出的合理维权费用。"},
        {"type": "SPEECH", "role": "DEFENDANT", "text": "我方对费用的关联性和必要性有异议。"},
    ],
}
LAW_ORDINARY = {
    "state_version": 101,
    "role": "PLAINTIFF",
    "text": "我方维持此前意见，没有法律问题需要解释。",
    "context": "当前争点：赔偿金额及维权费用是否合理。",
}
LAW_EXPLICIT = {
    "state_version": 102,
    "role": "DEFENDANT",
    "text": "图片可以公开下载，为什么不能用于商业宣传？法律依据是什么？",
    "context": "当前争点：涉案图片的商业使用是否构成侵权。",
}


CASES = []


def case(name, endpoint, kind, data, valid=True, request=None, reason=None):
    path = f"cases/{name}.json"
    save(path, data)
    item = {
        "id": name,
        "endpoint": endpoint,
        "kind": kind,
        "schema": f"{endpoint}-{kind}",
        "file": path,
        "valid": valid,
    }
    if request is not None:
        request_path = f"contexts/{name}.request.json"
        save(request_path, request)
        item["request"] = request_path
    if reason:
        item["reason"] = reason
    CASES.append(item)


def changed(data, key, value):
    result = copy.deepcopy(data)
    result[key] = value
    return result


def raw_case(name, endpoint, kind, text, valid, reason):
    path = ROOT / f"cases/{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    CASES.append(
        {
            "id": name,
            "endpoint": endpoint,
            "kind": kind,
            "schema": f"{endpoint}-{kind}",
            "file": f"cases/{name}.json",
            "valid": valid,
            "reason": reason,
        }
    )


def write_cases() -> None:
    case("law-ordinary-request", "law-check", "request", LAW_ORDINARY)
    case("law-explicit-request", "law-check", "request", LAW_EXPLICIT)
    case("law-context-omitted", "law-check", "request", {k: v for k, v in LAW_ORDINARY.items() if k != "context"})
    case("law-context-empty", "law-check", "request", changed(LAW_ORDINARY, "context", ""))
    case("law-state-version-max", "law-check", "request", changed(LAW_ORDINARY, "state_version", 9223372036854775807))
    case("law-text-unicode-max", "law-check", "request", changed(LAW_ORDINARY, "text", "问" * 8000))
    case("law-invalid-role", "law-check", "request", changed(LAW_ORDINARY, "role", "JUDGE"), False, reason="schema")
    case("law-text-blank", "law-check", "request", changed(LAW_ORDINARY, "text", "   "), False, reason="schema")
    case("law-text-over-max", "law-check", "request", changed(LAW_ORDINARY, "text", "问" * 8001), False, reason="schema")
    case("law-context-over-max", "law-check", "request", changed(LAW_ORDINARY, "context", "述" * 16001), False, reason="schema")
    case("law-version-negative", "law-check", "request", changed(LAW_ORDINARY, "state_version", -1), False, reason="schema")
    case("law-version-boolean", "law-check", "request", changed(LAW_ORDINARY, "state_version", True), False, reason="schema")
    case("law-version-string", "law-check", "request", changed(LAW_ORDINARY, "state_version", "101"), False, reason="schema")
    case("law-version-over-max", "law-check", "request", changed(LAW_ORDINARY, "state_version", 9223372036854775808), False, reason="schema")
    for field, value in (
        ("phase", "INVESTIGATION"),
        ("records", []),
        ("allowed_decisions", ["NO_ACTION"]),
        ("allowed_targets", ["PLAINTIFF"]),
        ("speech_id", "speech-1"),
    ):
        case(f"law-forbidden-{field.replace('_', '-')}", "law-check", "request", {**LAW_ORDINARY, field: value}, False, reason="schema")

    encoded = json.dumps(LAW_ORDINARY, ensure_ascii=False)
    raw_case("law-duplicate-key", "law-check", "request", encoded[:-1] + ',"state_version":101}', False, "invalid_json")
    raw_case("law-markdown-fence", "law-check", "request", "```json\n" + encoded + "\n```", False, "invalid_json")
    raw_case("law-body-max", "law-check", "request", encoded + " " * (524288 - len(encoded.encode("utf-8"))), True, "")
    raw_case("law-body-over-max", "law-check", "request", encoded + " " * (524289 - len(encoded.encode("utf-8"))), False, "body_size")

    no_action = {"state_version": 101, "decision": "NO_ACTION", "speech": "", "pending_points": []}
    explain = {"state_version": 102, "decision": "EXPLAIN_LAW", "speech": "根据本次检索取得的测试法律资料，适用条件为测试条件甲。", "pending_points": []}
    handoff = {"state_version": 102, "decision": "HANDOFF", "speech": "当前无法取得充分法律依据，请人工处理。", "pending_points": ["核对法律依据"]}
    case("law-no-action-response", "law-check", "response", no_action, request=LAW_ORDINARY)
    case("law-explain-response", "law-check", "response", explain, request=LAW_EXPLICIT)
    case("law-handoff-response", "law-check", "response", handoff, request=LAW_EXPLICIT)
    case("law-no-action-nonempty-speech", "law-check", "response", changed(no_action, "speech", "不需要解释。"), False, reason="schema")
    case("law-no-action-points", "law-check", "response", changed(no_action, "pending_points", ["不应存在"]), False, reason="schema")
    case("law-explain-empty", "law-check", "response", changed(explain, "speech", ""), False, reason="schema")
    case("law-handoff-no-points", "law-check", "response", changed(handoff, "pending_points", []), False, reason="schema")
    case("law-response-target-forbidden", "law-check", "response", {**no_action, "target": None}, False, reason="schema")
    case("law-response-flow-decision", "law-check", "response", changed(no_action, "decision", "COMPLETE"), False, reason="schema")
    case("law-response-stale", "law-check", "response", changed(no_action, "state_version", 100), False, request=LAW_ORDINARY, reason="stale_state")
    case("law-response-speech-max", "law-check", "response", changed(explain, "speech", "述" * 4000))
    case("law-response-speech-over-max", "law-check", "response", changed(explain, "speech", "述" * 4001), False, reason="schema")
    encoded_response = json.dumps(no_action, ensure_ascii=False)
    raw_case("law-response-body-max", "law-check", "response", encoded_response + " " * (131072 - len(encoded_response.encode("utf-8"))), True, "")
    raw_case("law-response-body-over-max", "law-check", "response", encoded_response + " " * (131073 - len(encoded_response.encode("utf-8"))), False, "body_size")

    case("next-investigation-request", "next-action", "request", INVESTIGATION_REQUEST)
    case("next-debate-request", "next-action", "request", DEBATE_REQUEST)
    case("next-investigation-complete-only", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_actions", ["COMPLETE", "HANDOFF"]))
    case("next-empty-records", "next-action", "request", changed(INVESTIGATION_REQUEST, "records", []))
    case("next-summary-record", "next-action", "request", changed(INVESTIGATION_REQUEST, "records", [{"type": "SUMMARY", "role": None, "text": "双方已说明图片来源，尚未说明平台授权范围。"}]))
    case("next-records-max", "next-action", "request", changed(INVESTIGATION_REQUEST, "records", [{"type": "SPEECH", "role": "DEFENDANT", "text": "答"}] * 512))
    case("next-law-action-forbidden", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_actions", ["ASK", "EXPLAIN_LAW", "HANDOFF"]), False, reason="schema")
    case("next-no-action-forbidden", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_actions", ["ASK", "NO_ACTION", "HANDOFF"]), False, reason="schema")
    case("next-missing-handoff", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_actions", ["ASK", "COMPLETE"]), False, reason="schema")
    case("next-duplicate-actions", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_actions", ["ASK", "ASK", "HANDOFF"]), False, reason="schema")
    case("next-investigation-continue", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_actions", ["CONTINUE", "HANDOFF"]), False, reason="schema")
    case("next-debate-ask", "next-action", "request", changed(DEBATE_REQUEST, "allowed_actions", ["ASK", "HANDOFF"]), False, reason="schema")
    case("next-ask-no-targets", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_targets", []), False, reason="schema")
    case("next-duplicate-targets", "next-action", "request", changed(INVESTIGATION_REQUEST, "allowed_targets", ["PLAINTIFF", "PLAINTIFF"]), False, reason="schema")
    case("next-debate-no-issue", "next-action", "request", changed(DEBATE_REQUEST, "current_issue", None), False, reason="schema")
    case("next-debate-no-summary", "next-action", "request", changed(DEBATE_REQUEST, "case_context", BASE_CONTEXT), False, reason="schema")
    case("next-investigation-summary-forbidden", "next-action", "request", changed(INVESTIGATION_REQUEST, "case_context", DEBATE_REQUEST["case_context"]), False, reason="schema")
    case("next-summary-role-forbidden", "next-action", "request", changed(INVESTIGATION_REQUEST, "records", [{"type": "SUMMARY", "role": "JUDGE", "text": "摘要"}]), False, reason="schema")
    case("next-records-over-max", "next-action", "request", changed(INVESTIGATION_REQUEST, "records", [{"type": "SPEECH", "role": "DEFENDANT", "text": "回答"}] * 513), False, reason="schema")
    case("next-missing-records", "next-action", "request", {key: value for key, value in INVESTIGATION_REQUEST.items() if key != "records"}, False, reason="schema")
    case("next-unknown-field", "next-action", "request", {**INVESTIGATION_REQUEST, "task": "legacy"}, False, reason="schema")
    case("next-version-boolean", "next-action", "request", changed(INVESTIGATION_REQUEST, "state_version", True), False, reason="schema")

    budget = copy.deepcopy(INVESTIGATION_REQUEST)
    budget["case_context"] = {"summary": "述", "claims": [], "defenses": [], "dispute_focuses": []}
    budget["records"] = [{"type": "SPEECH", "role": "D", "text": "述" * 7999} for _ in range(8)]
    case("next-content-budget-over", "next-action", "request", budget, False, reason="content_budget")

    ask = {"state_version": 120, "decision": "ASK", "target": "DEFENDANT", "speech": "被告，请说明平台展示的授权范围。", "pending_points": ["图片授权范围"]}
    complete = {"state_version": 120, "decision": "COMPLETE", "target": None, "speech": "双方已说明图片来源和使用情况，对授权范围仍有分歧，调查阶段结束。", "pending_points": ["双方对授权范围仍有分歧"]}
    cont = {"state_version": 220, "decision": "CONTINUE", "target": None, "speech": "请双方围绕律师费与本案的关联性和必要性补充意见。", "pending_points": ["律师费关联性和必要性"]}
    action_handoff = {"state_version": 120, "decision": "HANDOFF", "target": None, "speech": "已有记录不足以安全继续，请人工处理。", "pending_points": ["补充上一轮回答"]}
    case("next-ask-response", "next-action", "response", ask, request=INVESTIGATION_REQUEST)
    case("next-complete-response", "next-action", "response", complete, request=INVESTIGATION_REQUEST)
    case("next-continue-response", "next-action", "response", cont, request=DEBATE_REQUEST)
    case("next-handoff-response", "next-action", "response", action_handoff, request=INVESTIGATION_REQUEST)
    case("next-response-explain-forbidden", "next-action", "response", changed(complete, "decision", "EXPLAIN_LAW"), False, reason="schema")
    case("next-response-no-action-forbidden", "next-action", "response", changed(complete, "decision", "NO_ACTION"), False, reason="schema")
    case("next-response-decision-not-allowed", "next-action", "response", ask, False, changed(INVESTIGATION_REQUEST, "allowed_actions", ["COMPLETE", "HANDOFF"]), "decision_not_allowed")
    case("next-response-target-not-allowed", "next-action", "response", changed(ask, "target", "WITNESS"), False, INVESTIGATION_REQUEST, "target_not_allowed")
    case("next-response-stale", "next-action", "response", changed(ask, "state_version", 119), False, INVESTIGATION_REQUEST, "stale_state")
    case("next-complete-target-forbidden", "next-action", "response", changed(complete, "target", "DEFENDANT"), False, reason="schema")
    case("next-continue-no-points", "next-action", "response", changed(cont, "pending_points", []), False, reason="schema")
    case("next-handoff-no-points", "next-action", "response", changed(action_handoff, "pending_points", []), False, reason="schema")
    case("next-response-blank-speech", "next-action", "response", changed(ask, "speech", "   "), False, reason="schema")
    case("next-response-speech-max", "next-action", "response", changed(ask, "speech", "述" * 4000))
    case("next-response-speech-over-max", "next-action", "response", changed(ask, "speech", "述" * 4001), False, reason="schema")
    case("next-response-points-over-max", "next-action", "response", changed(ask, "pending_points", ["事项"] * 31), False, reason="schema")
    encoded_next_response = json.dumps(complete, ensure_ascii=False)
    raw_case("next-response-body-max", "next-action", "response", encoded_next_response + " " * (131072 - len(encoded_next_response.encode("utf-8"))), True, "")
    raw_case("next-response-body-over-max", "next-action", "response", encoded_next_response + " " * (131073 - len(encoded_next_response.encode("utf-8"))), False, "body_size")

    save("manifest.json", {"revision": REVISION, "cases": CASES})


def write_metadata(protocol: Path) -> None:
    save(
        "limits.json",
        {
            "revision": REVISION,
            "request_body_max_bytes": 524288,
            "response_body_max_bytes": 131072,
            "next_action_content_max_codepoints": 64000,
            "server_total_timeout_seconds": 120,
            "client_timeout_seconds": 135,
            "max_output_repair_attempts": 1,
            "length_semantics": "All lengths are Unicode code points before trimming.",
            "state_version_rule": "One committed party speech per state_version until its law-check result is consumed; same-version retries must have identical bodies.",
            "token_budget": "The implementation must also reserve model prompt, tool and output tokens and must not silently truncate records.",
        },
    )
    save(
        "behavior-scenarios.json",
        {
            "revision": REVISION,
            "status": "Frozen expectations only; not proof that either endpoint is implemented",
            "scenarios": [
                {"id": "ordinary-statement", "request_fixture": "law-ordinary-request", "expect": {"decision": "NO_ACTION", "law_tool_calls": 0, "tts_calls": 0}},
                {"id": "context-cannot-trigger", "setup": "text is an ordinary statement while context contains explicit legal questions", "expect": {"decision": "NO_ACTION", "law_tool_calls": 0}},
                {"id": "explicit-law-question", "request_fixture": "law-explicit-request", "expect": {"decision": "EXPLAIN_LAW", "law_tool": "intellectual_property_law_search", "minimum_tool_calls": 1, "speech_supported_by_current_tool_result": True}},
                {"id": "retrieval-failure", "request_fixture": "law-explicit-request", "expect": {"decision": "HANDOFF", "pending_points_min_items": 1, "fabricated_citation": False}},
                {"id": "no-action-must-not-search", "expect": {"decision": "NO_ACTION", "maximum_tool_calls": 0}},
                {"id": "single-agent-law-chain", "expect": {"agent": "virtual_court_law_check_judge", "separate_intent_agent": False}},
                {"id": "one-version-one-speech", "expect": {"same_version_different_body_rejected": True, "duplicate_response_consumed_once": True}},
                {"id": "explanation-resume", "expect": {"save_before_play": True, "round_delta": 0, "resume_original_position": True, "judge_explanation_retriggers_check": False}},
                {"id": "stale-or-takeover", "expect": {"stale_response_applied": False, "manual_takeover_invalidates_callbacks": True}},
                {"id": "investigation-actions", "request_fixture": "next-investigation-request", "expect": {"allowed": ["ASK", "COMPLETE", "HANDOFF"], "law_tool_calls": 0}},
                {"id": "debate-actions", "request_fixture": "next-debate-request", "expect": {"allowed": ["CONTINUE", "COMPLETE", "HANDOFF"], "law_tool_calls": 0}},
                {"id": "debate-barrier", "expect": {"next_action_before_both_law_checks": False, "party_order_preserved": True}},
                {"id": "split-tool-bindings", "expect": {"virtual_court_law_check_judge": ["intellectual_property_law_search"], "virtual_court_investigation_judge": [], "virtual_court_debate_judge": []}},
                {"id": "shared-deadline", "expect": {"server_total_seconds": 120, "maximum_repairs": 1, "retrieval_included": True}},
            ],
        },
    )
    (ROOT / "protocol-frozen.md").write_bytes(protocol.read_bytes())


def write_readme() -> None:
    text = f"""# JudgeAPI V2 双接口冻结契约

修订标识：`{REVISION}`。本目录是 `/judge/law-check` 与 `/judge/next-action` 的共享契约源。旧 `JudgeV2` 和 `JudgeV2LegalExtension` 目录只保留历史记录，不再定义当前接口。

## 内容

- `protocol-frozen.md`：冻结时的协议快照。
- `schemas/`：四份 Draft 2020-12 请求/响应 Schema。
- `manifest.json` 与 `cases/`：合法、非法及请求绑定响应样例。
- `contexts/`：验证响应权限、目标和状态版本时使用的请求。
- `behavior-scenarios.json`：工具、模型语义、播放恢复和状态机验收要求。
- `limits.json`：字节、码点、超时和纠错边界。
- `integrity.json`：冻结文件的 SHA-256 清单。
- `verify_fixtures.py`：离线契约和完整性验证器。
- `build_fixtures.py`：显式重新冻结生成器，不调用应用、LLM 或检索服务。

## 接口边界

| 端点 | 请求重点 | 响应决策 |
| --- | --- | --- |
| `{LAW_PATH}` | `state_version`、`role`、`text`、可选 `context` | `NO_ACTION`、`EXPLAIN_LAW`、`HANDOFF` |
| `{ACTION_PATH}` | 阶段、允许动作、案件上下文、当前争点、完整相关记录 | 调查：`ASK/COMPLETE/HANDOFF`；辩论：`CONTINUE/COMPLETE/HANDOFF` |

法律检查请求禁止完整 `records`，响应没有 `target`。流程请求和响应禁止 `EXPLAIN_LAW`、`NO_ACTION`。

静态 Schema 通过不证明真实模型正确理解普通陈述，也不证明工具调用和客户端恢复链已经实现；这些要求必须按 `behavior-scenarios.json` 另行验证。

## 验证

```powershell
python verify_fixtures.py
```

成功时退出码为 0，并报告全部样例与完整性检查通过。
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def freeze_integrity() -> None:
    entries = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "integrity.json" or "__pycache__" in path.parts:
            continue
        entries[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    save("integrity.json", entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    write_schemas()
    write_cases()
    write_metadata(args.protocol)
    write_readme()
    freeze_integrity()
    print(f"Generated {len(CASES)} cases for {REVISION}")


if __name__ == "__main__":
    main()
