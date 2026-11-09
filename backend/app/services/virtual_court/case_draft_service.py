"""Generate reviewable drafts from documents and a supplied draft contract."""

import asyncio
import json

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.exceptions import ToolNotRegisteredError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError

from .case_draft_validator import validate_case_draft_agent_output
from .exceptions import (
    CaseDraftConfigurationError,
    CaseDraftContextError,
    CaseDraftInvalidResponseError,
    CaseDraftTimeoutError,
    CaseDraftUnavailableError,
)


logger = get_logger(__name__)


class CaseDraftService:
    AGENT_NAME = "virtual_court_case_draft_generator"

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
                            raise CaseDraftInvalidResponseError(
                                params={"reason": "incomplete_or_tool_output", "field": "response"}
                            )
                        return validate_case_draft_agent_output(result.text, request)
                    except ToolNotRegisteredError as exc:
                        invalid = CaseDraftInvalidResponseError(
                            params={"reason": "unexpected_tool_call", "field": "response"},
                            cause=exc,
                        )
                        raw = ""
                    except CaseDraftInvalidResponseError as exc:
                        invalid = exc
                        raw = result.text
                    logger.warning(
                        "[CaseDraftV1] output rejected: attempt={}, diagnostic={}",
                        attempt + 1, invalid.params,
                    )
                    if attempt:
                        raise invalid
                    history = [
                        {"role": "user", "content": business_query},
                        {"role": "assistant", "content": raw},
                    ]
                    query = (
                        "上次输出未通过 JSON 契约校验。请核对原始材料，"
                        "只输出包含 draft 和 issues 的完整 JSON。issues 每项仅含 severity、code、message；"
                        "code 必须匹配 ^[A-Z][A-Z0-9_]{0,63}$，不要使用中文或小写字母。校验错误："
                        + json.dumps(invalid.params, ensure_ascii=False)
                    )
        except TimeoutError as exc:
            raise CaseDraftTimeoutError(
                params={"timeout": self._timeout_seconds}, cause=exc
            ) from exc
        except ContextBudgetExceeded as exc:
            raise CaseDraftContextError(
                params={"reason": "model_context_budget", "field": "materials"}, cause=exc
            ) from exc
        except ToolBuildError as exc:
            raise CaseDraftConfigurationError(
                params={"reason": "agent_tool_configuration"}, cause=exc
            ) from exc
        except (AgentNotFoundError, AgentInactiveError) as exc:
            raise CaseDraftConfigurationError(
                params={"reason": "agent_unavailable"}, cause=exc
            ) from exc
        except LLMClientError as exc:
            raise CaseDraftUnavailableError(cause=exc) from exc
