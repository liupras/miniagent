#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stable application errors for knowledge-domain plugins.

from app.schemas.exceptions import InfrastructureError


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
