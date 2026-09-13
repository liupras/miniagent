"""Acceptance-only HTTP app for deterministic Judge V2 upstream fault paths."""

from types import SimpleNamespace

from fastapi import FastAPI

from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.judge import router
from app.runtime.agent.execution import AgentExecution, ToolExecution
from app.services.virtual_court import LawCheckService
from app.services.virtual_court.law_policy import LAW_TOOL


class _Runner:
    def __init__(self, results, *, observe=False):
        self._results = iter(results)
        self._observe = observe

    async def execute(self, **kwargs):
        result = next(self._results)
        if self._observe:
            for event in result.tools:
                kwargs['tool_observer'](event)
        return result


class _Factory:
    def __init__(self, runner):
        self._runner = runner

    async def get_runner_by_name(self, _name):
        return self._runner


class _FaultLawService:
    async def check(self, request):
        if request.state_version == 891:
            event = ToolExecution(
                name=LAW_TOOL,
                call_id='acceptance-failed-retrieval',
                success=False,
                error='injected acceptance failure',
            )
            runner = _Runner([AgentExecution('{}', (event,))], observe=True)
        elif request.state_version == 892:
            event = ToolExecution(
                name=LAW_TOOL,
                call_id='acceptance-empty-retrieval',
                success=True,
                output='{"confidence":"empty","chunks":[]}',
            )
            runner = _Runner([AgentExecution('{}', (event,))], observe=True)
        else:
            runner = _Runner([AgentExecution('{}'), AgentExecution('{}')])
        return await LawCheckService(_Factory(runner)).check(request)


app = FastAPI()
app.state.container = SimpleNamespace(
    law_check_service=_FaultLawService(),
    next_action_service=None,
)
app.include_router(router, prefix='/api/v2/integrations/virtual-court')
register_global_exception_handlers(app)
register_integration_exception_handlers(app)
