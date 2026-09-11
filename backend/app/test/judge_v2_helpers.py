import json
from pathlib import Path
ROOT = Path(__file__).parent / 'fixtures/judge_v2_legal_extension'
def load(file): return json.loads((ROOT/file).read_text(encoding='utf-8'))
def request_data(phase='INVESTIGATION'):
    return load('cases/'+('investigation' if phase=='INVESTIGATION' else 'debate')+'-request.json')
def output(): return load('cases/ask-agent-output.json')
