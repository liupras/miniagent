"""Read-only compatibility observations. Rejections are gaps, not test successes."""
import json
import sys
from pathlib import Path
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent
BACKEND = Path('D:/miniagent/backend')
sys.path.insert(0, str(BACKEND))
from app.schemas.integrations.virtual_court import JudgeDecisionRequest, JudgeAgentOutput

observations = []
for name, kind in [
    ('investigation-request','request'),
    ('law-check-investigation','request'),
    ('law-check-debate-single-party','request'),
    ('investigation-explain-law-agent','agent-output'),
    ('investigation-no-action-agent','agent-output'),
]:
    data = json.loads((ROOT/'cases'/f'{name}.json').read_text(encoding='utf-8'))
    cls = JudgeDecisionRequest if kind == 'request' else JudgeAgentOutput
    try:
        cls.model_validate(data)
        observations.append({'case':name,'required_by_extension':'accept','current':'accept'})
    except ValidationError as exc:
        observations.append({'case':name,'required_by_extension':'accept','current':'reject',
                             'errors':[{'field':list(e['loc']),'type':e['type']} for e in exc.errors()]})

guard = (BACKEND/'app/runtime/agent/agent_runner.py').read_text(encoding='utf-8')
seed = json.loads((BACKEND/'app/infra/db/seed/agent_tool_relation.json').read_text(encoding='utf-8'))
names = {'virtual_court_investigation_judge','virtual_court_debate_judge'}
result = {
    'note':'Current implementation probes only; no LLM, HTTP service or database writes.',
    'schema_observations':observations,
    'current_tool_rejection_guard_present':'unexpected_tools' in guard,
    'current_seed_judge_tool_bindings':[r for r in seed if r['_agent_name'] in names],
}
print(json.dumps(result, ensure_ascii=False, indent=2))
