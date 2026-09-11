"""Capture allowlisted configuration and source identities; application DB is read-only."""
import hashlib
import importlib.metadata
import json
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
BACKEND=Path('D:/miniagent/backend')
OUT=PROJECT/'Tests/Results/JudgeV2LegalBaseline'
OUT.mkdir(parents=True,exist_ok=True)

def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(root,*args):
    return subprocess.check_output(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),*args],text=True,encoding='utf-8').strip()

snapshot={'captured_at':datetime.now(timezone.utc).isoformat(),'repositories':[]}
snapshot['test_runtime']={'python':__import__('sys').version,
    'packages':{name:importlib.metadata.version(name) for name in ('pytest','jsonschema','pydantic')},
    'unity':(PROJECT/'ProjectSettings/ProjectVersion.txt').read_text(encoding='utf-8').strip()}
for root in (PROJECT,BACKEND.parent):
    snapshot['repositories'].append({'path':str(root),'head':git(root,'rev-parse','HEAD'),
                                    'status':git(root,'status','--short')})
files=[PROJECT/'Tests/Manual/request.json',PROJECT/'Tests/Manual/response.json',
       PROJECT/'Docs/judge_protocol_v2.md',PROJECT/'Docs/judge_protocol_v2_implementation_plan.md',
       PROJECT/'Assets/StreamingAssets/judge-task-prompts.json',
       BACKEND/'app/infra/db/seed/agent.json',BACKEND/'app/services/virtual_court/judge_service.py']
snapshot['files']=[{'path':str(p),'sha256':sha(p)} for p in files]
settings=json.loads((PROJECT/'Assets/StreamingAssets/virtual-court-settings.json').read_text(encoding='utf-8-sig'))
snapshot['client_judge_configuration']={k:v for k,v in settings['judge'].items()
    if k in ('apiUrl','timeoutSeconds','maxTotalRounds','maxInquiryRounds','maxDebateRoundsPerIssue')}
snapshot['backend_dotenv_configuration']={}
for line in (BACKEND/'.env').read_text(encoding='utf-8-sig').splitlines():
    key,sep,value=line.partition('=')
    if sep and key.strip() in ('API_PORT','VIRTUAL_COURT_JUDGE_TIMEOUT_SECONDS'):
        snapshot['backend_dotenv_configuration'][key.strip()]=value.strip()
snapshot['configuration_note']='File/DB snapshot only; process environment overrides and loaded runtime caches not verified. No credentials or LLM endpoints exported.'

db=sqlite3.connect((BACKEND/'db/sqlite/miniagent.db').as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
agents=[dict(r) for r in db.execute("SELECT id,name,system_prompt,llm_id,max_output_tokens,is_active FROM agents WHERE name IN ('virtual_court_solo_judge','virtual_court_investigation_judge','virtual_court_debate_judge') ORDER BY name")]
for a in agents:
    a['system_prompt_sha256']=hashlib.sha256(a['system_prompt'].encode()).hexdigest()
    a['llm']=dict(db.execute('SELECT name,model_name,temperature,max_output_tokens FROM llms WHERE id=?',(a['llm_id'],)).fetchone()) if a['llm_id'] else None
    a['tools']=[dict(r) for r in db.execute('SELECT t.name FROM tools t JOIN agent_tool_relations r ON r.tool_id=t.id WHERE r.agent_id=? ORDER BY t.name',(a['id'],))]
db.close()
write('current-agent-configuration.json',agents)
snapshot['agent_configuration_sha256']=sha(OUT/'current-agent-configuration.json')
tests={}
for name in ('backend-current','unity-current'):
    tree=ET.parse(OUT/(name+'.xml')).getroot()
    if name=='backend-current':
        suite=tree.find('testsuite')
        failures=[{'name':t.attrib['name'],'class':t.attrib.get('classname'),
                   'message':t.find('failure').attrib.get('message','')} for t in tree.iter('testcase') if t.find('failure') is not None]
        tests[name]={'summary':suite.attrib,'failures':failures}
    else:
        tests[name]={'summary':tree.attrib}
write('test-summary.json',tests)
old=json.loads((PROJECT/'Tests/Manual/request.json').read_text(encoding='utf-8-sig'))
rounds=snapshot['client_judge_configuration']
fixture=json.loads((ROOT/'cases/investigation-request.json').read_text(encoding='utf-8'))
fixture['case_context']={k:old['case_context'][k] for k in ('summary','claims','defenses','dispute_focuses')}
fixture['records']=[{'type':'SPEECH','role':r['actor'],'text':r['content']} for r in old['recent_events']]
inquiry=rounds['maxInquiryRounds']
base=len(fixture['records'])
for i in range(inquiry):
    fixture['records'] += [{'type':'SPEECH','role':'JUDGE','text':f'第{i+1}轮：请说明相关情况。'},
                           {'type':'SPEECH','role':'DEFENDANT','text':'本轮回答：相关情况如前所述。'}]
measure={'source':'Current manual request mapped without evidence_summary; synthetic additional rounds, not real history.',
         'source_records':base,'configured_max_inquiry_rounds':inquiry,
         'inquiry_records_at_round_limit':len(fixture['records']),
         'inquiry_compact_utf8_bytes':len(json.dumps(fixture,ensure_ascii=False,separators=(',',':')).encode()),
         'max_current_issue_rounds':rounds['maxDebateRoundsPerIssue'],
         'current_issue_records_with_two_prompts_two_speeches_per_round':4*rounds['maxDebateRoundsPerIssue'],
         'configured_total_rounds':rounds['maxTotalRounds'],
         'note':'Counts demonstrate why 30-record truncation is insufficient; worst-case long speech uses separate aggregate budget, not guaranteed to fit.'}
write('measurement.json',measure)
# HEAD alone is insufficient while backend M1 is still uncommitted.
for relative in git(BACKEND.parent,'diff','--name-only','HEAD').splitlines():
    path=BACKEND.parent/relative
    if path.is_file() and path.suffix in ('.py','.json','.yaml'):
        snapshot['files'].append({'path':str(path),'sha256':sha(path)})
write('source-and-config.json',snapshot)
print('Captured current sources, read-only configuration and separate legal-extension baseline.')
