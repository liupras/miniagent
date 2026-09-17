#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stateless generation of a transcript draft from complete court material.

import asyncio
import json

from app.core.logger_config import get_logger
from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.exceptions import ToolNotRegisteredError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError

from .exceptions import (
    TranscriptConfigurationError,
    TranscriptContextError,
    TranscriptInvalidResponseError,
    TranscriptTimeoutError,
    TranscriptUnavailableError,
)
from .transcript_validator import validate_transcript_agent_output


logger = get_logger(__name__)


class TranscriptService:
    AGENT_NAME = "virtual_court_transcript_writer"

    def __init__(self, agent_factory, *, timeout_seconds=180.0):
        self._agent_factory = agent_factory
        self._timeout_seconds = timeout_seconds

    async def generate(self, request):
        """Generate and validate one transcript under a shared deadline."""

        try:
            async with asyncio.timeout(self._timeout_seconds):
                runner = await self._agent_factory.get_runner_by_name(
                    self.AGENT_NAME
                )
                business_query = self._build_agent_query(request)
                query = business_query
                history = None
                for attempt in range(2):
                    try:
                        result = await runner.execute(
                            query=query,
                            history=history,
                            preserve_context=True,
                        )
                    except ToolNotRegisteredError as exc:
                        invalid = TranscriptInvalidResponseError(
                            params={
                                "reason": "unexpected_tool_call",
                                "field": "response",
                            },
                            cause=exc,
                        )
                        logger.warning(
                            "[TranscriptV2] output rejected: state_version={}, attempt={}, diagnostic={}",
                            request.state_version,
                            attempt + 1,
                            invalid.params,
                        )
                        if attempt == 1:
                            raise invalid from exc
                        history = [
                            {"role": "user", "content": business_query},
                            {"role": "assistant", "content": ""},
                        ]
                        query = self._repair_query(invalid)
                        continue
                    if result.stop_reason != "completed":
                        raise TranscriptInvalidResponseError(
                            params={
                                "reason": "execution_not_completed",
                                "field": "response",
                            }
                        )
                    try:
                        if result.tools:
                            raise TranscriptInvalidResponseError(
                                params={
                                    "reason": "unexpected_tool_call",
                                    "field": "response",
                                }
                            )
                        response = validate_transcript_agent_output(
                            result.text,
                            request,
                        )
                        logger.info(
                            "[TranscriptV2] validated: state_version={}, attempts={}, records={}, transcript_codepoints={}",
                            request.state_version,
                            attempt + 1,
                            len(request.records),
                            len(response.transcript),
                        )
                        return response
                    except TranscriptInvalidResponseError as exc:
                        logger.warning(
                            "[TranscriptV2] output rejected: state_version={}, attempt={}, diagnostic={}",
                            request.state_version,
                            attempt + 1,
                            exc.params,
                        )
                        if attempt == 1:
                            raise
                        history = [
                            {"role": "user", "content": business_query},
                            {"role": "assistant", "content": result.text},
                        ]
                        query = self._repair_query(exc)
        except TimeoutError as exc:
            raise TranscriptTimeoutError(
                params={"timeout": self._timeout_seconds},
                cause=exc,
            ) from exc
        except ContextBudgetExceeded as exc:
            raise TranscriptContextError(
                params={"reason": "model_context_budget", "field": "records"},
                cause=exc,
            ) from exc
        except ToolBuildError as exc:
            raise TranscriptConfigurationError(
                params={"reason": "agent_tool_configuration"},
                cause=exc,
            ) from exc
        except (AgentNotFoundError, AgentInactiveError) as exc:
            raise TranscriptConfigurationError(
                params={"reason": "agent_unavailable"},
                cause=exc,
            ) from exc
        except LLMClientError as exc:
            raise TranscriptUnavailableError(cause=exc) from exc

    @staticmethod
    def _build_agent_query(request):
        data = request.model_dump(
            mode="json",
            exclude={"state_version"},
            exclude_unset=True,
        )
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _repair_query(error):
        return (
            "上次输出校验失败，请依据原始输入重新生成。错误："
            + json.dumps(error.params, ensure_ascii=False)
        )
