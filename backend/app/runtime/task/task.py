#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-16
# @description: Task Entity

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.runtime.task.progress_tracker import ProgressTracker

from .status import TaskStatus

class Task(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    current: int = 0
    total: int = 0
    message: str = ""
    result: Any | None = None
    error: str | None = None
    cancel_requested: bool = False
    expire_at: datetime | None = None

    created_at: datetime = Field(
        default_factory=datetime.now
    )
    updated_at: datetime = Field(
        default_factory=datetime.now
    )

    def start(self, total: int = 0):
        self.status = TaskStatus.RUNNING
        self.total = total
        self.updated_at = datetime.now()        

    def update_progress(
        self,
        current: int,
        total: int | None = None,
        message: str = "",
    ):
        self.current = current

        if total is not None:
            self.total = total

        if self.total:
            self.progress = int(
                current * 100 / self.total
            )

        self.message = message
        self.updated_at = datetime.now()

        ProgressTracker.emit_sync(
            self.task_id, stage="running", message=message, progress=self.progress
        )

    def success(self, result=None):
        self.status = TaskStatus.SUCCESS
        self.progress = 100
        self.result = result
        self.updated_at = datetime.now()
        self.expire_at = datetime.now() + timedelta(hours=1)

        ProgressTracker.emit_sync(
            self.task_id, stage="success", message="Task completed successfully!", progress=100, done=True
        )

    def fail(self, error: str):
        self.status = TaskStatus.FAILED
        self.error = error
        self.updated_at = datetime.now()
        self.expire_at = datetime.now() + timedelta(hours=24)

        ProgressTracker.emit_sync(
            self.task_id, stage="failed", message=error,done=False,error=True
        )

    def cancel(self):
        self.cancel_requested = True
        self.expire_at = datetime.now() + timedelta(minutes=10)

        ProgressTracker.emit_sync(
            self.task_id, stage="canceled",done=False
        )