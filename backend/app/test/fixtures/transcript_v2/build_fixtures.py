"""Build the frozen VirtualCourt TranscriptAPI V2 contract fixtures.

This is an offline contract tool. It does not import the application, call an
LLM, or mutate a database. Re-running it is an explicit protocol re-freeze.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


REVISION = "2026-09-17-transcript-v2"
ENDPOINT = "/api/v2/integrations/virtual-court/transcript/generate"
ROOT = Path(__file__).resolve().parent
REQUEST_MAX_BYTES = 524288
RESPONSE_MAX_BYTES = 524288
CONTENT_MAX_CODEPOINTS = 64000
TRANSCRIPT_MAX_CODEPOINTS = 64000


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


def array(item, maximum: int):
    return {
        "type": "array",
        "items": item,
        "minItems": 0,
        "maxItems": maximum,
    }


def obj(properties):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


VERSION = {
    "type": "integer",
    "minimum": 0,
    "maximum": 9223372036854775807,
}
ROLE = string(64)
CASE_CONTEXT = obj(
    {
        "summary": string(16000),
        "claims": array(string(4000), 30),
        "defenses": array(string(4000), 30),
        "dispute_focuses": array(string(1000), 20),
    }
)
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
TRANSCRIPT_REQUEST = obj(
    {
        "state_version": VERSION,
        "case_context": CASE_CONTEXT,
        "records": array(RECORD, 512),
    }
)
TRANSCRIPT_RESPONSE = obj(
    {
        "state_version": VERSION,
        "transcript": string(TRANSCRIPT_MAX_CODEPOINTS),
    }
)


BASE_CONTEXT = {
    "summary": "原告主张被告未经许可使用涉案作品，被告主张已经获得授权。",
    "claims": ["停止侵权", "赔偿经济损失"],
    "defenses": ["被告主张使用行为已经获得授权"],
    "dispute_focuses": ["被告是否获得授权", "被诉行为是否构成侵权"],
}
BASE_REQUEST = {
    "state_version": 42,
    "case_context": BASE_CONTEXT,
    "records": [
        {
            "type": "SPEECH",
            "role": "JUDGE",
            "text": "现在开庭，请原告陈述诉讼请求。",
        },
        {
            "type": "SPEECH",
            "role": "PLAINTIFF",
            "text": "请求判令被告停止侵权并赔偿经济损失。",
        },
        {
            "type": "SPEECH",
            "role": "DEFENDANT",
            "text": "我方认为已经获得相关授权。",
        },
    ],
}
SUMMARY_REQUEST = {
    **BASE_REQUEST,
    "state_version": 43,
    "records": [
        {
            "type": "SUMMARY",
            "role": None,
            "text": "此前原告请求停止侵权并赔偿损失，被告主张已经获得授权。",
        },
        {
            "type": "SPEECH",
            "role": "JUDGE",
            "text": "双方是否还有补充？",
        },
    ],
}


CASES = []


def case(name, kind, data, valid=True, request=None, reason=None):
    path = f"cases/{name}.json"
    save(path, data)
    item = {
        "id": name,
        "endpoint": "transcript",
        "kind": kind,
        "schema": f"transcript-{kind}",
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


def raw_case(name, kind, text, valid, reason=""):
    path = ROOT / f"cases/{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    item = {
        "id": name,
        "endpoint": "transcript",
        "kind": kind,
        "schema": f"transcript-{kind}",
        "file": f"cases/{name}.json",
        "valid": valid,
    }
    if reason:
        item["reason"] = reason
    CASES.append(item)


def changed(data, key, value):
    result = copy.deepcopy(data)
    result[key] = value
    return result


def write_schemas() -> None:
    for name, source in {
        "transcript-request": TRANSCRIPT_REQUEST,
        "transcript-response": TRANSCRIPT_RESPONSE,
    }.items():
        schema = copy.deepcopy(source)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:virtual-court:transcript-v2:{name}:{REVISION}"
        schema["title"] = "TranscriptV2-" + name
        save(f"schemas/{name}.schema.json", schema)


def write_cases() -> None:
    case("transcript-speech-request", "request", BASE_REQUEST)
    case("transcript-summary-request", "request", SUMMARY_REQUEST)
    case("transcript-empty-records", "request", changed(BASE_REQUEST, "records", []))
    case(
        "transcript-state-version-max",
        "request",
        changed(BASE_REQUEST, "state_version", 9223372036854775807),
    )
    case(
        "transcript-speech-text-max",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SPEECH", "role": "JUDGE", "text": "述" * 8000}],
        ),
    )
    case(
        "transcript-summary-text-max",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SUMMARY", "role": None, "text": "摘" * 16000}],
        ),
    )
    case(
        "transcript-unknown-field",
        "request",
        {**BASE_REQUEST, "options": {}},
        False,
        reason="schema",
    )
    case(
        "transcript-missing-records",
        "request",
        {key: value for key, value in BASE_REQUEST.items() if key != "records"},
        False,
        reason="schema",
    )
    case(
        "transcript-version-boolean",
        "request",
        changed(BASE_REQUEST, "state_version", True),
        False,
        reason="schema",
    )
    case(
        "transcript-version-negative",
        "request",
        changed(BASE_REQUEST, "state_version", -1),
        False,
        reason="schema",
    )
    case(
        "transcript-speech-role-null",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SPEECH", "role": None, "text": "现在开庭。"}],
        ),
        False,
        reason="schema",
    )
    case(
        "transcript-summary-role-forbidden",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SUMMARY", "role": "JUDGE", "text": "庭审摘要。"}],
        ),
        False,
        reason="schema",
    )
    case(
        "transcript-record-type-invalid",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "EVENT", "role": "JUDGE", "text": "现在开庭。"}],
        ),
        False,
        reason="schema",
    )
    case(
        "transcript-speech-text-over-max",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SPEECH", "role": "JUDGE", "text": "述" * 8001}],
        ),
        False,
        reason="schema",
    )
    case(
        "transcript-summary-text-over-max",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SUMMARY", "role": None, "text": "摘" * 16001}],
        ),
        False,
        reason="schema",
    )
    case(
        "transcript-records-over-max",
        "request",
        changed(
            BASE_REQUEST,
            "records",
            [{"type": "SPEECH", "role": "JUDGE", "text": "答"}] * 513,
        ),
        False,
        reason="schema",
    )

    budget = changed(
        BASE_REQUEST,
        "case_context",
        {"summary": "述", "claims": [], "defenses": [], "dispute_focuses": []},
    )
    budget["records"] = [
        {"type": "SPEECH", "role": "D", "text": "述" * 7999}
        for _ in range(8)
    ]
    case(
        "transcript-content-budget-over",
        "request",
        budget,
        False,
        reason="content_budget",
    )

    encoded_request = json.dumps(BASE_REQUEST, ensure_ascii=False)
    raw_case(
        "transcript-duplicate-key",
        "request",
        encoded_request[:-1] + ',"state_version":42}',
        False,
        "invalid_json",
    )
    raw_case(
        "transcript-markdown-fence",
        "request",
        "```json\n" + encoded_request + "\n```",
        False,
        "invalid_json",
    )
    raw_case(
        "transcript-request-body-max",
        "request",
        encoded_request
        + " " * (REQUEST_MAX_BYTES - len(encoded_request.encode("utf-8"))),
        True,
    )
    raw_case(
        "transcript-request-body-over-max",
        "request",
        encoded_request
        + " " * (REQUEST_MAX_BYTES + 1 - len(encoded_request.encode("utf-8"))),
        False,
        "body_size",
    )

    response = {
        "state_version": 42,
        "transcript": (
            "庭审笔录\n\n审判员：现在开庭，请原告陈述诉讼请求。\n\n"
            "原告：请求判令被告停止侵权并赔偿经济损失。\n\n"
            "被告：我方认为已经获得相关授权。"
        ),
    }
    case(
        "transcript-response",
        "response",
        response,
        request=BASE_REQUEST,
    )
    case(
        "transcript-response-summary-source",
        "response",
        {
            "state_version": 43,
            "transcript": "庭审笔录\n\n此前庭审记录摘要：原告请求停止侵权并赔偿损失，被告主张已经获得授权。\n\n审判员：双方是否还有补充？",
        },
        request=SUMMARY_REQUEST,
    )
    case(
        "transcript-response-blank",
        "response",
        changed(response, "transcript", "   "),
        False,
        reason="schema",
    )
    case(
        "transcript-response-missing-transcript",
        "response",
        {"state_version": 42},
        False,
        reason="schema",
    )
    case(
        "transcript-response-unknown-field",
        "response",
        {**response, "warnings": []},
        False,
        reason="schema",
    )
    case(
        "transcript-response-version-boolean",
        "response",
        changed(response, "state_version", True),
        False,
        reason="schema",
    )
    case(
        "transcript-response-stale",
        "response",
        changed(response, "state_version", 41),
        False,
        request=BASE_REQUEST,
        reason="stale_state",
    )
    case(
        "transcript-response-text-max",
        "response",
        changed(response, "transcript", "录" * TRANSCRIPT_MAX_CODEPOINTS),
    )
    case(
        "transcript-response-text-over-max",
        "response",
        changed(response, "transcript", "录" * (TRANSCRIPT_MAX_CODEPOINTS + 1)),
        False,
        reason="schema",
    )

    encoded_response = json.dumps(response, ensure_ascii=False)
    raw_case(
        "transcript-response-body-max",
        "response",
        encoded_response
        + " " * (RESPONSE_MAX_BYTES - len(encoded_response.encode("utf-8"))),
        True,
    )
    raw_case(
        "transcript-response-body-over-max",
        "response",
        encoded_response
        + " " * (RESPONSE_MAX_BYTES + 1 - len(encoded_response.encode("utf-8"))),
        False,
        "body_size",
    )

    save("manifest.json", {"revision": REVISION, "cases": CASES})


def write_metadata(protocol: Path) -> None:
    save(
        "limits.json",
        {
            "revision": REVISION,
            "request_body_max_bytes": REQUEST_MAX_BYTES,
            "response_body_max_bytes": RESPONSE_MAX_BYTES,
            "content_max_codepoints": CONTENT_MAX_CODEPOINTS,
            "transcript_max_codepoints": TRANSCRIPT_MAX_CODEPOINTS,
            "records_max_items": 512,
            "max_output_repair_attempts": 1,
            "length_semantics": "All string lengths are Unicode code points before trimming.",
            "token_budget": "The implementation must reserve prompt and output tokens and must not silently truncate records.",
        },
    )
    save(
        "behavior-scenarios.json",
        {
            "revision": REVISION,
            "status": "Frozen expectations only; not proof that the endpoint or agent is implemented",
            "scenarios": [
                {
                    "id": "speech-order-preserved",
                    "request_fixture": "transcript-speech-request",
                    "expect": {"record_order_preserved": True, "fabricated_content": False},
                },
                {
                    "id": "summary-not-expanded-to-verbatim",
                    "request_fixture": "transcript-summary-request",
                    "expect": {"summary_identified_as_summary": True, "invented_speaker": False},
                },
                {
                    "id": "trusted-state-version",
                    "expect": {"state_version_sent_to_model": False, "state_version_injected_by_server": True},
                },
                {
                    "id": "dedicated-agent-no-tools",
                    "expect": {"agent": "virtual_court_transcript_writer", "tools": []},
                },
                {
                    "id": "invalid-output-repaired-once",
                    "expect": {"maximum_repairs": 1, "invalid_raw_output_exposed": False},
                },
                {
                    "id": "shared-deadline",
                    "expect": {"generation_and_repair_share_deadline": True},
                },
                {
                    "id": "stale-response-rejected-by-client",
                    "expect": {"stale_response_applied": False},
                },
                {
                    "id": "complete-context-or-explicit-error",
                    "expect": {"silent_truncation": False, "silent_record_removal": False},
                },
                {
                    "id": "record-prompt-injection-is-data",
                    "expect": {"record_instructions_executed": False},
                },
                {
                    "id": "confidential-logging",
                    "expect": {"request_body_logged": False, "model_raw_output_logged": False},
                },
            ],
        },
    )
    (ROOT / "protocol-frozen.md").write_bytes(protocol.read_bytes())


def write_readme() -> None:
    text = f"""# TranscriptAPI V2 冻结契约

修订标识：`{REVISION}`。本目录是 `{ENDPOINT}` 的离线契约基线，不表示接口或专用 Agent 已经实现。

## 内容

- `protocol-frozen.md`：冻结时的协议快照。
- `schemas/`：Draft 2020-12 请求和响应 Schema。
- `manifest.json` 与 `cases/`：合法、非法以及边界样例。
- `contexts/`：校验响应 `state_version` 时使用的请求。
- `behavior-scenarios.json`：模型语义、状态和安全验收要求。
- `limits.json`：字节、码点、记录数量和纠错边界。
- `integrity.json`：冻结文件的 SHA-256 清单。
- `verify_fixtures.py`：离线契约和完整性验证器。
- `build_fixtures.py`：显式重新冻结生成器，不导入应用或调用模型。

## 最小接口边界

| 方向 | 字段 |
| --- | --- |
| 请求 | `state_version`、`case_context`、`records` |
| 响应 | `state_version`、`transcript` |

`records` 允许 `SPEECH` 和 `SUMMARY`。摘要只能作为摘要处理，不能恢复或伪造逐字发言。

静态 Schema 通过不证明模型能够忠实生成笔录；相关要求必须按 `behavior-scenarios.json` 另行验证。

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
