#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-16
# @description: Task Manager

from datetime import datetime
from threading import Lock

from .task import Task

class TaskManager:

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = Lock()

    def create(
        self,
        task_id: str,
        task_type: str,
    ) -> Task:

        task = Task(
            task_id=task_id,
            task_type=task_type,
        )

        with self._lock:
            self._tasks[task_id] = task

        return task

    def get(
        self,
        task_id: str,
    ) -> Task | None:

        return self._tasks.get(task_id)

    def remove(
        self,
        task_id: str,
    ):
        with self._lock:
            self._tasks.pop(task_id, None)

    def list(self):
        return list(self._tasks.values())
    
    def cleanup(self):

        now = datetime.now()
        expired_ids = []

        with self._lock:
            for task_id, task in self._tasks.items():
                if (
                    task.expire_at
                    and task.expire_at <= now
                ):
                    expired_ids.append(task_id)

            for task_id in expired_ids:
                self._tasks.pop(task_id, None)

# Global instance
task_manager = TaskManager()