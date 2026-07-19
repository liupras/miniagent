#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-01
# @description: Unified permission authentication — encapsulated as AuthPermission
#               and registered as a singleton on ServiceContainer.

import json
from functools import wraps
from typing import Callable, Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from loguru import logger

from app.core.i18n.i18n_http import raise_forbidden
from app.infra.cache.factory import create_cache_backend

# ── Module-level constants ─────────────────────────────────────────────────────

from app.core.constants import SUPER_PERMISSION
from app.core.audit_context import set_audit_user

CACHE_TTL_SECONDS = 3600.0         # Permission TTL: 60 min
CACHE_KEY_PREFIX  = "user_perms:" # "user_perms:<user_id>"

# Shared HTTPBearer scheme (stateless, safe to be module-level)
_bearer_scheme = HTTPBearer(auto_error=True)

from app.core.i18n.i18n import t

# ── AuthPermission ─────────────────────────────────────────────────────────────

class AuthPermission:
    """
    Unified JWT authentication + permission enforcement service.
    """

    def __init__(
        self,
        container,
        cache_max_size: int   = 2000,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        from .jwt_auth import jwt_auth
        self._jwt_auth  = jwt_auth
        self._user_db   = container.user_db
        self._menu_db   = container.menu_db
        self._cache     = create_cache_backend(namespace="auth", max_size=cache_max_size)
        self._cache_ttl = cache_ttl_seconds
        logger.info(
            "AuthPermission initialised — cache max_size={:d}, ttl={:.0f}s",
            cache_max_size, cache_ttl_seconds
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _unauthorized(detail: str = "Invalid or expired token") -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _cache_key(self, user_id: int) -> str:
        return f"{CACHE_KEY_PREFIX}{user_id}"

    @staticmethod
    def _encode(perms: Set[str]) -> bytes:
        return json.dumps(list(perms), ensure_ascii=False).encode()

    @staticmethod
    def _decode(raw: bytes) -> Set[str]:
        return set(json.loads(raw.decode()))

    # ── Token resolution ───────────────────────────────────────────────────

    async def resolve_user_id(self, token: str) -> int:
        """
        Verify *token* and return the authenticated ``user_id``.

        Flow
        ────
        1. ``jwt_auth.verify_token(token)`` — PyJWT signature + expiry check,
           returns ``username`` or ``None``.
        2. DB lookup: ``_get_user_by_username`` → full ``User`` ORM row.
           Needed to obtain the integer PK and check ``is_active``.
        3. Reject deactivated accounts with 401 (identity invalid, not just
           lacking a permission).
           
        Raises
        ──────
        HTTP 401 on any failure (bad token, unknown user, inactive account).
        """
        # Step 1 — verify JWT, extract username
        username: Optional[str] = self._jwt_auth.verify_token(token)
        if not username:
            logger.warning("Token verification failed (expired or invalid).")
            raise self._unauthorized(t("auth.token_invalid"))

        # Step 2 — username → User row
        async with self._user_db.get_session() as session:
            user = await self._user_db._get_user_by_username(session, username)

        if user is None:
            logger.warning("Token valid but username '{}' not found in DB.", username)
            raise self._unauthorized(t("auth.user_not_found"))

        # Step 3 — reject disabled accounts
        if not user.is_active:
            logger.warning("Blocked login for deactivated user '{}'.", username)
            raise self._unauthorized(t("auth.user_disabled"))

        set_audit_user(user.id, user.username)
        logger.debug("Token resolved: '{}' → user_id={}", username, user.id)
        return user.id

    # ── Permission cache ───────────────────────────────────────────────────

    async def _load_permissions(self, user_id: int) -> Set[str]:
        """DB → cache write-through. Returns the fresh permission set."""

        perms: Set[str] = await self._menu_db.get_user_resource_codes(user_id)
        self._cache.mset_with_ttl(
            [(self._cache_key(user_id), self._encode(perms))],
            ttl_seconds=self._cache_ttl,
        )
        logger.debug("Permissions cached for user_id={} ({} codes)", user_id, len(perms))
        return perms

    async def get_permissions(self, user_id: int) -> Set[str]:
        """Return permission set: TTL cache → DB fallback."""
        cached = self._cache.mget_ttl([self._cache_key(user_id)])[0]
        if cached is not None:
            logger.debug("Permission cache HIT for user_id={}", user_id)
            return self._decode(cached)
        logger.debug("Permission cache MISS for user_id={}", user_id)
        return await self._load_permissions(user_id)

    # ── Core permission check ──────────────────────────────────────────────

    async def check(self, user_id: int, required: str) -> None:
        """
        Raise HTTP 403 unless *user_id* holds *required* (or `SUPER_PERMISSION`).
        """
        perms = await self.get_permissions(user_id)
        if SUPER_PERMISSION in perms or required in perms:
            return
        logger.warning("Access denied — user_id={} lacks '{}'", user_id, required)
        raise_forbidden("auth.permission_denied", required=required)

    # ── FastAPI dependency factories ───────────────────────────────────────

    def get_user_id(self) -> "AuthPermission.CurrentUser":
        """
        Return a FastAPI dependency that only verifies the token and resolves
        ``user_id`` — **no** permission check.

        The returned ``CurrentUser`` instance is self-contained and can be
        built at module level (no container required at import time).

        Usage::

            # Module level — build once, reuse everywhere
            current_user = Permission("*")          # or:
            current_user = AuthPermission.CurrentUser()

            @router.get("/me")
            async def me(user_id: int = Depends(container.auth.get_user_id())):
                ...
        """
        return AuthPermission.CurrentUser()

    class CurrentUser:
        """
        Callable dependency produced by ``AuthPermission.get_user_id()``.
        Resolves auth from ``request.app.state.container.auth`` at call time.
        """

        __slots__ = ()

        async def __call__(
            self,
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
        ) -> int:
            auth: "AuthPermission" = request.app.state.container.auth
            return await auth.resolve_user_id(credentials.credentials)

    def require(self, permission_code: str) -> "AuthPermission.Permission":
        """
        Return a FastAPI-compatible dependency that verifies the Bearer token
        **and** enforces *permission_code* in a single step.
        """
        return AuthPermission.Permission(permission_code)

    class Permission:
        """
        Callable FastAPI dependency produced by ``AuthPermission.require()``.

        Self-contained: resolves ``AuthPermission`` from
        ``request.app.state.container.auth`` at call time, so instances can be
        created at **module level** without the container being available yet.

        FastAPI inspects ``__call__``'s signature statically at startup, which
        is why this must be a class rather than a plain closure — closures with
        inner ``Depends()`` calls are not visible to the DI introspection.
        """

        __slots__ = ("_code",)

        def __init__(self, permission_code: str) -> None:
            self._code = permission_code

        async def __call__(
            self,
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
        ) -> int:
            """Verify token → resolve user_id → check permission → return user_id."""
            auth: "AuthPermission" = request.app.state.container.auth
            user_id: int = await auth.resolve_user_id(credentials.credentials)
            await auth.check(user_id, self._code)
            return user_id

    def guard(self, permission_code: str) -> Callable:
        """
        Decorator that enforces *permission_code*.

        The decorated coroutine **must** declare ``request: Request`` so the
        decorator can extract and verify the Bearer token.

        Usage::

            @router.delete("/users/{uid}")
            @container.auth.guard("system:user:delete")
            async def delete_user(uid: int, request: Request):
                ...
        """
        auth = self

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                request: Optional[Request] = kwargs.get("request")
                if request is None:
                    # Fallback: scan positional args for a Request instance
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break
                if request is None:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=t("auth.auth_required"),
                    )
                # Extract Bearer token manually from the Authorization header
                auth_header: str = request.headers.get("Authorization", "")
                if not auth_header.startswith("Bearer "):
                    raise auth._unauthorized(t("auth.missing_bearer"))
                token = auth_header[len("Bearer "):]
                user_id = await auth.resolve_user_id(token)
                await auth.check(user_id, permission_code)
                # Inject resolved user_id so the handler can use it
                kwargs["user_id"] = user_id
                return await func(*args, **kwargs)

            return wrapper
        return decorator

    # ── Cache management (called by admin router / role-change hooks) ──────

    def invalidate(self, user_id: int) -> None:
        """Remove a single user's cache entry (call after role change)."""
        self._cache.mdelete([self._cache_key(user_id)])
        logger.info("Permission cache invalidated for user_id={}", user_id)

    async def refresh(self, user_id: int) -> Set[str]:
        """Force-reload one user's permissions from DB and repopulate cache."""
        return await self._load_permissions(user_id)
