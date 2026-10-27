"""Generate a reviewable civil case draft from pleading and evidence text."""

import asyncio
import json

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.exceptions import ToolNotRegisteredError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError

from .civil_draft_validator import validate_civil_draft_agent_output
from .exceptions import (
    CivilDraftConfigurationError,
    CivilDraftContextError,
    CivilDraftInvalidResponseError,
    CivilDraftTimeoutError,
    CivilDraftUnavailableError,
)


logger = get_logger(__name__)


class CivilDraftService:
    AGENT_NAME = "virtual_court_civil_draft_generator"

    def __init__(self, agent_factory, *, timeout_seconds=300.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def generate(self, request):
        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(self.AGENT_NAME)
                business_query = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
                query = business_query
                history = None
                for attempt in range(2):
                    try:
                        result = await runner.execute(
                            query=query, history=history, preserve_context=True
                        )
                        if result.stop_reason != "completed" or result.tools:
                            raise CivilDraftInvalidResponseError(
                                params={"reason": "incomplete_or_tool_output", "field": "response"}
                            )
                        return validate_civil_draft_agent_output(result.text, request)
                    except ToolNotRegisteredError as exc:
                        invalid = CivilDraftInvalidResponseError(
                            params={"reason": "unexpected_tool_call", "field": "response"},
                            cause=exc,
                        )
                        raw = ""
                    except CivilDraftInvalidResponseError as exc:
                        invalid = exc
                        raw = result.text
                    logger.warning(
                        "[CivilDraftV1] output rejected: attempt={}, diagnostic={}",
                        attempt + 1,
                        invalid.params,
                    )
                    if attempt:
                        raise invalid
                    history = [
                        {"role": "user", "content": business_query},
                        {"role": "assistant", "content": raw},
                    ]
                    query = (
                        "上次输出未通过契约或来源校验。请重新核对原始材料、完整输出 JSON，"
                        "为每项诉请、答辩要点和证据摘录提供可定位的原文引文。"
                    )
        except TimeoutError as exc:
            raise CivilDraftTimeoutError(
                params={"timeout": self._timeout_seconds}, cause=exc
            ) from exc
        except ContextBudgetExceeded as exc:
            raise CivilDraftContextError(
                params={"reason": "model_context_budget", "field": "materials"}, cause=exc
            ) from exc
        except ToolBuildError as exc:
            raise CivilDraftConfigurationError(
                params={"reason": "agent_tool_configuration"}, cause=exc
            ) from exc
        except (AgentNotFoundError, AgentInactiveError) as exc:
            raise CivilDraftConfigurationError(
                params={"reason": "agent_unavailable"}, cause=exc
            ) from exc
        except LLMClientError as exc:
            raise CivilDraftUnavailableError(cause=exc) from exc
