# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Late localization for stable application exceptions.

from app.core.i18n.i18n import t
from app.schemas.exceptions import BaseDomainError


def translate_domain_error(error: BaseDomainError) -> str:
    """Translate an error at a response/presentation boundary."""
    params = error.translation_params()
    key = error.i18n_key()
    detail = t(key, **params)
    if detail != key:
        return detail

    fallback_key = f"entity.{error.error_key.rsplit('.', 1)[-1]}"
    fallback_detail = t(fallback_key, **params)
    if fallback_detail != fallback_key:
        return fallback_detail

    return t("common.failed")
