import json
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]/'infra/db/seed'
@pytest.mark.parametrize('name,phase',[('virtual_court_investigation_judge','INVESTIGATION'),('virtual_court_debate_judge','DEBATE')])
def test_v2_stage_seed(name,phase):
    rows=json.loads((ROOT/'agent.json').read_text(encoding='utf-8'))
    matches=[r for r in rows if r['name']==name]
    assert len(matches)==1
    row=matches[0]
    assert row['is_active'] and row['max_output_tokens']==2048
    text=row['system_prompt']
    for value in (phase,'allowed_decisions','allowed_targets','pending_points','不得判断证据真伪'):
        assert value in text
    for value in ('END_CURRENT_STAGE','issue_assessment','REQUEST_CLARIFICATION'):
        assert value not in text
    tools=json.loads((ROOT/'agent_tool_relation.json').read_text(encoding='utf-8'))
    assert [r['_tool_name'] for r in tools if r['_agent_name']==name] == ['intellectual_property_law_search']
    for rule in ('EXPLAIN_LAW', 'NO_ACTION', 'records', '已经回答', '不足', '反问'):
        assert rule in text

    assert '[JudgeAPI V2:' not in text
