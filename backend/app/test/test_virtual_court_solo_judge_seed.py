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
    tools=json.loads((ROOT/'agent_tool_relation.json').read_text(encoding='utf-8'))
    assert [r['_tool_name'] for r in tools if r['_agent_name']==name] == ['intellectual_property_law_search']
    for rule in ('EXPLAIN_LAW', 'NO_ACTION', 'records', '已回答', '不足', '反问'):
        assert rule in text

    for rule in (
        '最新一条当事人发言', '不能单独触发 EXPLAIN_LAW',
        '我方维持此前意见，没有法律问题需要解释。',
        '不得检索或返回 EXPLAIN_LAW',
        '允许 NO_ACTION 时返回 NO_ACTION',
        '不允许 NO_ACTION 时，按当前阶段规则正常推进',
    ):
        assert rule in text

    if phase == 'DEBATE':
        for rule in (
            '只处理 current_issue', '不得提前结束当前争点',
            '双方已经完成本轮发言', '需要实质补充时返回 CONTINUE',
            '无需继续讨论时返回 COMPLETE',
        ):
            assert rule in text

    assert '[JudgeAPI V2:' not in text


def test_judge_stage_prompts_share_common_decision_rules():
    rows=json.loads((ROOT/'agent.json').read_text(encoding='utf-8'))
    prompts={row['name']:row['system_prompt'] for row in rows}
    investigation=prompts['virtual_court_investigation_judge'].split('调查阶段 INVESTIGATION\n',1)[0]
    debate=prompts['virtual_court_debate_judge'].split('辩论阶段 DEBATE\n',1)[0]
    assert investigation == debate
