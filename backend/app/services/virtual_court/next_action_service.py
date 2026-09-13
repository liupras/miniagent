"""Stateless, phase-specific courtroom flow decisions."""

import asyncio
import json

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.virtual_court import JudgePhase

from .exceptions import (
    JudgeConfigurationError,
    JudgeContextError,
    JudgeInvalidResponseError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)
from .response_validator import validate_next_action_agent_output


logger = get_logger(__name__)


class NextActionService:
    AGENT_BY_PHASE = {
        JudgePhase.INVESTIGATION: 'virtual_court_investigation_judge',
        JudgePhase.DEBATE: 'virtual_court_debate_judge',
    }

    def __init__(self, agent_factory, *, timeout_seconds=120.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def decide(self, request):
        """Return one request-authorized action under a shared deadline."""

        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(
                    self.AGENT_BY_PHASE[request.phase]
                )
                business_query = self._build_agent_query(request)
                query = business_query
                history = None
                for attempt in range(2):
                    result = await runner.execute(
                        query=query,
                        history=history,
                        preserve_context=True,
                    )
                    if result.stop_reason != 'completed':
                        raise JudgeInvalidResponseError(
                            params={'reason': 'tool_step_limit', 'field': 'response'}
                        )
                    try:
                        response = validate_next_action_agent_output(
                            result.text,
                            request,
                        )
                        logger.info(
                            '[NextActionV2] validated: phase={}, state_version={}, decision={}, attempts={}, tool_calls={}',
                            request.phase,
                            request.state_version,
                            response.decision,
                            attempt + 1,
                            len(result.tools),
                        )
                        return response
                    except JudgeInvalidResponseError as exc:
                        logger.warning(
                            '[NextActionV2] output rejected: phase={}, state_version={}, attempt={}, diagnostic={}',
                            request.phase,
                            request.state_version,
                            attempt + 1,
                            exc.params,
                        )
                        if attempt == 1:
                            raise
                        history = [
                            {'role': 'user', 'content': business_query},
                            {'role': 'assistant', 'content': result.text},
                        ]
                        query = (
                            '上次输出校验失败，请依据原始输入重新生成。错误：'
                            + json.dumps(exc.params, ensure_ascii=False)
                        )
        except TimeoutError as exc:
            raise JudgeTimeoutError(
                params={'timeout': self._timeout_seconds}, cause=exc
            ) from exc
        except ContextBudgetExceeded as exc:
            raise JudgeContextError(
                params={'reason': 'model_context_budget', 'field': 'records'},
                cause=exc,
            ) from exc
        except ToolBuildError as exc:
            raise JudgeConfigurationError(
                params={'reason': 'agent_tool_configuration'}, cause=exc
            ) from exc
        except (AgentNotFoundError, AgentInactiveError) as exc:
            raise JudgeConfigurationError(
                params={'reason': 'agent_unavailable'}, cause=exc
            ) from exc
        except LLMClientError as exc:
            raise JudgeUnavailableError(cause=exc) from exc

    @staticmethod
    def _build_agent_query(request):
        data = request.model_dump(
            mode='json',
            exclude={'state_version'},
            exclude_unset=True,
        )
        return json.dumps(data, ensure_ascii=False)
