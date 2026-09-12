"""Judge-specific retrieval requirements; no model or tool execution here."""
import json
from app.schemas.integrations.virtual_court import JudgeDecision, JudgeLawCheckDecision
from app.runtime.agent.execution import ToolExecution

LAW_TOOL = 'intellectual_property_law_search'

def handoff(reason):
    return json.dumps({'decision':JudgeDecision.HANDOFF, 'target':None,
        'speech':'当前无法提供有充分检索依据的法律解释，请人工处理。',
        'pending_points':[reason]}, ensure_ascii=False)

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
    if not event.success:
        raise LawRetrievalUnavailable('工具执行失败，请人工核对法律依据。')
    if event.name == LAW_TOOL and not has_material(event.output):
        raise LawRetrievalUnavailable('法律检索未返回可用依据，请人工核对。')

def has_law_evidence(executions) -> bool:
    return any(e.name == LAW_TOOL and e.success and has_material(e.output) for e in executions)
