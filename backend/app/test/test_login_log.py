import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db.database import LoginLog
from app.repositories.async_login_log import AsyncLoginLogDatabase
from app.services.auth.login_log import LoginLogService


def test_login_and_refresh_events_are_persisted():
    asyncio.run(_exercise_login_log())


async def _exercise_login_log():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(LoginLog.__table__.create)

    service = LoginLogService(AsyncLoginLogDatabase(engine, session_factory))
    await service.record(
        request_id=str(uuid4()),
        event_type="LOGIN",
        success=True,
        username="admin",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    await service.record(
        request_id=str(uuid4()),
        event_type="REFRESH_TOKEN",
        success=False,
        failure_reason="invalid_refresh_token",
    )

    async with session_factory() as session:
        rows = (
            await session.execute(select(LoginLog).order_by(LoginLog.id))
        ).scalars().all()

    assert len(rows) == 2
    assert rows[0].event_type == "LOGIN"
    assert rows[0].success is True
    assert rows[0].username == "admin"
    assert rows[1].event_type == "REFRESH_TOKEN"
    assert rows[1].success is False
    assert rows[1].failure_reason == "invalid_refresh_token"

    await engine.dispose()
