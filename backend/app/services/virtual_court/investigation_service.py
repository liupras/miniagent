"""Three isolated agents for the unified investigation workflow."""

import asyncio
import json

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.exceptions import ToolNotRegisteredError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError

from .exceptions import (
    InvestigationConfigurationError,
    InvestigationContextError,
    InvestigationInvalidResponseError,
    InvestigationTimeoutError,
    InvestigationUnavailableError,
)
from .investigation_validator import (
    validate_intent_output,
    validate_judge_output,
    validate_speech_output,
)


logger = get_logger(__name__)


class InvestigationAgentService:
    AGENTS = {
        "intent": ("virtual_court_investigation_participant_intent", validate_intent_output),
        "speech": ("virtual_court_investigation_participant_speech", validate_speech_output),
        "judge": ("virtual_court_investigation_judge_dispatch", validate_judge_output),
    }

    def __init__(self, agent_factory, *, timeout_seconds=120.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def intent(self, request):
        return await self._run("intent", request)

    async def speech(self, request):
        return await self._run("speech", request)

    async def next_action(self, request):
        return await self._run("judge", request)

    async def _run(self, operation, request):
        agent_name, validator = self.AGENTS[operation]
        business_query = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(agent_name)
                history = None
                query = business_query
                for attempt in range(2):
                    result = None
                    try:
                        result = await runner.execute(
                            query=query, history=history, preserve_context=True
                        )
                        if result.stop_reason != "completed" or result.tools:
                            raise InvestigationInvalidResponseError(
                                params={"reason": "unexpected_agent_execution", "field": "response"}
                            )
                        response = validator(result.text, request)
                        logger.info(
                            "[InvestigationAgent] validated: operation={}, attempts={}, records={}",
                            operation, attempt + 1, len(request.records),
                        )
                        return response
                    except ToolNotRegisteredError as exc:
                        invalid = InvestigationInvalidResponseError(
                            params={"reason": "unexpected_tool_call", "field": "response"},
                            cause=exc,
                        )
                    except InvestigationInvalidResponseError as exc:
                        invalid = exc
                    logger.warning(
                        "[InvestigationAgent] output rejected: operation={}, attempt={}, diagnostic={}",
                        operation, attempt + 1, invalid.params,
                    )
                    if attempt == 1:
                        raise invalid
                    history = [
                        {"role": "user", "content": business_query},
                        {"role": "assistant", "content": result.text if result is not None else ""},
                    ]
                    query = (
                        "上次输出未通过校验。请仅根据原始输入修正 JSON；错误："
                        + json.dumps(invalid.params, ensure_ascii=False)
                    )
        except TimeoutError as exc:
            raise InvestigationTimeoutError(
                params={"timeout": self._timeout_seconds}, cause=exc
            ) from exc
        except ContextBudgetExceeded as exc:
            raise InvestigationContextError(
                params={"reason": "model_context_budget", "field": "records"}, cause=exc
            ) from exc
        except (ToolBuildError, AgentNotFoundError, AgentInactiveError) as exc:
            raise InvestigationConfigurationError(
                params={"reason": "agent_configuration"}, cause=exc
            ) from exc
        except LLMClientError as exc:
            raise InvestigationUnavailableError(cause=exc) from exc
