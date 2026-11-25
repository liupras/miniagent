"""Dedicated verdict Agent; room bindings stay outside the model prompt."""

import asyncio
import json

from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.exceptions import ToolNotRegisteredError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court.criminal_verdict import (
    CriminalVerdictRequest, CriminalVerdictResponse, _schema,
)
from app.services.virtual_court.exceptions import (
    InvestigationConfigurationError, InvestigationContextError,
    InvestigationInvalidResponseError, InvestigationTimeoutError,
    InvestigationUnavailableError,
)


AGENT = "virtual_court_criminal_verdict"


def _invalid(field: str):
    raise InvestigationInvalidResponseError(
        params={"reason": "schema_validation_failed", "field": field})


def validate_decision(request: CriminalVerdictRequest, result: dict) -> None:
    """Verify every model citation against the frozen courtroom basis."""
    basis = request.basis
    focus_ids = {item["focusId"] for item in basis["disputeFocuses"]}
    charge_ids = {item["chargeId"] for item in basis["charges"]}
    legal_ids = {item["legalSourceId"] for item in basis["legalSources"]}
    speech_ids = {str(item["sequence"]) for item in basis["records"]}
    evidence_ids = {item["materialId"] for item in basis["evidenceMaterials"]
                    if item["usageStatus"] != "listed"}
    decision = result["decision"]
    if not any(word in decision["pronouncementText"]
               for word in ("模拟", "教学", "训练")):
        _invalid("decision.pronouncementText")
    findings = decision["findings"]
    charges = decision["chargeDecisions"]
    if ({item["focusId"] for item in findings} != focus_ids or
            len(findings) != len(focus_ids) or
            {item["chargeId"] for item in charges} != charge_ids or
            len(charges) != len(charge_ids)):
        _invalid("decision")

    def check_refs(refs):
        for ref in refs:
            kind, identifier = ref.split(":", 1)
            if identifier not in {
                "evidence": evidence_ids, "speech": speech_ids,
                "legal": legal_ids,
            }[kind]:
                _invalid("decision.references")

    for finding in findings:
        check_refs(finding["supportRefs"])
        check_refs(finding["contraryRefs"])
    for charge in charges:
        if (set(charge["legalSourceIds"]) - legal_ids or
                not charge["reason"].strip() or
                charge["outcome"] == "convicted" and
                not charge["dispositionText"].strip()):
            _invalid("decision.chargeDecisions")
        check_refs(charge["basisRefs"])


def model_result(raw: str, request: CriminalVerdictRequest) -> dict:
    try:
        result = strict_json(raw, max_bytes=131_072)
    except (ValueError, UnicodeError, RecursionError):
        _invalid("response")
    if not isinstance(result, dict) or result.get("status") not in \
            {"decision", "handoff"}:
        _invalid("status")
    if set(result) != ({"status", "decision"} if result["status"] == "decision"
                       else {"status", "handoffReason"}):
        _invalid("response")
    envelope = {
        "contractVersion": request.contractVersion,
        "decisionRunId": request.decisionRunId,
        "roomEpoch": request.roomEpoch,
        "stepRunId": request.stepRunId,
        "sourceStateVersion": request.sourceStateVersion,
        "basisSha256": request.basisSha256,
        **result,
    }
    error = next(_schema("criminal-verdict-response-v1.schema.json")
                 .iter_errors(envelope), None)
    if error is not None:
        _invalid("decision" if result["status"] == "decision" else "handoffReason")
    if result["status"] == "decision":
        validate_decision(request, result)
    return result


class CriminalVerdictService:
    def __init__(self, agent_factory, *, timeout_seconds=120.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def run(self, request: CriminalVerdictRequest) -> CriminalVerdictResponse:
        query = json.dumps({"basis": request.basis}, ensure_ascii=False)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(AGENT)
                history = None
                for attempt in range(2):
                    execution = None
                    try:
                        execution = await runner.execute(
                            query=query, history=history, preserve_context=True)
                        if execution.stop_reason != "completed" or execution.tools:
                            _invalid("execution")
                        result = model_result(execution.text, request)
                        return CriminalVerdictResponse(
                            contractVersion=request.contractVersion,
                            decisionRunId=request.decisionRunId,
                            roomEpoch=request.roomEpoch,
                            stepRunId=request.stepRunId,
                            sourceStateVersion=request.sourceStateVersion,
                            basisSha256=request.basisSha256,
                            **result,
                        )
                    except ToolNotRegisteredError:
                        error = InvestigationInvalidResponseError(
                            params={"reason": "unexpected_tool_call", "field": "response"})
                    except InvestigationInvalidResponseError as exc:
                        error = exc
                    if attempt:
                        raise error
                    history = [
                        {"role": "user", "content": json.dumps(
                            {"basis": request.basis}, ensure_ascii=False)},
                        {"role": "assistant", "content": execution.text if execution else ""},
                    ]
                    query = "请仅修正 JSON。错误字段：" + str(
                        error.params.get("field", "response"))
        except TimeoutError as exc:
            raise InvestigationTimeoutError(cause=exc) from exc
        except ContextBudgetExceeded as exc:
            raise InvestigationContextError(cause=exc) from exc
        except (ToolBuildError, AgentNotFoundError, AgentInactiveError) as exc:
            raise InvestigationConfigurationError(cause=exc) from exc
        except LLMClientError as exc:
            raise InvestigationUnavailableError(cause=exc) from exc
