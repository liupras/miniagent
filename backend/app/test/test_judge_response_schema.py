import json
import pytest
from app.schemas.integrations.virtual_court import JudgeDecisionRequest, JudgeAgentOutput, JudgeDecisionResponse
from app.services.virtual_court.response_validator import validate_judge_agent_output
from app.schemas.integrations.virtual_court.judge import strict_json
from app.test.judge_v2_helpers import ROOT, load

CASES=[c for c in load('manifest.json')['cases'] if c['kind']!='request']
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_frozen_response_contract(case):
    raw=(ROOT/case['file']).read_text(encoding='utf-8')
    def validate():
        cls=JudgeAgentOutput if case['kind']=='agent-output' else JudgeDecisionResponse
        result=cls.model_validate(strict_json(raw))
        if 'request' in case:
            req=JudgeDecisionRequest.model_validate(load(case['request']))
            if case['kind']=='response' and result.state_version!=req.state_version:
                raise ValueError('stale_state') # This check belongs to the caller, not model generation.
            validate_judge_agent_output(json.dumps(result.model_dump(exclude={'state_version'})),req)
        return result
    if case['valid']: validate()
    else:
        from app.services.virtual_court import JudgeInvalidResponseError
        with pytest.raises((ValueError,JudgeInvalidResponseError)): validate()

def test_response_fields():
    assert set(JudgeAgentOutput.model_fields)=={'decision','target','speech','pending_points'}
    assert set(JudgeDecisionResponse.model_fields)==set(JudgeAgentOutput.model_fields)|{'state_version'}
