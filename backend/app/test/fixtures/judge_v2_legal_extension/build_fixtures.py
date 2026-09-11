"""Rebuild frozen contract fixtures; does not call either application or any LLM."""
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]

def save(name, data):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def string(n, minimum=1):
    return {'type': 'string', 'minLength': minimum, 'maxLength': n, **({'pattern': r'\S'} if minimum else {})}

def array(item, n, minimum=0):
    return {'type': 'array', 'items': item, 'minItems': minimum, 'maxItems': n}

def obj(properties, required=None):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties,
            'required': list(properties) if required is None else required}

def nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}

role = string(64)
version = {'type': 'integer', 'minimum': 0, 'maximum': 9223372036854775807}
context = obj({'summary': string(16000), 'claims': array(string(4000), 30),
               'defenses': array(string(4000), 30), 'dispute_focuses': array(string(1000), 20),
               'investigation_summary': string(16000)},
              ['summary', 'claims', 'defenses', 'dispute_focuses'])
record = obj({'type': {'enum': ['SPEECH', 'SUMMARY']}, 'role': nullable(role), 'text': string(16000)})
record['allOf'] = [
    {'if': {'properties': {'type': {'const': 'SPEECH'}}},
     'then': {'properties': {'role': role, 'text': string(8000)}},
     'else': {'properties': {'role': {'type': 'null'}}}}
]
request = obj({'state_version': version, 'phase': {'enum': ['INVESTIGATION', 'DEBATE']},
               'allowed_decisions': {**array({'enum': ['ASK', 'CONTINUE', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION']}, 5, 1),
                                     'uniqueItems': True, 'contains': {'const': 'HANDOFF'}},
               'allowed_targets': {**array(role, 32), 'uniqueItems': True},
               'case_context': context,
               'current_issue': nullable(obj({'id': string(64), 'question': string(1000)})),
               'records': array(record, 512)})
request['allOf'] = [
    {'if': {'properties': {'phase': {'const': 'INVESTIGATION'}}},
     'then': {'properties': {'allowed_decisions': {'items': {'enum': ['ASK', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION']}},
                              'current_issue': {'type': 'null'},
                              'case_context': {'not': {'required': ['investigation_summary']}}}},
     'else': {'properties': {'allowed_decisions': {'items': {'enum': ['CONTINUE', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION']}},
                              'current_issue': {'type': 'object'},
                              'case_context': {'required': ['investigation_summary']}}}},
    {'if': {'properties': {'allowed_decisions': {'contains': {'const': 'ASK'}}}},
     'then': {'properties': {'allowed_targets': {'minItems': 1}}}}
]
output = obj({'decision': {'enum': ['ASK', 'CONTINUE', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION']},
              'target': nullable(role), 'speech': string(4000, 0), 'pending_points': array(string(1000), 30)})
output['allOf'] = [
    {'if': {'properties': {'decision': {'const': 'ASK'}}},
     'then': {'properties': {'target': role}}, 'else': {'properties': {'target': {'type': 'null'}}}},
    {'if': {'properties': {'decision': {'enum': ['CONTINUE', 'HANDOFF']}}},
     'then': {'properties': {'pending_points': {'minItems': 1}}}}
]
request['allOf'].append({
    'if': {'properties': {'allowed_decisions': {'contains': {'const':'NO_ACTION'}}}},
    'then': {'properties': {'allowed_decisions': {
        'minItems':3, 'maxItems':3,
        'items':{'enum':['EXPLAIN_LAW','NO_ACTION','HANDOFF']}
    }}}
})
output['allOf'].append({
    'if': {'properties': {'decision': {'const':'NO_ACTION'}}},
    'then': {'properties': {'speech':{'const':''}, 'pending_points':{'maxItems':0}}},
    'else': {'properties': {'speech': string(4000)}}
})
response = copy.deepcopy(output)
response['properties']['state_version'] = version
response['required'].append('state_version')
for name, schema in [('request', request), ('agent-output', output), ('response', response)]:
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['title'] = 'JudgeV2-' + name
    save('schemas/' + name + '.schema.json', schema)

save('limits.json', {
    'revision': '2026-09-12-legal-extension', 'request_body_max_bytes': 524288,
    'response_body_max_bytes': 131072, 'request_content_max_codepoints': 64000,
    'server_total_timeout_seconds': 120, 'client_timeout_seconds': 135,
    'max_output_repair_attempts': 1,
    'allowed_decisions_max_items': 5,
    'length_semantics': 'Unicode code points before trimming; only NO_ACTION.speech must be exactly empty; other whitespace-only text is invalid.',
    'content_budget_fields': 'All string leaves in case_context and records, plus current_issue.question.',
    'token_budget': 'Deployment must additionally check the actual model context window, including tool descriptions/calls/results and reserving prompt/schema/output tokens; do not truncate.'
})

blocks = [json.loads(s) for s in re.findall(r'```json\n(.*?)\n```',
    (ROOT / 'protocol-frozen.md').read_text(encoding='utf-8'), re.S)]
inq = next(d for d in blocks if isinstance(d, dict) and d.get('phase')=='INVESTIGATION' and 'NO_ACTION' not in d['allowed_decisions'])
deb = next(d for d in blocks if isinstance(d, dict) and d.get('phase')=='DEBATE')
responses = [d for d in blocks if isinstance(d, dict) and d.get('decision') in ('ASK','CONTINUE','COMPLETE','HANDOFF')]
cases = []
def case(name, kind, data, expected=True, request_data=None, reason=''):
    file = 'cases/' + name + '.json'
    save(file, data)
    entry = {'id': name, 'kind': kind, 'file': file, 'valid': expected}
    if request_data is not None:
        ref = 'contexts/' + name + '.json'
        save(ref, request_data)
        entry['request'] = ref
    if reason:
        entry['reason'] = reason
    cases.append(entry)

case('investigation-request', 'request', inq)
case('debate-request', 'request', deb)
for name, data in zip(['ask', 'investigation-complete', 'continue', 'debate-complete', 'handoff'], responses):
    req = copy.deepcopy(deb if name in ('continue', 'debate-complete') else inq)
    req['state_version'] = data['state_version']
    case(name + '-response', 'response', data, request_data=req)
    case(name + '-agent-output', 'agent-output', {k: v for k, v in data.items() if k != 'state_version'}, request_data=req)

def changed(data, key, value):
    d = copy.deepcopy(data)
    d[key] = value
    return d

case('empty-records', 'request', changed(inq, 'records', []))
case('summary-and-speech', 'request', changed(inq, 'records', blocks[1]))
case('over-thirty-records', 'request', changed(inq, 'records', inq['records'] * 55))
case('limit-reached', 'request', changed(deb, 'allowed_decisions', ['COMPLETE', 'HANDOFF']))
extended = changed(inq, 'allowed_targets', ['WITNESS'])
case('extended-role', 'request', extended)
case('extended-role-response', 'response', changed(responses[0], 'target', 'WITNESS'), request_data=extended)
case('record-role-not-target', 'request', changed(inq, 'records', [{'type':'SPEECH','role':'JUDGE','text':'法官问题。'}]))
case('missing-field', 'request', {k:v for k,v in inq.items() if k != 'allowed_targets'}, False, reason='schema')
case('legacy-task', 'request', {**inq, 'task':'旧任务'}, False, reason='schema')
case('cross-phase-request', 'request', changed(inq, 'allowed_decisions', ['CONTINUE','HANDOFF']), False, reason='schema')
case('missing-handoff', 'request', changed(inq, 'allowed_decisions', ['ASK']), False, reason='schema')
case('duplicate-targets', 'request', changed(inq, 'allowed_targets', ['PLAINTIFF','PLAINTIFF']), False, reason='schema')
case('ask-no-targets', 'request', changed(inq, 'allowed_targets', []), False, reason='schema')
case('debate-no-issue', 'request', changed(deb, 'current_issue', None), False, reason='schema')
case('debate-no-summary', 'request', changed(deb, 'case_context', inq['case_context']), False, reason='schema')
case('investigation-summary-forbidden', 'request', changed(inq, 'case_context', deb['case_context']), False, reason='schema')
case('evidence-summary-forbidden', 'request', changed(inq, 'case_context', {**inq['case_context'],'evidence_summary':'材料'}), False, reason='schema')
case('summary-role-forbidden', 'request', changed(inq, 'records', [{'type':'SUMMARY','role':'JUDGE','text':'摘要'}]), False, reason='schema')
case('unauthorized-target', 'response', changed(responses[0], 'target', 'WITNESS'), False, inq, 'target_not_allowed')
case('decision-not-allowed', 'response', responses[0], False, changed(inq,'allowed_decisions',['COMPLETE','HANDOFF']), 'decision_not_allowed')
case('cross-phase-response', 'response', responses[2], False, changed(inq,'state_version',35), 'decision_not_allowed')
case('stale-version', 'response', changed(responses[0], 'state_version', 19), False, inq, 'stale_state')
case('complete-target-forbidden', 'response', changed(responses[1], 'target','DEFENDANT'), False, reason='schema')
case('continue-no-points', 'response', changed(responses[2], 'pending_points',[]), False, reason='schema')
case('handoff-no-points', 'response', changed(responses[4], 'pending_points',[]), False, reason='schema')
case('blank-speech', 'response', changed(responses[0], 'speech','   '), False, reason='schema')
case('agent-generated-version', 'agent-output', responses[0], False, reason='schema')
case('speech-max', 'response', changed(responses[0], 'speech','述'*4000))
case('speech-over-max', 'response', changed(responses[0], 'speech','述'*4001), False, reason='schema')
case('unicode-codepoints', 'response', changed(responses[0], 'speech','😀'*4000))
case('records-max', 'request', changed(inq,'records',inq['records']*512))
case('records-over-max', 'request', changed(inq,'records',inq['records']*513), False, reason='schema')
for n in (64000,64001):
    d=copy.deepcopy(inq)
    d['case_context']={'summary':'述','claims':[],'defenses':[],'dispute_focuses':[]}
    remaining=n-1
    d['records']=[]
    while remaining:
        size=min(remaining,8000)
        # SPEECH and DEFENDANT strings also count toward the documented string-leaf budget.
        size=min(remaining-15,8000)
        d['records'].append({'type':'SPEECH','role':'DEFENDANT','text':'述'*size})
        remaining-=size+15
    case('content-budget-'+str(n),'request',d,n==64000,reason='' if n==64000 else 'content_budget')
case('negative-version', 'request', changed(inq,'state_version',-1), False, reason='schema')
case('boolean-version', 'request', changed(inq,'state_version',True), False, reason='schema')
case('string-version', 'request', changed(inq,'state_version','20'), False, reason='schema')
case('version-max', 'request', changed(inq,'state_version',9223372036854775807))
case('version-over-max', 'request', changed(inq,'state_version',9223372036854775808), False, reason='schema')
def raw_case(name, text, valid, reason=''):
    file='cases/'+name+'.json'
    (ROOT/file).write_text(text,encoding='utf-8')
    cases.append({'id':name,'kind':'request','file':file,'valid':valid,**({'reason':reason} if reason else {})})
encoded=json.dumps(inq,ensure_ascii=False)
raw_case('body-bytes-max',encoded+' '*(524288-len(encoded.encode('utf-8'))),True)
raw_case('body-bytes-over-max',encoded+' '*(524289-len(encoded.encode('utf-8'))),False,'body_size')
raw_case('markdown-fence','```json\n'+encoded+'\n```',False,'invalid_json')
raw_case('duplicate-key',encoded[:-1]+',"state_version":20}',False,'invalid_json')
# All legal assertions below are synthetic test data, not legal advice.
check = changed(inq, 'allowed_decisions', ['EXPLAIN_LAW','NO_ACTION','HANDOFF'])
check['records']=[{'type':'SPEECH','role':'DEFENDANT','text':'法官，请解释这项规定的法律依据和适用条件。'}]
deb_check = changed(deb, 'allowed_decisions', ['EXPLAIN_LAW','NO_ACTION','HANDOFF'])
deb_check['records']=[{'type':'SPEECH','role':'PLAINTIFF','text':'法官，请解释本争点涉及的法律规定。'}]
explain={'state_version':20,'decision':'EXPLAIN_LAW','target':None,'speech':'依照本次检索返回的测试条文A（虚构测试资料），适用条件为测试条件甲。这里只说明规则，不认定案件事实。','pending_points':[]}
no_action={'state_version':20,'decision':'NO_ACTION','target':None,'speech':'','pending_points':[]}
case('law-check-investigation','request',check)
case('law-check-debate-single-party','request',deb_check)
case('law-check-empty-targets','request',changed(check,'allowed_targets',[]))
case('law-check-reordered','request',changed(check,'allowed_decisions',['HANDOFF','NO_ACTION','EXPLAIN_LAW']))
case('law-check-completed-question-history','request',changed(check,'records',check['records']+[{'type':'SPEECH','role':'JUDGE','text':explain['speech']},{'type':'SPEECH','role':'DEFENDANT','text':'这个问题没有新的补充。'}]))
for phase, context in [('investigation',check),('debate',deb_check)]:
 for name,data in [('explain-law',explain),('no-action',no_action)]:
  current=changed(data,'state_version',context['state_version'])
  case(phase+'-'+name,'response',current,request_data=context)
  case(phase+'-'+name+'-agent','agent-output',{k:v for k,v in current.items() if k!='state_version'},request_data=context)
case('explain-at-investigation-progress','response',explain,request_data=inq)
case('explain-at-debate-progress','response',changed(explain,'state_version',deb['state_version']),request_data=deb)
case('law-check-mixed-ask','request',changed(check,'allowed_decisions',['EXPLAIN_LAW','NO_ACTION','HANDOFF','ASK']),False,reason='schema')
case('law-check-mixed-complete','request',changed(check,'allowed_decisions',['EXPLAIN_LAW','NO_ACTION','HANDOFF','COMPLETE']),False,reason='schema')
case('law-check-mixed-continue','request',changed(deb_check,'allowed_decisions',['EXPLAIN_LAW','NO_ACTION','HANDOFF','CONTINUE']),False,reason='schema')
case('law-check-no-explain','request',changed(check,'allowed_decisions',['NO_ACTION','HANDOFF']),False,reason='schema')
case('law-check-no-handoff','request',changed(check,'allowed_decisions',['EXPLAIN_LAW','NO_ACTION']),False,reason='schema')
case('law-check-duplicate','request',changed(check,'allowed_decisions',['NO_ACTION','NO_ACTION','HANDOFF']),False,reason='schema')
case('all-five-not-valid-check','request',changed(check,'allowed_decisions',['ASK','COMPLETE','HANDOFF','EXPLAIN_LAW','NO_ACTION']),False,reason='schema')
case('over-five-decisions','request',changed(check,'allowed_decisions',['ASK','CONTINUE','COMPLETE','HANDOFF','EXPLAIN_LAW','NO_ACTION']),False,reason='schema')
case('legal-question-field-forbidden','request',{**check,'legal_question':'不应新增此字段'},False,reason='schema')
case('law-check-debate-no-issue','request',changed(deb_check,'current_issue',None),False,reason='schema')
case('law-check-debate-no-investigation-summary','request',changed(deb_check,'case_context',inq['case_context']),False,reason='schema')
case('no-action-at-progress','response',no_action,False,inq,'decision_not_allowed')
case('explain-not-authorized','response',explain,False,changed(inq,'allowed_decisions',['COMPLETE','HANDOFF']),'decision_not_allowed')
case('complete-during-law-check','response',changed(responses[1],'state_version',20),False,check,'decision_not_allowed')
case('ask-during-law-check','response',responses[0],False,check,'decision_not_allowed')
for field,value in [('speech','不需要解释'),('speech',' '),('speech',None),('target','DEFENDANT'),('pending_points',['事项'])]:
 suffix='null' if value is None else ('space' if value==' ' else 'nonempty')
 case('no-action-'+field+'-'+suffix,'response',changed(no_action,field,value),False,reason='schema')
case('no-action-missing-speech','response',{k:v for k,v in no_action.items() if k!='speech'},False,reason='schema')
case('explain-empty','response',changed(explain,'speech',''),False,reason='schema')
case('explain-space','response',changed(explain,'speech',' '),False,reason='schema')
case('explain-target','response',changed(explain,'target','DEFENDANT'),False,reason='schema')
case('explain-max','response',changed(explain,'speech','述'*4000))
case('explain-over-max','response',changed(explain,'speech','述'*4001),False,reason='schema')
case('explain-unicode-max','response',changed(explain,'speech','😀'*4000))
case('explain-with-pending','response',changed(explain,'pending_points',['双方对事实仍有分歧，本次仅解释规则。']),request_data=check)
case('no-action-stale','response',changed(no_action,'state_version',19),False,check,'stale_state')
case('explain-agent-generated-version','agent-output',explain,False,reason='schema')
case('post-explanation-progress','request',changed(inq,'allowed_decisions',['ASK','COMPLETE','HANDOFF']))
case('round-limit-can-explain','request',changed(inq,'allowed_decisions',['COMPLETE','HANDOFF','EXPLAIN_LAW']))
save('manifest.json', {'revision':'2026-09-12-legal-extension','cases':cases})
print('Generated',len(cases),'contract cases')
