#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio
from types import SimpleNamespace

import pytest

from app.runtime.conversation.service_conversation import ConversationService
from app.runtime.conversation.title_generator import TitleGenerationError


class _ChatDatabase:
    def __init__(self, existing_title=None) -> None:
        self.existing_title = existing_title
        self.saved = []

    async def get_session_by_id(self, session_id):
        return SimpleNamespace(title=self.existing_title)

    async def save_message(self, **kwargs):
        self.saved.append(kwargs)
        return 11


class _TitleGenerator:
    def __init__(self, result="generated", error=None) -> None:
        self.result = result
        self.error = error
        self.call_count = 0
        self.config = SimpleNamespace(default_title="default title")

    def generate(self, content):
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.result


def _save(service, *, role="user", session_id=7):
    return asyncio.run(
        service.save_message(
            user_id="1",
            agent_id=2,
            session_id=session_id,
            role=role,
            content="question",
        )
    )


def test_service_generates_title_for_untitled_session():
    database = _ChatDatabase(existing_title=None)
    generator = _TitleGenerator()
    service = ConversationService(database, generator)

    assert _save(service) == 11
    assert generator.call_count == 1
    assert database.saved[0]["session_title"] == "generated"


def test_service_does_not_generate_title_for_titled_session():
    database = _ChatDatabase(existing_title="existing")
    generator = _TitleGenerator()
    service = ConversationService(database, generator)

    _save(service)

    assert generator.call_count == 0
    assert database.saved[0]["session_title"] is None


def test_service_does_not_generate_title_for_assistant_message():
    database = _ChatDatabase(existing_title=None)
    generator = _TitleGenerator()
    service = ConversationService(database, generator)

    _save(service, role="assistant")

    assert generator.call_count == 0
    assert database.saved[0]["session_title"] is None


def test_known_title_generation_failure_uses_configured_default():
    database = _ChatDatabase(existing_title=None)
    generator = _TitleGenerator(
        error=TitleGenerationError(cause=RuntimeError("provider unavailable")),
    )
    service = ConversationService(database, generator)

    _save(service)

    assert database.saved[0]["session_title"] == "default title"


def test_unexpected_title_generation_failure_is_not_swallowed():
    database = _ChatDatabase(existing_title=None)
    generator = _TitleGenerator(error=RuntimeError("unexpected failure"))
    service = ConversationService(database, generator)

    with pytest.raises(RuntimeError, match="unexpected failure"):
        _save(service)

    assert database.saved == []


def test_new_session_generates_title_without_repository_lookup():
    class _NewSessionDatabase(_ChatDatabase):
        async def get_session_by_id(self, session_id):
            raise AssertionError("new session must not be queried")

    database = _NewSessionDatabase()
    generator = _TitleGenerator()
    service = ConversationService(database, generator)

    _save(service, session_id=None)

    assert database.saved[0]["session_title"] == "generated"
