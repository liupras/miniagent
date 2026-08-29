import pytest

from app.infra.db.exceptions import DatabaseInitializationError
from app.retrieval.embedding_inputs import EmbeddingInputTooLongError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.conversation.service_conversation import (
    MessageNotFoundError,
    SessionNotFoundError,
)
from app.runtime.llm.models import LLMClientError
from app.schemas.exceptions import (
    BaseDomainError,
    InfrastructureError,
    PermissionDeniedError,
    ToolInactiveError,
)
from app.services.integration_auth import (
    IntegrationNotConfiguredError,
    InvalidIntegrationCredentialsError,
)
from app.services.kb.exceptions import (
    DomainPluginRegistrationError,
    DocumentDeletionError,
    DocumentIndexingError,
    DocumentUpdateError,
    NoDomainPluginsConfiguredError,
    RetrievalConfidenceMissingError,
    SmartRouterConfigurationError,
    SmartRouterQueryError,
)
from app.services.admin.system_status import DatabaseInfoUnavailableError
from app.services.sql_agent.exceptions import (
    SQLTableImportError,
    SQLTableNotFoundError,
    SQLTableOperationError,
    SQLUnsupportedFileTypeError,
)
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeInvalidResponseError,
    JudgeServiceError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)
from app.services.workplace_agent import (
    AgentAccessDeniedError,
    AgentSelectionError,
    AgentSessionNotFoundError,
    SessionAgentMismatchError,
    SessionTitleInvalidError,
)


@pytest.mark.parametrize(
    ("error", "expected_key"),
    [
        (ToolBuildError("tool failed"), "tool.build_failed"),
        (LLMClientError("provider failed"), "llm.client_error"),
        (
            EmbeddingInputTooLongError("input is too long"),
            "embedding.input_too_long",
        ),
        (JudgeServiceError("judge failed"), "judge.failed"),
        (
            JudgeConfigurationError("bad configuration"),
            "judge.configuration_error",
        ),
        (JudgeUnavailableError("provider unavailable"), "judge.unavailable"),
        (JudgeTimeoutError("timed out"), "judge.timeout"),
        (JudgeInvalidResponseError("bad output"), "judge.invalid_response"),
        (DatabaseInitializationError(), "database.initialization_failed"),
        (
            DomainPluginRegistrationError("law_cn"),
            "domain_plugin.registration_failed",
        ),
        (
            NoDomainPluginsConfiguredError(),
            "domain_plugin.none_configured",
        ),
        (
            SQLTableNotFoundError("main", "orders"),
            "sqltable.not_found",
        ),
        (
            SQLUnsupportedFileTypeError("orders.pdf", ".csv"),
            "sql_agent.unsupported_file_extension",
        ),
        (SQLTableImportError("orders.csv"), "sql_agent.import_failed"),
        (
            SQLTableOperationError("list_tables"),
            "sql_agent.operation_failed",
        ),
        (AgentSelectionError(), "agent.input_invalid"),
        (AgentAccessDeniedError(1, 2), "agent.unauthorized"),
        (AgentSessionNotFoundError(3), "agent.session_not_found"),
        (SessionAgentMismatchError(3, 2), "agent.session_not_belong"),
        (SessionTitleInvalidError(), "agent.title_not_empty"),
        (SessionNotFoundError(3), "session.not_found"),
        (MessageNotFoundError(4), "message.not_found"),
        (DatabaseInfoUnavailableError(), "operations.database_info_failed"),
        (IntegrationNotConfiguredError(), "integration.not_configured"),
        (
            InvalidIntegrationCredentialsError(),
            "integration.authentication_failed",
        ),
        (
            SmartRouterConfigurationError("missing embedding provider"),
            "smart_router.configuration_error",
        ),
        (SmartRouterQueryError("router-1"), "smart_router.query_failed"),
        (RetrievalConfidenceMissingError(1), "kb.no_confidence"),
        (ToolInactiveError("sql_agent"), "tool.inactive"),
        (DocumentIndexingError(1), "document.indexing_failed"),
        (DocumentUpdateError(1), "document.update_failed"),
        (DocumentDeletionError(1), "document.deletion_failed"),
    ],
)
def test_custom_errors_inherit_base_domain_error(error, expected_key):
    assert isinstance(error, BaseDomainError)
    assert error.i18n_key() == expected_key


def test_infrastructure_errors_share_infrastructure_base():
    assert isinstance(ToolBuildError("failed"), InfrastructureError)
    assert isinstance(LLMClientError("failed"), InfrastructureError)
    assert isinstance(EmbeddingInputTooLongError("failed"), InfrastructureError)


def test_agent_access_denied_uses_permission_denied_base():
    assert isinstance(AgentAccessDeniedError(1, 2), PermissionDeniedError)
