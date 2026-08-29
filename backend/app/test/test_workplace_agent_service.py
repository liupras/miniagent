import asyncio
from types import SimpleNamespace

import pytest

from app.schemas.exceptions import PermissionDeniedError
from app.services.workplace_agent import (
    AgentAccessDeniedError,
    AgentSelectionError,
    AgentSessionNotFoundError,
    SessionAgentMismatchError,
    SessionTitleInvalidError,
    WorkplaceAgentService,
)


class _Runner:
    agent_id = 7
    agent_name = "test-agent"

    def __init__(self):
        self.invoke_args = None

    async def invoke(self, **kwargs):
        self.invoke_args = kwargs
        return "answer"


class _Factory:
    def __init__(self, runner):
        self.runner = runner

    async def get_runner(self, agent_id):
        return self.runner

    async def get_runner_by_name(self, agent_name):
        return self.runner


class _Relations:
    def __init__(self, allowed=True):
        self.allowed = allowed

    async def user_has_agent(self, user_id, agent_id):
        return self.allowed

    async def get_user_agents(self, user_id):
        return [SimpleNamespace(id=7)]


class _Conversation:
    def __init__(self, session=None, renamed=True, deleted=True):
        self.session = session
        self.renamed = renamed
        self.deleted = deleted
        self.renamed_title = None

    async def create_user_session(self, user_id, agent_id):
        return SimpleNamespace(id=11, agent_id=agent_id)

    async def get_user_session(self, session_id, user_id):
        return self.session

    async def list_user_messages(self, **kwargs):
        return 0, []

    async def rename_user_session(self, session_id, user_id, title):
        self.renamed_title = title
        return self.renamed

    async def delete_user_session(self, session_id, user_id):
        return self.deleted


def _service(*, allowed=True, session=None, renamed=True, deleted=True):
    runner = _Runner()
    conversation = _Conversation(session, renamed, deleted)
    container = SimpleNamespace(
        agent_factory=_Factory(runner),
        conversation_service=conversation,
        user_agent_relation_db=_Relations(allowed),
    )
    return WorkplaceAgentService(container), runner, conversation


def test_prepare_call_requires_an_agent_selector():
    service, _, _ = _service()

    with pytest.raises(AgentSelectionError):
        asyncio.run(
            service.prepare_call(
                user_id=1,
                agent_id=None,
                agent_name=None,
                session_id=None,
            )
        )


def test_prepare_call_rejects_unassigned_agent():
    service, _, _ = _service(allowed=False)

    with pytest.raises(AgentAccessDeniedError) as caught:
        asyncio.run(
            service.prepare_call(
                user_id=1,
                agent_id=7,
                agent_name=None,
                session_id=None,
            )
        )

    assert isinstance(caught.value, PermissionDeniedError)


def test_prepare_call_validates_existing_session_owner_and_agent():
    service, _, _ = _service(session=None)
    with pytest.raises(AgentSessionNotFoundError):
        asyncio.run(
            service.prepare_call(
                user_id=1, agent_id=7, agent_name=None, session_id=11
            )
        )

    service, _, _ = _service(session=SimpleNamespace(id=11, agent_id=8))
    with pytest.raises(SessionAgentMismatchError):
        asyncio.run(
            service.prepare_call(
                user_id=1, agent_id=7, agent_name=None, session_id=11
            )
        )


def test_invoke_creates_session_and_forwards_authenticated_identity():
    service, runner, _ = _service()

    answer, session_id = asyncio.run(
        service.invoke(
            user_id=3,
            agent_id=7,
            agent_name=None,
            session_id=None,
            query="hello",
            history=[],
        )
    )

    assert (answer, session_id) == ("answer", 11)
    assert runner.invoke_args == {
        "query": "hello",
        "history": None,
        "user_id": "3",
        "session_id": 11,
    }


def test_rename_normalizes_title_and_rejects_invalid_or_missing_session():
    service, _, conversation = _service()
    assert asyncio.run(service.rename_user_session(11, 1, "  title  ")) == "title"
    assert conversation.renamed_title == "title"

    with pytest.raises(SessionTitleInvalidError):
        asyncio.run(service.rename_user_session(11, 1, "   "))

    service, _, _ = _service(renamed=False)
    with pytest.raises(AgentSessionNotFoundError):
        asyncio.run(service.rename_user_session(11, 1, "title"))


def test_delete_missing_session_raises_domain_error():
    service, _, _ = _service(deleted=False)

    with pytest.raises(AgentSessionNotFoundError):
        asyncio.run(service.delete_user_session(11, 1))
