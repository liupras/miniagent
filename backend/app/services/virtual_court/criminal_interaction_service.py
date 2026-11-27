"""Four criminal agents using the existing MiniAgent runner and error framework."""

import asyncio
import json

from pydantic import ValidationError

from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.exceptions import ToolNotRegisteredError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court.criminal_interaction import (
    CriminalInteractionRequest, CriminalInteractionResponse,
    MODE_PARTY_ROLES, SPEECH_KINDS,
)
from app.services.virtual_court.exceptions import (
    InvestigationConfigurationError, InvestigationContextError,
    InvestigationInvalidResponseError, InvestigationTimeoutError,
    InvestigationUnavailableError,
)


AGENTS = {
    "intent": "virtual_court_criminal_intent",
    "participant_speech": "virtual_court_criminal_party_speech",
    "summary_speech": "virtual_court_criminal_party_speech",
    "witness_speech": "virtual_court_criminal_witness",
    "judge_action": "virtual_court_criminal_judge",
}
MAX_RESPONSE_BYTES = 131_072


def model_input(request: CriminalInteractionRequest) -> dict:
    """Exclude room bindings; expose case facts with their sources and current floor."""
    case = request.casePackage
    state = request.interaction
    witness = request.operation == "witness_speech"
    if witness:
        profile = next(item for item in case["witnessProfiles"]
                       if item["participantId"] == request.targetParticipantId)
        material_ids = set(profile["statementMaterialIds"])
        case_view = {
            "caseInfo": {key: case["caseInfo"][key]
                         for key in ("caseNumber", "courtName", "subjectMatter")},
            "sourceDocuments": case["sourceDocuments"],
            "participants": [{key: item[key] for key in
                              ("participantId", "role", "displayName")}
                             for item in case["participants"]],
            "evidenceGroups": [
                {"evidenceGroupId": group["evidenceGroupId"],
                 "materials": [item for item in group["materials"]
                               if item["materialId"] in material_ids]}
                for group in case["evidenceGroups"]
                if any(item["materialId"] in material_ids
                       for item in group["materials"])
            ],
        }
        records = [item for item in request.records
                   if item["participantId"] == request.targetParticipantId or
                   item["roleId"] == "judge" or
                   item["speechKind"] == "question_witness"]
    else:
        case_view = {key: case[key] for key in (
            "caseInfo", "sourceDocuments", "participants", "charges", "positions",
            "disputeFocuses", "evidenceGroups", "legalSources",
        )}
        records = request.records
    return {
        "operation": request.operation,
        "target": {"participantId": request.targetParticipantId,
                   "roleId": request.targetRoleId},
        "case": case_view,
        "witnessProfiles": (
            [profile] if witness else
            case["witnessProfiles"] if request.operation == "judge_action" else []
        ),
        "interaction": {key: state[key] for key in (
            "mode", "roundIndex", "roundLabels", "currentTopicId",
            "displayedEvidenceGroupIds", "presentedEvidenceGroupIds",
            "pendingRequests", "activeTurn",
        )},
        "records": records,
        **({"task": state["summaryTask"]} if request.operation == "summary_speech" else {}),
    }


def _invalid(field: str):
    raise InvestigationInvalidResponseError(
        params={"reason": "schema_validation_failed", "field": field})


