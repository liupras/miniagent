import asyncio
from types import SimpleNamespace

import pytest

import app.core.service_container as container_module
from app.core.service_container import ServiceContainer
from app.schemas.exceptions import BaseDomainError
from app.services.kb.domain_plugin import DomainPlugin
from app.services.kb.domain_registry import DomainRegistry
from app.services.kb.exceptions import (
    DomainPluginRegistrationError,
    NoDomainPluginsConfiguredError,
)


class _DomainDatabase:
    def __init__(self, domains):
        self.domains = domains

    async def get_all_domains(self):
        return self.domains


class _Processor:
    pass


class _Plugin(DomainPlugin):
    def __init__(self, processor):
        self._processor = processor

    @property
    def processor(self):
        return self._processor

    def parse_metadata(self, raw: dict) -> dict:
        return raw


def _container(domains):
    container = object.__new__(ServiceContainer)
    container.domain_db = _DomainDatabase(domains)
    container.domain_registry = DomainRegistry()
    return container


def _domain(name: str, processor="processor", plugin="plugin"):
    return SimpleNamespace(
        name=name,
        processor_class=processor,
        plugin_class=plugin,
    )


def test_all_configured_plugins_are_registered(monkeypatch):
    classes = {"processor": _Processor, "plugin": _Plugin}
    monkeypatch.setattr(container_module, "import_class", classes.__getitem__)
    container = _container([_domain("general"), _domain("law_cn")])

    asyncio.run(container.init_plugins())

    assert isinstance(container.domain_registry.get("general"), _Plugin)
    assert isinstance(container.domain_registry.get("law_cn"), _Plugin)


def test_missing_domain_configuration_aborts_startup():
    container = _container([])

    with pytest.raises(NoDomainPluginsConfiguredError):
        asyncio.run(container.init_plugins())


def test_plugin_import_failure_is_converted_and_aborts_startup(monkeypatch):
    def fail_import(_path):
        raise ImportError("module is missing")

    monkeypatch.setattr(container_module, "import_class", fail_import)
    container = _container([_domain("law_cn")])

    with pytest.raises(DomainPluginRegistrationError) as captured:
        asyncio.run(container.init_plugins())

    assert isinstance(captured.value, BaseDomainError)
    assert captured.value.domain == "law_cn"
    assert isinstance(captured.value.__cause__, ImportError)
    assert container.domain_registry.get("law_cn") is None


def test_invalid_plugin_type_aborts_startup(monkeypatch):
    classes = {"processor": _Processor, "plugin": object}
    monkeypatch.setattr(container_module, "import_class", classes.__getitem__)
    container = _container([_domain("invalid")])

    with pytest.raises(DomainPluginRegistrationError) as captured:
        asyncio.run(container.init_plugins())

    assert isinstance(captured.value.__cause__, TypeError)


def test_registration_is_atomic_when_a_later_plugin_fails(monkeypatch):
    classes = {
        "processor": _Processor,
        "plugin": _Plugin,
        "broken_plugin": object,
    }
    monkeypatch.setattr(container_module, "import_class", classes.__getitem__)
    container = _container(
        [
            _domain("general"),
            _domain("broken", plugin="broken_plugin"),
        ]
    )

    with pytest.raises(DomainPluginRegistrationError):
        asyncio.run(container.init_plugins())

    assert container.domain_registry.get("general") is None
    assert container.domain_registry.get("broken") is None
