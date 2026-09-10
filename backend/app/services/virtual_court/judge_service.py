#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Application service for VirtualCourt sole-judge decisions.

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.virtual_court import (
    JudgeDecisionRequest,
    JudgeDecisionResponse,
    JudgeStage,
    judge_agent_output_json_schema,
)

from .exceptions import (
    JudgeConfigurationError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)
from .response_validator import validate_judge_agent_output

if TYPE_CHECKING:
    from app.runtime.agent.agent_factory import AgentFactory


logger = get_logger(__name__)


class JudgeService:
    """Run the dedicated judge agent and validate its proposed decision."""

    AGENT_BY_STAGE = {
        JudgeStage.COURT_INVESTIGATION: "virtual_court_investigation_judge",
        JudgeStage.COURT_DEBATE: "virtual_court_debate_judge",
    }
    REQUIRED_TOOL_NAME = "intellectual_property_law_search"

    def __init__(
        self,
        agent_factory: "AgentFactory",
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def decide(
        self,
        request: JudgeDecisionRequest,
    ) -> JudgeDecisionResponse:
        """Return one validated, request-bound judge decision.

        The call is deliberately stateless: no conversation identity or
        history is supplied to ``AgentRunner``.  ``state_version`` is also
        excluded from the model prompt and is injected only after validation.
        """

        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(
                    self.AGENT_BY_STAGE[request.current_stage]
                )
                if self.REQUIRED_TOOL_NAME not in runner.tool_names:
                    raise JudgeConfigurationError(
                        params={
                            "reason": "missing_required_tool",
                            "tool_name": self.REQUIRED_TOOL_NAME,
                        }
                    )
                raw_output = await runner.invoke(query=self._build_agent_query(request))
                response = validate_judge_agent_output(raw_output, request)
        except TimeoutError as exc:
            raise JudgeTimeoutError(
                params={"timeout": self._timeout_seconds},
                cause=exc,
            ) from exc
        except (AgentNotFoundError, AgentInactiveError, ToolBuildError) as exc:
            raise JudgeConfigurationError(
                params={"reason": "agent_unavailable"},
                cause=exc,
            ) from exc
        except LLMClientError as exc:
            raise JudgeUnavailableError(
                cause=exc,
            ) from exc

        logger.info(
            "[JudgeService] decision validated: state_version={}, action={}, "
            "confidence={}",
            response.state_version,
            response.action.type,
            response.confidence,
        )
        return response

    @staticmethod
    def _build_agent_query(request: JudgeDecisionRequest) -> str:
        reasoning_input = request.model_dump(
            mode="json",
            exclude={"state_version"},
        )
        schema = judge_agent_output_json_schema()
        # Business behavior belongs to the selected agent's system prompt.
        # Keep the request payload and generated wire contract as the only input.
        return (
            "庭审输入：\n"
            f"{json.dumps(reasoning_input, ensure_ascii=False, indent=2)}\n\n"
            "输出 JSON Schema：\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
