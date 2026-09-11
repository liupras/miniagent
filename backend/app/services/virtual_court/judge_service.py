"""Stateless JudgeAPI V2 execution with at most one bounded output repair."""
import asyncio
import json
from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.virtual_court import JudgePhase, JudgeDecision
from .exceptions import JudgeConfigurationError, JudgeTimeoutError, JudgeUnavailableError, JudgeInvalidResponseError
from .response_validator import validate_judge_agent_output
from .exceptions import JudgeContextError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from .law_policy import (handoff, check_law_observation,
                         has_law_evidence, LawRetrievalUnavailable)

logger = get_logger(__name__)

class JudgeService:
    AGENT_BY_PHASE = {
        JudgePhase.INVESTIGATION:'virtual_court_investigation_judge',
        JudgePhase.DEBATE:'virtual_court_debate_judge',
    }

    def __init__(self, agent_factory, *, timeout_seconds=120.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def decide(self, request):
        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(self.AGENT_BY_PHASE[request.phase])
                query = self._build_agent_query(request)
                for attempt in range(2):
                    result = await runner.execute(query=query, preserve_context=True,
                                                  tool_observer=check_law_observation)
                    if result.stop_reason != 'completed':
                        raise JudgeInvalidResponseError(params={'reason':'tool_step_limit', 'field':'response'})
                    raw = result.text
                    try:
                        response = validate_judge_agent_output(raw, request)
                        if response.decision == JudgeDecision.EXPLAIN_LAW and not has_law_evidence(result.tools):
                            return validate_judge_agent_output(handoff('法律解释缺少本次有效检索依据。'), request)
                        logger.info('[JudgeV2] validated: phase={}, state_version={}, decision={}, attempts={}',
                                    request.phase, request.state_version, response.decision, attempt + 1)
                        return response
                    except JudgeInvalidResponseError as exc:
                        logger.warning('[JudgeV2] output rejected: phase={}, state_version={}, attempt={}, diagnostic={}',
                                       request.phase, request.state_version, attempt + 1, exc.params)
                        if attempt == 1: raise
                        query = self._build_agent_query(request) + '\n上次输出校验失败，请重新生成。错误：' + json.dumps(exc.params, ensure_ascii=False)
        except TimeoutError as exc:
            raise JudgeTimeoutError(params={'timeout':self._timeout_seconds}, cause=exc) from exc
        except ContextBudgetExceeded as exc:
            raise JudgeContextError(params={'reason':'model_context_budget', 'field':'records'}, cause=exc) from exc
        except LawRetrievalUnavailable as exc:
            return validate_judge_agent_output(handoff(str(exc)), request)
        except ToolBuildError:
            return validate_judge_agent_output(handoff('法律检索工具加载失败，请人工处理。'), request)
        except (AgentNotFoundError, AgentInactiveError) as exc:
            raise JudgeConfigurationError(params={'reason':'agent_unavailable'}, cause=exc) from exc
        except LLMClientError as exc:
            raise JudgeUnavailableError(cause=exc) from exc

    @staticmethod
    def _build_agent_query(request):
        data = request.model_dump(mode='json', exclude={'state_version'}, exclude_unset=True)
        return json.dumps(data, ensure_ascii=False)
