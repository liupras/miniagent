#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: I18n http

from fastapi import HTTPException, status
from app.core.i18n import t

_BEARER_HEADERS = {"WWW-Authenticate": "Bearer"}

def msg(key: str, **kwargs) -> str:
    """Returns the translated plain text (for ApiResponse.message / HTTPException.detail)."""
    return t(key, **kwargs)

def raise_unauthorized(key: str = "auth.token_invalid", **kwargs) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=msg(key, **kwargs),
        headers=_BEARER_HEADERS,
    )

def raise_forbidden(key: str, **kwargs) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg(key, **kwargs))

def raise_not_found(key: str, **kwargs) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg(key, **kwargs))

def raise_conflict(key: str, **kwargs) -> None:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg(key, **kwargs))