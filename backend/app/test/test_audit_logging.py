import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.audit_context import begin_audit_context, reset_audit_context
from app.infra.db.audit import install_audit_listeners, record_request_outcome
from app.infra.db.database import AuditLog, SystemSetting
from app.repositories.async_audit_log import AsyncAuditLogDatabase


def test_orm_changes_are_audited_automatically():
    asyncio.run(_exercise_audit_logging())


async def _exercise_audit_logging():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SystemSetting.__table__.create)
        await connection.run_sync(AuditLog.__table__.create)

    install_audit_listeners()

    token = begin_audit_context("POST", "/api/v1/admin/system-settings", "127.0.0.1")
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    SystemSetting(key="demo", value="initial"),
                    SystemSetting(key="demo-related", value="related"),
                ]
            )
            await session.commit()
    finally:
        reset_audit_context(token)

    token = begin_audit_context(
        "PATCH", "/api/v1/admin/system-settings/demo", "127.0.0.1"
    )
    try:
        async with session_factory() as session:
            setting = await session.get(SystemSetting, "demo")
            setting.value = "updated"
            await session.commit()
    finally:
        reset_audit_context(token)

    audit_log_db = AsyncAuditLogDatabase(engine, session_factory)
    token = begin_audit_context(
        "POST", "/api/v1/admin/tasks/run", "127.0.0.1"
    )
    try:
        await record_request_outcome(
            audit_log_db,
            status_code=200,
            route_name="run_task",
            path_params={"task_id": "demo-task"},
        )
    finally:
        reset_audit_context(token)

    async with session_factory() as session:
        logs = (
            await session.execute(select(AuditLog).order_by(AuditLog.id))
        ).scalars().all()

    create_logs = [log for log in logs if log.action == "CREATE"]
    update_log = next(log for log in logs if log.action == "UPDATE")
    execute_log = next(log for log in logs if log.action == "EXECUTE")
    demo_create = next(log for log in create_logs if log.target_id == "demo")

    assert len(create_logs) == 2
    assert len({log.request_id for log in create_logs}) == 1
    assert demo_create.target_type == "SystemSetting"
    assert demo_create.before_value is None
    assert demo_create.after_value["value"] == "initial"
    assert update_log.before_value["value"] == "initial"
    assert update_log.after_value["value"] == "updated"
    assert update_log.request_id != demo_create.request_id
    assert execute_log.target_type == "run_task"
    assert execute_log.target_id == "demo-task"
    for log in logs:
        UUID(log.request_id)

    await engine.dispose()
