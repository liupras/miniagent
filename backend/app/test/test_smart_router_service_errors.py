import asyncio
from types import SimpleNamespace

import pytest

from app.schemas.exceptions import BaseDomainError, NotFoundError
from app.services.kb.exceptions import (
    SmartRouterConfigurationError,
    SmartRouterQueryError,
)
from app.services.kb.service_smart_router import KBSmartRouterService
from app.services.kb.smart_router import RouterConfig, SmartRouter


class _Factory:
    def __init__(self, *, router=None, error=None):
        self.router = router
        self.error = error

    async def get_router(self, router_config_id):
        if self.error:
            raise self.error
        return self.router


class _FailingRouter:
    def __init__(self, error):
        self.error = error

    async def query(self, **kwargs):
        raise self.error


def _service(factory):
    service = object.__new__(KBSmartRouterService)
    service._factory = factory
    return service


def _query(service):
    return asyncio.run(
        service.query(
            router_config_id="router-1",
            query="question",
            kb_ids=[1],
        )
    )


def test_smart_router_service_preserves_domain_error():
    source_error = NotFoundError("KnowledgeBase", 1)
    service = _service(_Factory(router=_FailingRouter(source_error)))

    with pytest.raises(BaseDomainError) as caught:
        _query(service)

    assert caught.value is source_error


def test_smart_router_service_wraps_unexpected_failure_once():
    source_error = RuntimeError("private vector database detail")
    service = _service(_Factory(router=_FailingRouter(source_error)))

    with pytest.raises(SmartRouterQueryError) as caught:
        _query(service)

    assert caught.value.cause is source_error
    assert "private vector database detail" not in caught.value.to_detail()


def test_embedding_selection_raises_configuration_domain_error():
    router = object.__new__(SmartRouter)
    router.router_config = RouterConfig(
        selection_strategy="embedding",
        extra_config={},
    )

    with pytest.raises(SmartRouterConfigurationError):
        asyncio.run(router._select_kbs_by_embedding("question", [1]))


def test_all_kb_failures_propagate_instead_of_causing_attribute_error():
    class _Retrieval:
        async def query(self, **kwargs):
            raise NotFoundError("KnowledgeBase", kwargs["kb_id"])

    router = object.__new__(SmartRouter)
    router.kb_services = _Retrieval()
    router.router_config = RouterConfig(selection_strategy="keyword")

    async def select_all(query, kb_ids):
        return kb_ids

    router._select_kbs = select_all

    with pytest.raises(NotFoundError):
        asyncio.run(router.query("question", [1, 2]))
