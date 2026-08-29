#!/usr/bin/python
# -*- coding:utf-8 -*-
# @description: Authenticated workplace Agent and conversation orchestration.

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.exceptions import (
    BaseDomainError,
    NotFoundError,
    PermissionDeniedError,
)

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer


class AgentSelectionError(BaseDomainError):
    error_key = "agent.input_invalid"

    def __init__(self) -> None:
        super().__init__(message="agent_id or agent_name is required")


class AgentAccessDeniedError(PermissionDeniedError):
    error_key = "agent.unauthorized"

    def __init__(self, user_id: int, agent_id: int) -> None:
        self.user_id = user_id
        self.agent_id = agent_id
        super().__init__(
            f"User '{user_id}' cannot access agent '{agent_id}'",
        )


class SessionAgentMismatchError(BaseDomainError):
    error_key = "agent.session_not_belong"

    def __init__(self, session_id: int, agent_id: int) -> None:
        self.session_id = session_id
        self.agent_id = agent_id
        super().__init__(
            message=f"Session '{session_id}' does not belong to agent '{agent_id}'",
        )


class AgentSessionNotFoundError(NotFoundError):
    error_key = "agent.session_not_found"

    def __init__(self, session_id: int) -> None:
        super().__init__("Session", session_id)


class SessionTitleInvalidError(BaseDomainError):
    error_key = "agent.title_not_empty"

    def __init__(self) -> None:
        super().__init__(message="Session title cannot be empty")


class WorkplaceAgentService:
    """Coordinate authenticated Agent access and user-owned conversations."""

    def __init__(self, container: ServiceContainer) -> None:
        self._agent_factory = container.agent_factory
        self._conversation = container.conversation_service
        self._user_agent_relations = container.user_agent_relation_db

    async def list_available_agents(self, user_id: int):
        return await self._user_agent_relations.get_user_agents(user_id)

    async def _resolve_runner(
        self,
        user_id: int,
        agent_id: int | None,
        agent_name: str | None,
    ):
        if agent_id is not None:
            runner = await self._agent_factory.get_runner(agent_id)
        elif agent_name:
            runner = await self._agent_factory.get_runner_by_name(agent_name)
        else:
            raise AgentSelectionError()

        if not await self._user_agent_relations.user_has_agent(
            user_id,
            runner.agent_id,
        ):
            raise AgentAccessDeniedError(user_id, runner.agent_id)
        return runner

    async def _resolve_session(
        self,
        user_id: int,
        agent_id: int,
        session_id: int | None,
    ):
        if session_id is None:
            return await self._conversation.create_user_session(user_id, agent_id)

        session = await self._conversation.get_user_session(session_id, user_id)
        if session is None:
            raise AgentSessionNotFoundError(session_id)
        if session.agent_id != agent_id:
            raise SessionAgentMismatchError(session_id, agent_id)
        return session

    async def prepare_call(
        self,
        *,
        user_id: int,
        agent_id: int | None,
        agent_name: str | None,
        session_id: int | None,
    ):
        runner = await self._resolve_runner(user_id, agent_id, agent_name)
        session = await self._resolve_session(user_id, runner.agent_id, session_id)
        return runner, session

    async def invoke(
        self,
        *,
        user_id: int,
        agent_id: int | None,
        agent_name: str | None,
        session_id: int | None,
        query: str,
        history,
    ) -> tuple[str, int]:
        runner, session = await self.prepare_call(
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=session_id,
        )
        answer = await runner.invoke(
            query=query,
            history=history or None,
            user_id=str(user_id),
            session_id=session.id,
        )
        return answer, session.id

    async def list_user_sessions(self, **kwargs):
        return await self._conversation.list_user_sessions(**kwargs)

    async def list_user_messages(
        self,
        *,
        session_id: int,
        user_id: int,
        page: int,
        page_size: int,
    ):
        if await self._conversation.get_user_session(session_id, user_id) is None:
            raise AgentSessionNotFoundError(session_id)
        return await self._conversation.list_user_messages(
            session_id=session_id,
            user_id=user_id,
            page=page,
            page_size=page_size,
        )

    async def rename_user_session(
        self,
        session_id: int,
        user_id: int,
        title: str,
    ) -> str:
        normalized_title = title.strip()
        if not normalized_title:
            raise SessionTitleInvalidError()
        renamed = await self._conversation.rename_user_session(
            session_id,
            user_id,
            normalized_title,
        )
        if not renamed:
            raise AgentSessionNotFoundError(session_id)
        return normalized_title

    async def delete_user_session(self, session_id: int, user_id: int) -> None:
        if not await self._conversation.delete_user_session(session_id, user_id):
            raise AgentSessionNotFoundError(session_id)
