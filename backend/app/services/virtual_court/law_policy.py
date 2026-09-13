"""Judge-specific retrieval requirements; no model or tool execution here."""
import json
import re

from app.core.logger_config import get_logger
from app.runtime.agent.execution import ToolExecution
from app.schemas.integrations.virtual_court import JudgeLawCheckDecision

LAW_TOOL = 'intellectual_property_law_search'
logger = get_logger(__name__)

_QUESTION_CUE = re.compile(
    r'(?:请问|想问|咨询|解释|说明|告知|依据|法律|法条|法规|著作权|'
    r'专利|商标|版权|侵权|合法|违法|为什么|为何|如何|怎么|是否|'
    r'能否|可否|应否|哪条|哪部|哪项|什么法|什么规定|怎么办|行不行|吗|么|呢)'
)


def is_definitely_no_action(text: str) -> bool:
    """Conservatively recognize statements that cannot request legal analysis."""

    return '?' not in text and '？' not in text and _QUESTION_CUE.search(text) is None


def law_check_no_action():
    return json.dumps({
        'decision': JudgeLawCheckDecision.NO_ACTION,
        'speech': '',
        'pending_points': [],
    }, ensure_ascii=False)

def law_check_handoff(reason):
    return json.dumps({
        'decision': JudgeLawCheckDecision.HANDOFF,
        'speech': '当前无法提供有充分检索依据的法律解释，请人工处理。',
        'pending_points': [reason],
    }, ensure_ascii=False)

def has_material(raw):
    # The bound smart-router tool returns structured chunks, not a free-text answer.
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return (isinstance(data, dict) and not data.get('error')
            and data.get('confidence') != 'empty' and isinstance(data.get('chunks'), list)
            and any(isinstance(c, dict) and isinstance(c.get('text'), str)
                    and c['text'].strip() for c in data['chunks']))
    except (ValueError, TypeError):
        return False

class LawRetrievalUnavailable(Exception):
    """An observation requires a business HANDOFF, not output repair."""

def check_law_observation(event: ToolExecution) -> None:
    material = event.name == LAW_TOOL and event.success and has_material(event.output)
    logger.info(
        '[LawCheckV2] tool observed: name={}, success={}, material={}',
        event.name,
        event.success,
        material,
    )
    if not event.success:
        raise LawRetrievalUnavailable('工具执行失败，请人工核对法律依据。')
    if event.name == LAW_TOOL and not material:
        raise LawRetrievalUnavailable('法律检索未返回可用依据，请人工核对。')

def has_law_evidence(executions) -> bool:
    return any(e.name == LAW_TOOL and e.success and has_material(e.output) for e in executions)