def _model_result(raw: str, request: CriminalInteractionRequest) -> dict:
    try:
        result = strict_json(raw, max_bytes=MAX_RESPONSE_BYTES)
    except (ValueError, UnicodeError, RecursionError):
        _invalid("response")
    if not isinstance(result, dict):
        _invalid("response")
    operation = request.operation
    state = request.interaction
    case = request.casePackage
    topics = {item["focusId"] for item in case["disputeFocuses"]} | {"other"}
    people = {item["participantId"]: item["role"] for item in case["participants"]}
    presented = set(state["presentedEvidenceGroupIds"])
    if operation == "intent":
        decision = result.get("decision")
        if decision == "pass" and set(result) == {"decision"}:
            return result
        if (decision != "request" or
                set(result) not in ({"decision", "speechKind", "topicId"},
                                    {"decision", "speechKind", "topicId", "reason"}) or
                result.get("speechKind") not in SPEECH_KINDS[state["mode"]] or
                result.get("topicId") not in topics or
                not isinstance(result.get("reason", ""), str) or
                len(result.get("reason", "")) > 500):
            _invalid("intent")
        if any(item.get("participantId") == request.targetParticipantId and
               item.get("speechKind") == result["speechKind"] and
               item.get("topicId") == result["topicId"]
               for item in state["pendingRequests"]):
            return {"decision": "pass"}
        return result
    if operation in {"participant_speech", "summary_speech", "witness_speech"}:
        if (set(result) not in ({"speech"}, {"speech", "evidenceGroupIds"}) or
                not isinstance(result.get("speech"), str) or
                not result["speech"].strip() or len(result["speech"]) > 8000):
            _invalid("speech")
        ids = result.get("evidenceGroupIds", [])
        if (not isinstance(ids, list) or
                any(not isinstance(item, str) for item in ids) or
                len(ids) != len(set(ids)) or
                any(item not in presented for item in ids) or
                operation == "witness_speech" and ids):
            _invalid("evidenceGroupIds")
        return {"speech": result["speech"], "evidenceGroupIds": ids}

    decision = result.get("decision")
    # Accept a redundant action name in decision, including a missing action.type.
    if (decision in {"grant_request", "reject_request", "invite_participant",
                    "next_round", "close_investigation"} and
            isinstance(result.get("action"), dict) and
            result["action"].get("type", decision) == decision):
        result["action"].setdefault("type", decision)
        result["decision"] = decision = "action"
    action = result.get("action")
    if (decision == "action" and isinstance(action, dict) and
            state["mode"] == "criminal_investigation" and
            action.get("type") == "invite_participant" and
            people.get(action.get("participantId")) == "accused" and
            action.get("speechKind") == "answer_accused"):
        action["speechKind"] = "statement"
    if decision == "handoff":
        if (set(result) != {"decision", "reason"} or
                not isinstance(result.get("reason"), str) or
                not result["reason"].strip() or len(result["reason"]) > 8000):
            _invalid("reason")
        return result
    if (decision != "action" or set(result) != {"decision", "action", "utterance"} or
            not isinstance(result.get("action"), dict) or
            not isinstance(result.get("utterance"), str) or
            len(result["utterance"]) > 8000):
        _invalid("decision")
    action = result["action"]
    kind = action.get("type")
    if kind in {"grant_request", "reject_request"}:
        if (set(action) != {"type", "requestId"} or
                action.get("requestId") not in {
                    item.get("requestId") for item in state["pendingRequests"]
                    if not item.get("locked")
                }):
            _invalid("action.requestId")
    elif kind == "invite_participant":
        invitee_role = people.get(action.get("participantId"))
        if (set(action) not in ({"type", "participantId", "speechKind"},
                                {"type", "participantId", "speechKind", "topicId"}) or
                invitee_role not in MODE_PARTY_ROLES[state["mode"]] | (
                    {"witness"} if state["mode"] == "criminal_investigation" else set()) or
                action.get("speechKind") not in SPEECH_KINDS[state["mode"]] or
                invitee_role == "witness" and action.get("speechKind") != "statement" or
                action.get("topicId", state.get("currentTopicId")) not in topics):
            _invalid("action.invite_participant")
    elif kind == "next_round":
        if (set(action) != {"type"} or state["mode"] != "criminal_debate" or
                state["roundIndex"] >= len(state["roundLabels"]) or
                state["pendingRequests"]):
            _invalid("action.next_round")
    elif kind == "close_investigation":
        if (set(action) != {"type"} or not result["utterance"].strip() or
                state["pendingRequests"]):
            _invalid("action.close_investigation")
    else:
        _invalid("action.type")
    return result


class CriminalInteractionService:
    def __init__(self, agent_factory, *, timeout_seconds=120.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def run(self, request: CriminalInteractionRequest) -> CriminalInteractionResponse:
        query = json.dumps(model_input(request), ensure_ascii=False)
        agent_name = AGENTS[request.operation]
        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(agent_name)
                history = None
                for attempt in range(2):
                    execution = None
                    try:
                        execution = await runner.execute(
                            query=query, history=history, preserve_context=True)
                        if execution.stop_reason != "completed" or execution.tools:
                            _invalid("execution")
                        result = _model_result(execution.text, request)
                        turn = request.interaction.get("activeTurn")
                        return CriminalInteractionResponse(
                            contractVersion="criminal-ai-v1",
                            operation=request.operation,
                            callId=request.callId, roomEpoch=request.roomEpoch,
                            stepRunId=request.stepRunId,
                            sourceStateVersion=request.sourceStateVersion,
                            investigationId=request.interaction["investigationId"],
                            decisionRevision=request.interaction["decisionRevision"],
                            turnId=turn.get("turnId") if request.operation in
                                {"participant_speech", "summary_speech", "witness_speech"} else None,
                            result=result,
                        )
                    except ToolNotRegisteredError:
                        error = InvestigationInvalidResponseError(
                            params={"reason": "unexpected_tool_call", "field": "response"})
                    except InvestigationInvalidResponseError as exc:
                        error = exc
                    if attempt:
                        raise error
                    history = [
                        {"role": "user", "content": json.dumps(model_input(request), ensure_ascii=False)},
                        {"role": "assistant", "content": execution.text if execution else ""},
                    ]
                    field = str(error.params.get("field", "response"))
                    if field == "evidenceGroupIds":
                        allowed = request.interaction["presentedEvidenceGroupIds"]
                        query = ("请仅修正 JSON。evidenceGroupIds 只能从已出示证据组 " +
                                 json.dumps(allowed, ensure_ascii=False) +
                                 " 中选择；若为空，删去对未出示具体证据的引用，" +
                                 "仅围绕庭审已记录的发言表达，并填 []。")
                    else:
                        query = "请仅修正 JSON。错误字段：" + field
        except TimeoutError as exc:
            raise InvestigationTimeoutError(cause=exc) from exc
        except ContextBudgetExceeded as exc:
            raise InvestigationContextError(cause=exc) from exc
        except (ToolBuildError, AgentNotFoundError, AgentInactiveError) as exc:
            raise InvestigationConfigurationError(cause=exc) from exc
        except LLMClientError as exc:
            raise InvestigationUnavailableError(cause=exc) from exc
