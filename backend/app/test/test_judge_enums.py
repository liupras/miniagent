import json
import pytest
from pydantic import ValidationError
from app.schemas.integrations.virtual_court import (
    JudgePhase, JudgeDecision, JudgeRecordType, JudgeDecisionRequest, JudgeAgentOutput, JudgeRecord)
from app.test.judge_v2_helpers import request_data, output

@pytest.mark.parametrize('from_json',[False,True])
def test_wire_strings_become_enum_members_and_serialize_unchanged(from_json):
    data=request_data()
    model=(JudgeDecisionRequest.model_validate_json(json.dumps(data)) if from_json
           else JudgeDecisionRequest.model_validate(data,strict=True))
    assert model.phase is JudgePhase.INVESTIGATION
    assert all(isinstance(d,JudgeDecision) for d in model.allowed_decisions)
    assert all(isinstance(r.type,JudgeRecordType) for r in model.records)
    assert model.model_dump(mode='json',exclude_unset=True)==data
    assert json.loads(model.model_dump_json(exclude_unset=True))==data

def test_internal_enum_instances_are_accepted():
    data=request_data();data['phase']=JudgePhase.INVESTIGATION
    data['allowed_decisions']=[JudgeDecision.ASK,JudgeDecision.HANDOFF]
    req=JudgeDecisionRequest.model_validate(data)
    assert req.allowed_decisions[0] is JudgeDecision.ASK
    result=JudgeAgentOutput.model_validate({**output(),'decision':JudgeDecision.ASK})
    assert result.decision is JudgeDecision.ASK
    assert result.model_dump(mode='json')['decision']=='ASK'

@pytest.mark.parametrize('value',[1,True,None,b'INVESTIGATION','investigation',' INVESTIGATION','UNKNOWN'])
def test_phase_rejects_non_strings_and_unknown_values(value):
    with pytest.raises(ValidationError):JudgeDecisionRequest.model_validate({**request_data(),'phase':value})

@pytest.mark.parametrize('value',[1,True,None,b'ASK','ask','ASK ','UNKNOWN'])
def test_decision_rejects_coercion(value):
    with pytest.raises(ValidationError):JudgeAgentOutput.model_validate({**output(),'decision':value})
    with pytest.raises(ValidationError):JudgeDecisionRequest.model_validate({**request_data(),'allowed_decisions':[value,'HANDOFF']})

@pytest.mark.parametrize('value',[1,True,None,b'SPEECH','speech',' SPEECH','UNKNOWN'])
def test_record_type_rejects_coercion(value):
    with pytest.raises(ValidationError):JudgeRecord.model_validate({'type':value,'role':'PLAINTIFF','text':'statement'})

def test_other_fields_remain_strict_and_roles_remain_extensible():
    with pytest.raises(ValidationError):JudgeDecisionRequest.model_validate({**request_data(),'state_version':'1'})
    with pytest.raises(ValidationError):JudgeRecord.model_validate({'type':'SPEECH','role':1,'text':'statement'})
    record=JudgeRecord.model_validate({'type':'SPEECH','role':'FUTURE_ROLE','text':'statement'})
    assert type(record.role) is str and record.type is JudgeRecordType.SPEECH

def test_json_schema_exposes_wire_enum_values():
    schema=JudgeDecisionRequest.model_json_schema()
    for name,enum in [('JudgePhase',JudgePhase),('JudgeDecision',JudgeDecision),('JudgeRecordType',JudgeRecordType)]:
        assert schema['$defs'][name]['enum']==[member.value for member in enum]
        assert schema['$defs'][name]['type']=='string'
