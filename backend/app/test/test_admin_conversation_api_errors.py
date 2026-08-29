import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.admin.conversation as conversation_api
from app.api.exception_handlers import register_global_exception_handlers
from app.runtime.conversation.service_conversation import (
    ConversationService,
    SessionNotFoundError,
)


class _MissingSessionDatabase:
    async def get_session_by_id(self, session_id):
        return None


def test_conversation_service_raises_domain_error_for_missing_session():
    service = ConversationService(_MissingSessionDatabase())

    with pytest.raises(SessionNotFoundError) as caught:
        asyncio.run(service.get_session("11"))

    assert caught.value.i18n_key() == "session.not_found"


class _MissingSessionService:
    async def get_session(self, session_id):
        raise SessionNotFoundError(session_id)


def test_missing_session_is_mapped_by_global_exception_handler():
    app = FastAPI()
    register_global_exception_handlers(app)
    app.include_router(conversation_api.router)
    app.dependency_overrides[conversation_api._get_service] = (
        lambda: _MissingSessionService()
    )
    app.dependency_overrides[conversation_api._list] = lambda: 1
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/sessions/11")

    assert response.status_code == 404
    assert response.json()["code"] == 404
    assert "Chat session not found" not in response.text
