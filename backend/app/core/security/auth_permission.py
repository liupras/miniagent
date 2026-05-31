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

from app.infra.cache_backend import MemoryCacheStore,create_cache_backend

# ── Module-level constants ─────────────────────────────────────────────────────

SUPER_PERMISSION  = "*:*:*"
CACHE_TTL_SECONDS = 3600.0         # Permission TTL: 60 min
CACHE_KEY_PREFIX  = "user_perms:" # "user_perms:<user_id>"

# Shared HTTPBearer scheme (stateless, safe to be module-level)
_bearer_scheme = HTTPBearer(auto_error=True)


# ── AuthPermission ─────────────────────────────────────────────────────────────

class AuthPermission:
    """
    Unified JWT authentication + permission enforcement service.

    Usage in routes
    ───────────────
    Three equivalent patterns (pick whichever fits the endpoint style):

    1. ``Depends(container.auth.require("system:user:list"))``
       — composable dependency, works with OpenAPI security UI.

    2. ``@container.auth.guard("system:user:delete")``
       — decorator, for endpoints where decorator style is preferred.

    3. ``router = APIRouter(dependencies=[Depends(container.auth.require(...))])``
       — router-level, protects every route in the router at once.
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
        
        self._jwt_auth  = container.jwt_auth
        self._user_db   = container.user_db
        self._cache     = MemoryCacheStore(max_size=cache_max_size)
        self._cache_ttl = cache_ttl_seconds
        logger.info(
            "AuthPermission initialised — cache max_size=%d, ttl=%.0fs",
            cache_max_size, cache_ttl_seconds,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _unauthorized(detail: str = "Invalid or expired token.") -> HTTPException:
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
            raise self._unauthorized()

        # Step 2 — username → User row
        async with self._user_db.get_session() as session:
            user = await self._user_db._get_user_by_username(session, username)

        if user is None:
            logger.warning("Token valid but username '%s' not found in DB.", username)
            raise self._unauthorized("User account not found.")

        # Step 3 — reject disabled accounts
        if not user.is_active:
            logger.warning("Blocked login for deactivated user '%s'.", username)
            raise self._unauthorized("User account is disabled.")

        logger.debug("Token resolved: '%s' → user_id=%s", username, user.id)
        return user.id

    # ── Permission cache ───────────────────────────────────────────────────

    async def _load_permissions(self, user_id: int) -> Set[str]:
        """DB → cache write-through. Returns the fresh permission set."""
        perms: Set[str] = await self._user_db.get_user_resource_codes(user_id)
        self._cache.mset_with_ttl(
            [(self._cache_key(user_id), self._encode(perms))],
            ttl_seconds=self._cache_ttl,
        )
        logger.debug("Permissions cached for user_id=%s (%d codes)", user_id, len(perms))
        return perms

    async def get_permissions(self, user_id: int) -> Set[str]:
        """Return permission set: TTL cache → DB fallback."""
        cached = self._cache.mget_ttl([self._cache_key(user_id)])[0]
        if cached is not None:
            logger.debug("Permission cache HIT for user_id=%s", user_id)
            return self._decode(cached)
        logger.debug("Permission cache MISS for user_id=%s", user_id)
        return await self._load_permissions(user_id)

    # ── Core permission check ──────────────────────────────────────────────

    async def check(self, user_id: int, required: str) -> None:
        """
        Raise HTTP 403 unless *user_id* holds *required* (or ``*:*:*``).
        """
        perms = await self.get_permissions(user_id)
        if SUPER_PERMISSION in perms or required in perms:
            return
        logger.warning("Access denied — user_id=%s lacks '%s'", user_id, required)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: '{required}' is required.",
        )

    # ── FastAPI dependency factories ───────────────────────────────────────

    def get_user_id(self) -> Callable:
        """
        Return a FastAPI dependency that resolves the current user_id.

        Usage::

            @router.get("/me")
            async def me(user_id: int = Depends(container.auth.get_user_id())):
                ...
        """
        auth = self  # capture for closure

        async def _dep(
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
        ) -> int:
            return await auth.resolve_user_id(credentials.credentials)

        return _dep

    def require(self, permission_code: str) -> Callable:
        """
        Return a FastAPI dependency that enforces *permission_code*.

        Resolves the token and checks the permission in one shot, so no
        separate ``get_user_id`` dependency is needed when using this pattern.

        Usage::

            @router.get("/users", dependencies=[Depends(container.auth.require("system:user:list"))])
            async def list_users(): ...

            # or inject user_id at the same time:
            @router.get("/users")
            async def list_users(user_id: int = Depends(container.auth.require("system:user:list"))):
                ...
        """
        auth = self

        async def _dep(
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
        ) -> int:
            user_id = await auth.resolve_user_id(credentials.credentials)
            await auth.check(user_id, permission_code)
            return user_id  # pass through so routes can use it if needed

        return _dep

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
                        detail="Authentication required (no Request in scope).",
                    )
                # Extract Bearer token manually from the Authorization header
                auth_header: str = request.headers.get("Authorization", "")
                if not auth_header.startswith("Bearer "):
                    raise auth._unauthorized("Missing Bearer token.")
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
        logger.info("Permission cache invalidated for user_id=%s", user_id)

    def invalidate_all(self) -> None:
        """Flush the entire permission cache (call after bulk role/menu changes)."""
        keys = list(self._cache.yield_keys(prefix=CACHE_KEY_PREFIX))
        self._cache.mdelete(keys)
        logger.info("Entire permission cache flushed (%d entries).", len(keys))

    async def refresh(self, user_id: int) -> Set[str]:
        """Force-reload one user's permissions from DB and repopulate cache."""
        return await self._load_permissions(user_id)

    def stats(self) -> dict:
        """Return LRU cache hit/miss/TTL statistics."""
        return self._cache.get_stats()