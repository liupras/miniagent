import json
import pytest
from app.schemas.integrations.virtual_court import JudgeDecisionRequest
from app.schemas.integrations.virtual_court.judge import REQUEST_MAX_BYTES, strict_json
from app.test.judge_v2_helpers import ROOT, load

CASES=[c for c in load('manifest.json')['cases'] if c['kind']=='request']
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_frozen_request_contract(case):
    raw=(ROOT/case['file']).read_bytes()
    def validate():
        if len(raw)>REQUEST_MAX_BYTES: raise ValueError('body_size')
        return JudgeDecisionRequest.model_validate(strict_json(raw))
    if case['valid']: validate()
    else:
        with pytest.raises(ValueError): validate()

def test_schema_keeps_exact_seven_fields():
    assert set(JudgeDecisionRequest.model_fields)=={'state_version','phase','allowed_decisions','allowed_targets','case_context','current_issue','records'}
