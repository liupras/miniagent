import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db.database import LoginLog
from app.repositories.async_login_log import AsyncLoginLogDatabase
from app.services.admin.login_log import LoginLogAdminService
from app.services.auth.login_log import LoginLogService


def test_login_and_refresh_events_are_persisted():
    asyncio.run(_exercise_login_log())


async def _exercise_login_log():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(LoginLog.__table__.create)

    repository = AsyncLoginLogDatabase(engine, session_factory)
    recorder = LoginLogService(repository)
    admin_service = LoginLogAdminService(repository)
    login_row = await recorder.record(
        request_id=str(uuid4()),
        event_type="LOGIN",
        success=True,
        username="admin",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    await recorder.record(
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

    failed_refreshes = await admin_service.list_logs(
        event_type="REFRESH_TOKEN",
        success=False,
    )
    assert failed_refreshes.total == 1
    assert failed_refreshes.data[0].failure_reason == "invalid_refresh_token"

    detail = await admin_service.get(login_row.id)
    assert detail.event_type == "LOGIN"
    assert detail.username == "admin"

    await engine.dispose()
