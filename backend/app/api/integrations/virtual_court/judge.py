"""JudgeAPI V2 only. Bound raw body and reject duplicate JSON keys before parsing."""
from time import perf_counter
from app.core.logger_config import get_logger
from fastapi import APIRouter, Depends, Request, Security
from fastapi.routing import APIRoute
from app.api.integrations.auth import require_virtual_court_api_key
from app.api.integrations.errors import integration_error_response
from app.schemas.integrations.virtual_court import JudgeDecisionRequest, JudgeDecisionResponse, IntegrationErrorCode, IntegrationErrorResponse
from app.schemas.integrations.virtual_court.judge import REQUEST_MAX_BYTES, strict_json
from app.services.virtual_court import JudgeService

logger = get_logger(__name__)

class JudgeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            chunks = bytearray()
            try:
                async for chunk in request.stream():
                    if len(chunks) + len(chunk) > REQUEST_MAX_BYTES:
                        return integration_error_response(status_code=422, code=IntegrationErrorCode.INVALID_REQUEST,
                            message='请求超过大小限制。', retryable=False, details={'reason':'body_size'})
                    chunks.extend(chunk)
                strict_json(bytes(chunks).decode('utf-8'))
            except (ValueError, UnicodeError, RecursionError):
                return integration_error_response(status_code=422, code=IntegrationErrorCode.INVALID_REQUEST,
                    message='请求必须是合法且没有重复字段的 UTF-8 JSON。', retryable=False, details={'reason':'invalid_json'})
            # Starlette caches request bodies here; downstream FastAPI keeps typed OpenAPI validation.
            request._body = bytes(chunks)
            return await original(request)
        return handler

router = APIRouter(route_class=JudgeRoute)
def get_judge_service(request: Request):
    return request.app.state.container.judge_service

@router.post('/judge/decide', response_model=JudgeDecisionResponse,
             responses={code:{'model':IntegrationErrorResponse} for code in (401,422,500,502,503,504)},
             summary='One constrained V2 investigation or debate decision')
async def decide(body: JudgeDecisionRequest,
                 _authenticated: None = Security(require_virtual_court_api_key),
                 service: JudgeService = Depends(get_judge_service)) -> JudgeDecisionResponse:
    started = perf_counter()
    logger.info('[JudgeV2] accepted: phase={}, state_version={}', body.phase, body.state_version)
    logger.debug('[JudgeV2] request: {}', body.model_dump_json(exclude_unset=True))
    response = await service.decide(body)
    logger.debug('[JudgeV2] response: {}', response.model_dump_json())
    logger.info('[JudgeV2] completed: decision={}, elapsed_ms={:.1f}', response.decision, (perf_counter()-started)*1000)
    return response
