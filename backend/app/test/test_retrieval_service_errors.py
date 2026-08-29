import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.user.kb as kb_api
from app.api.exception_handlers import register_global_exception_handlers
from app.schemas.exceptions import InfrastructureError
from app.services.kb.exceptions import RetrievalConfidenceMissingError
from app.services.kb.service_retrieval import KBRetrievalService


class _Pipeline:
    async def run(self, **kwargs):
        return SimpleNamespace(confidence=None)


class _PipelineCache:
    async def get_or_build(self, kb_id):
        return _Pipeline()


def test_missing_retrieval_confidence_raises_domain_error():
    service = object.__new__(KBRetrievalService)
    service._pipeline_cache = _PipelineCache()

    with pytest.raises(RetrievalConfidenceMissingError) as caught:
        asyncio.run(service.query(kb_id=1, query="question"))

    assert isinstance(caught.value, InfrastructureError)
    assert caught.value.kb_id == 1
    assert caught.value.i18n_key() == "kb.no_confidence"


class _KBService:
    async def kb_exists(self, kb_id):
        return True


class _FailingRetrievalService:
    async def query(self, **kwargs):
        raise RetrievalConfidenceMissingError(kwargs["kb_id"])


def test_missing_retrieval_confidence_is_mapped_to_safe_http_503():
    app = FastAPI()
    register_global_exception_handlers(app)
    app.include_router(kb_api.router)
    app.dependency_overrides[kb_api.get_container] = lambda: SimpleNamespace(
        kb_service=_KBService()
    )
    app.dependency_overrides[kb_api.get_service_retrieval] = (
        lambda: _FailingRetrievalService()
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/1/query", json={"query": "question"})

    assert response.status_code == 503
    assert response.json()["code"] == 503
    assert "RuntimeError" not in response.text
