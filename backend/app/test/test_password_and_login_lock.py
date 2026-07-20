import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.db.database import Base
from app.repositories.async_user import AsyncUserDatabase
from app.schemas.admin.user import UserCreate, UserPasswordReset


@pytest.mark.parametrize(
    "password",
    ["Short1A", "lowercase1", "UPPERCASE1", "NoDigitsHere"],
)
def test_password_policy_rejects_passwords_missing_a_requirement(password):
    with pytest.raises(ValidationError):
        UserCreate(username="tester", password=password)
    with pytest.raises(ValidationError):
        UserPasswordReset(password=password)


def test_password_policy_accepts_configured_complexity():
    payload = UserCreate(username="tester", password="ValidPass1")
    assert payload.password == "ValidPass1"


def test_failed_logins_lock_account_and_admin_can_unlock():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        users = AsyncUserDatabase(engine, sessions)
        user = await users.create_user("tester", "ValidPass1")
        assert user is not None

        for attempt in range(1, 5):
            result = await users.authenticate(
                "tester", "wrong", max_failed_attempts=5, lock_duration_minutes=10
            )
            assert result.status == "invalid_credentials"
            stored = await users.get_by_id(user.id)
            assert stored.failed_login_attempts == attempt

        locked = await users.authenticate(
            "tester", "wrong", max_failed_attempts=5, lock_duration_minutes=10
        )
        assert locked.status == "locked"
        assert locked.locked_until is not None

        correct_but_locked = await users.authenticate(
            "tester", "ValidPass1", max_failed_attempts=5, lock_duration_minutes=10
        )
        assert correct_but_locked.status == "locked"

        assert await users.unlock_user(user.id)
        success = await users.authenticate(
            "tester", "ValidPass1", max_failed_attempts=5, lock_duration_minutes=10
        )
        assert success.status == "success"
        stored = await users.get_by_id(user.id)
        assert stored.failed_login_attempts == 0
        assert stored.locked_until is None

        await engine.dispose()

    asyncio.run(scenario())
