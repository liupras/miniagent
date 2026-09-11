"""Generic execution results. Tool payloads are internal and excluded from repr."""
from dataclasses import dataclass, field
from typing import Callable

@dataclass(frozen=True)
class ToolExecution:
    name: str
    call_id: str
    success: bool
    output: str | None = field(default=None, repr=False)
    error: str | None = None

ToolObserver = Callable[[ToolExecution], None]

@dataclass(frozen=True)
class AgentExecution:
    text: str
    tools: tuple[ToolExecution, ...] = field(default=(), repr=False)
    stop_reason: str = 'completed'
