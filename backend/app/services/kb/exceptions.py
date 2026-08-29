#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stable application errors for knowledge-domain plugins.

from app.schemas.exceptions import InfrastructureError


class SmartRouterError(InfrastructureError):
    """Base class for expected smart-router failures."""

    error_key = "smart_router.failed"


class SmartRouterConfigurationError(SmartRouterError):
    """The selected routing strategy is not configured correctly."""

    error_key = "smart_router.configuration_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SmartRouterQueryError(SmartRouterError):
    """An unexpected routing or retrieval dependency failed."""

    error_key = "smart_router.query_failed"

    def __init__(
        self,
        router_config_id: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.router_config_id = router_config_id
        super().__init__(
            f"Smart Router query failed for config '{router_config_id}'",
            params={"router_config_id": router_config_id},
            cause=cause,
        )


class RetrievalError(InfrastructureError):
    """Base class for knowledge-base retrieval pipeline failures."""

    error_key = "retrieval.failed"


class RetrievalConfidenceMissingError(RetrievalError):
    """The retrieval pipeline completed without producing confidence data."""

    error_key = "kb.no_confidence"

    def __init__(self, kb_id: int) -> None:
        self.kb_id = kb_id
        super().__init__(
            f"Retrieval pipeline returned no confidence for KB '{kb_id}'",
            params={"kb_id": kb_id},
        )


class DocumentOperationError(InfrastructureError):
    """Base class for failures during document lifecycle operations."""

    error_key = "document.operation_failed"

    def __init__(
        self,
        doc_id: int,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.doc_id = doc_id
        super().__init__(
            f"Document operation failed for document '{doc_id}'",
            params={"doc_id": doc_id},
            cause=cause,
        )


class DocumentIndexingError(DocumentOperationError):
    error_key = "document.indexing_failed"


class DocumentUpdateError(DocumentOperationError):
    error_key = "document.update_failed"


class DocumentDeletionError(DocumentOperationError):
    error_key = "document.deletion_failed"


class DomainPluginError(InfrastructureError):
    """Base class for domain-plugin startup failures."""

    error_key = "domain_plugin.error"


class NoDomainPluginsConfiguredError(DomainPluginError):
    """No domain plugin configuration exists in the database."""

    error_key = "domain_plugin.none_configured"

    def __init__(self) -> None:
        super().__init__("No domain plugins are configured")


class DomainPluginRegistrationError(DomainPluginError):
    """A required domain plugin could not be imported or constructed."""

    error_key = "domain_plugin.registration_failed"

    def __init__(
        self,
        domain: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.domain = domain
        super().__init__(
            f"Failed to register required domain plugin '{domain}'",
            params={"domain": domain},
            cause=cause,
        )
