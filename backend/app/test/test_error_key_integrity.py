import ast
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

import pytest
import yaml
from starlette.requests import Request

from app.api.domain_error_mapping import domain_error_http_status
from app.api.exception_handlers import domain_error_handler
from app.api.integrations.errors import judge_service_error_handler
from app.core.i18n import i18n as i18n_module
from app.core.i18n.error_translation import translate_domain_error
from app.schemas.exceptions import BaseDomainError
from app.schemas.exceptions import (
    AlreadyExistsError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    UnsupportedMediaTypeError,
)
from app.services.integration_auth import (
    IntegrationNotConfiguredError,
    InvalidIntegrationCredentialsError,
)
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeInvalidResponseError,
    JudgeServiceError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)


APP_ROOT = Path(__file__).resolve().parents[1]
LOCALE_ROOT = APP_ROOT / "locales"
ERROR_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


@dataclass(frozen=True)
class _ClassDeclaration:
    qualified_name: str
    name: str
    bases: tuple[str, ...]
    error_key: str | None


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _declared_error_key(node: ast.ClassDef) -> str | None:
    for statement in node.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue

        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if not any(isinstance(target, ast.Name) and target.id == "error_key" for target in targets):
            continue

        value = statement.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        return None
    return None


def _application_classes() -> dict[str, _ClassDeclaration]:
    declarations: dict[str, _ClassDeclaration] = {}
    for path in APP_ROOT.rglob("*.py"):
        if "test" in path.parts:
            continue

        module = ".".join(path.relative_to(APP_ROOT.parent).with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in (item for item in ast.walk(tree) if isinstance(item, ast.ClassDef)):
            bases = tuple(
                name
                for base in node.bases
                if (name := _base_name(base)) is not None
            )
            declaration = _ClassDeclaration(
                qualified_name=f"{module}.{node.name}",
                name=node.name,
                bases=bases,
                error_key=_declared_error_key(node),
            )
            declarations[declaration.qualified_name] = declaration
    return declarations


def _domain_error_declarations() -> list[tuple[_ClassDeclaration, str]]:
    declarations = _application_classes()
    by_name: dict[str, list[_ClassDeclaration]] = {}
    for declaration in declarations.values():
        by_name.setdefault(declaration.name, []).append(declaration)

    domain_names = {"BaseDomainError"}
    changed = True
    while changed:
        changed = False
        for declaration in declarations.values():
            if declaration.name not in domain_names and any(
                base in domain_names for base in declaration.bases
            ):
                domain_names.add(declaration.name)
                changed = True

    def effective_key(declaration: _ClassDeclaration, seen: set[str]) -> str | None:
        if declaration.error_key is not None:
            return declaration.error_key
        if declaration.qualified_name in seen:
            return None
        for base in declaration.bases:
            for parent in by_name.get(base, []):
                if key := effective_key(parent, seen | {declaration.qualified_name}):
                    return key
        return None

    result = []
    for declaration in declarations.values():
        if declaration.name == "BaseDomainError":
            continue
        if any(base in domain_names for base in declaration.bases):
            result.append((declaration, effective_key(declaration, set()) or ""))
    return result


def _load_locale(language: str) -> dict:
    with (LOCALE_ROOT / f"{language}.yaml").open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    for name, value in data.items():
        key = f"{prefix}.{name}" if prefix else str(name)
        if isinstance(value, dict):
            flattened.update(_flatten(value, key))
        else:
            flattened[key] = str(value)
    return flattened


def _placeholders(template: str) -> set[str]:
    return {
        field_name.split(".", 1)[0].split("[", 1)[0]
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }


def _translation_key(error_key: str) -> str:
    if "." in error_key:
        return error_key
    return f"entity.{error_key}"


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


def test_all_domain_error_classes_have_stable_error_keys():
    errors = _domain_error_declarations()

    assert errors, "No BaseDomainError subclasses were discovered"
    for declaration, error_key in errors:
        assert error_key, f"{declaration.qualified_name} has no stable error_key"
        assert ERROR_KEY_PATTERN.fullmatch(error_key), (
            f"{declaration.qualified_name} has invalid error_key {error_key!r}"
        )


def test_chinese_and_english_locale_keys_are_identical():
    zh = _flatten(_load_locale("zh"))
    en = _flatten(_load_locale("en"))

    assert zh.keys() == en.keys()


def test_chinese_and_english_placeholders_are_identical():
    zh = _flatten(_load_locale("zh"))
    en = _flatten(_load_locale("en"))

    mismatches = {
        key: (_placeholders(zh[key]), _placeholders(en[key]))
        for key in zh.keys() & en.keys()
        if _placeholders(zh[key]) != _placeholders(en[key])
    }
    assert mismatches == {}


@pytest.mark.parametrize("language", ["zh", "en"])
def test_every_domain_error_key_has_a_translation(language, monkeypatch):
    locale = _load_locale(language)
    flattened = _flatten(locale)
    monkeypatch.setattr(i18n_module, "translations", locale)

    for declaration, error_key in _domain_error_declarations():
        translation_key = _translation_key(error_key)
        assert translation_key in flattened, (
            f"{declaration.qualified_name} uses missing {language} locale key "
            f"{translation_key!r}"
        )

        params = {
            name: f"<{name}>"
            for name in _placeholders(flattened[translation_key])
        }
        error = BaseDomainError(
            entity_name="Entity" if "." not in error_key else None,
            entity_id=1,
            error_key=error_key,
            params=params,
        )
        translated = translate_domain_error(error)
        assert translated != translation_key
        assert translated != error_key


def test_integration_and_standard_api_share_error_message_semantics(monkeypatch):
    monkeypatch.setattr(i18n_module, "translations", _load_locale("en"))
    error = JudgeUnavailableError()

    async def render_responses():
        standard = await domain_error_handler(_request("/api/v1/test"), error)
        integration = await judge_service_error_handler(
            _request("/api/v1/integrations/virtual-court/judge/decide"),
            error,
        )
        return standard, integration

    standard_response, integration_response = asyncio.run(
        render_responses()
    )
    standard_payload = json.loads(standard_response.body)
    integration_payload = json.loads(integration_response.body)

    assert standard_payload["message"] == integration_payload["error"]["message"]
    assert standard_payload["message"] == translate_domain_error(error)
    assert standard_response.status_code == integration_response.status_code
    assert "error" not in standard_payload
    assert set(integration_payload) == {"error"}


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (BaseDomainError(), 400),
        (NotFoundError("User", 1), 404),
        (AlreadyExistsError("User", 1), 409),
        (PermissionDeniedError("denied"), 403),
        (UnsupportedMediaTypeError("unsupported"), 415),
        (InfrastructureError("unavailable"), 503),
        (InvalidIntegrationCredentialsError(), 401),
        (IntegrationNotConfiguredError(), 503),
        (JudgeConfigurationError(), 503),
        (JudgeUnavailableError(), 503),
        (JudgeTimeoutError(params={"timeout": 30}), 504),
        (JudgeInvalidResponseError(), 502),
        (JudgeServiceError(), 500),
    ],
)
def test_domain_error_http_status_is_mapped_only_at_api_boundary(
    error,
    expected_status,
):
    assert not hasattr(error, "status_code")
    assert domain_error_http_status(error) == expected_status
