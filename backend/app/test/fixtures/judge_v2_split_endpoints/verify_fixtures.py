"""Offline oracle for the frozen split-endpoint JudgeAPI V2 contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent


def read(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def content_size(value) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(content_size(item) for item in value.values())
    if isinstance(value, list):
        return sum(content_size(item) for item in value)
    return 0


def main() -> int:
    limits = read(ROOT / "limits.json")
    validators = {}
    for name in (
        "law-check-request",
        "law-check-response",
        "next-action-request",
        "next-action-response",
    ):
        schema = read(ROOT / f"schemas/{name}.schema.json")
        Draft202012Validator.check_schema(schema)
        validators[name] = Draft202012Validator(schema)

    manifest = read(ROOT / "manifest.json")
    failures = []
    passed = 0
    for item in manifest["cases"]:
        path = ROOT / item["file"]
        reason = ""
        try:
            data = read(path)
            if list(validators[item["schema"]].iter_errors(data)):
                reason = "schema"
        except ValueError:
            data = None
            reason = "invalid_json"

        if not reason:
            body_limit = limits[
                "request_body_max_bytes"
                if item["kind"] == "request"
                else "response_body_max_bytes"
            ]
            if path.stat().st_size > body_limit:
                reason = "body_size"
            elif item["schema"] == "next-action-request":
                size = content_size(data["case_context"])
                size += content_size(data["records"])
                size += len((data["current_issue"] or {}).get("question", ""))
                if size > limits["next_action_content_max_codepoints"]:
                    reason = "content_budget"

        if not reason and item.get("request"):
            request = read(ROOT / item["request"])
            if data["state_version"] != request["state_version"]:
                reason = "stale_state"
            elif item["endpoint"] == "next-action":
                if data["decision"] not in request["allowed_actions"]:
                    reason = "decision_not_allowed"
                elif data["decision"] == "ASK" and data["target"] not in request["allowed_targets"]:
                    reason = "target_not_allowed"

        expected_reason = item.get("reason", "")
        ok = (not reason) == item["valid"] and (
            not expected_reason or reason == expected_reason
        )
        if ok:
            passed += 1
        else:
            failures.append(
                {
                    "id": item["id"],
                    "expected_valid": item["valid"],
                    "expected_reason": expected_reason,
                    "actual_reason": reason,
                }
            )

    integrity = read(ROOT / "integrity.json")
    actual_files = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path.name != "integrity.json" and "__pycache__" not in path.parts
    }
    if actual_files != set(integrity):
        failures.append({"id": "integrity:file-set", "passed": False})
    for name, expected in integrity.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            failures.append({"id": "integrity:" + name, "passed": False})

    behavior = read(ROOT / "behavior-scenarios.json")
    if behavior["revision"] != manifest["revision"] or limits["revision"] != manifest["revision"]:
        failures.append({"id": "revision:mismatch", "passed": False})

    print(
        json.dumps(
            {
                "revision": manifest["revision"],
                "total": len(manifest["cases"]),
                "passed": passed,
                "behavior_scenarios": len(behavior["scenarios"]),
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
