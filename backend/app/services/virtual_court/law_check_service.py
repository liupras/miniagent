"""Stateless legal-question checking for one committed party speech."""

import asyncio
import json

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.virtual_court import JudgeLawCheckDecision

from .exceptions import (
    JudgeConfigurationError,
    JudgeContextError,
    JudgeInvalidResponseError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)
from .law_policy import (
    LawRetrievalUnavailable,
    check_law_observation,
    has_law_evidence,
    is_definitely_no_action,
    law_check_handoff,
    law_check_no_action,
)
from .response_validator import validate_law_check_agent_output


logger = get_logger(__name__)


class LawCheckService:
    AGENT_NAME = 'virtual_court_law_check_judge'

    def __init__(self, agent_factory, *, timeout_seconds=120.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def check(self, request):
        """Check only the request's latest speech under one shared deadline."""

        if is_definitely_no_action(request.text):
            logger.info(
                '[LawCheckV2] definite statement: state_version={}, decision=NO_ACTION, tool_calls=0',
                request.state_version,
            )
            return validate_law_check_agent_output(law_check_no_action(), request)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(self.AGENT_NAME)
                business_query = self._build_agent_query(request)
                query = business_query
                history = None
                for attempt in range(2):
                    result = await runner.execute(
                        query=query,
                        history=history,
                        preserve_context=True,
                        tool_observer=check_law_observation,
                    )
                    if result.stop_reason != 'completed':
                        raise JudgeInvalidResponseError(
                            params={'reason': 'tool_step_limit', 'field': 'response'}
                        )
                    try:
                        response = validate_law_check_agent_output(result.text, request)
                        if (
                            response.decision == JudgeLawCheckDecision.NO_ACTION
                            and result.tools
                        ):
                            raise JudgeInvalidResponseError(
                                params={
                                    'reason': 'no_action_with_tool_call',
                                    'field': 'decision',
                                }
                            )
                        if (
                            response.decision == JudgeLawCheckDecision.EXPLAIN_LAW
                            and not has_law_evidence(result.tools)
                        ):
                            return self._handoff(
                                request,
                                '法律解释缺少本次有效检索依据。',
                            )
                        logger.info(
                            '[LawCheckV2] validated: state_version={}, decision={}, attempts={}, tool_calls={}',
                            request.state_version,
                            response.decision,
                            attempt + 1,
                            len(result.tools),
                        )
                        return response
                    except JudgeInvalidResponseError as exc:
                        logger.warning(
                            '[LawCheckV2] output rejected: state_version={}, attempt={}, diagnostic={}',
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
                params={'reason': 'model_context_budget', 'field': 'context'},
                cause=exc,
            ) from exc
        except LawRetrievalUnavailable:
            return self._handoff(
                request,
                '法律检索失败或未返回可用依据，请人工核对。',
            )
        except ToolBuildError:
            return self._handoff(
                request,
                '法律检索工具加载失败，请人工处理。',
            )
        except (AgentNotFoundError, AgentInactiveError) as exc:
            raise JudgeConfigurationError(
                params={'reason': 'agent_unavailable'}, cause=exc
            ) from exc
        except LLMClientError as exc:
            raise JudgeUnavailableError(cause=exc) from exc

    @staticmethod
    def _build_agent_query(request):
        data = {
            'latest_speech': {
                'role': request.role.value,
                'text': request.text,
            },
            'reference_context': request.context,
        }
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _handoff(request, reason):
        return validate_law_check_agent_output(law_check_handoff(reason), request)
