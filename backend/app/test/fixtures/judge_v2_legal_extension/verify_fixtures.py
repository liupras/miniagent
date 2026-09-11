"""Offline contract oracle for M0; not proof that either V2 implementation exists."""
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent

def read(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:
                raise ValueError('duplicate key')
            result[k]=v
        return result
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)

def content_size(value):
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(map(content_size, value.values()))
    if isinstance(value, list):
        return sum(map(content_size, value))
    return 0

def main():
    limits = read(ROOT / 'limits.json')
    validators = {}
    for kind in ('request','response','agent-output'):
        schema = read(ROOT / f'schemas/{kind}.schema.json')
        Draft202012Validator.check_schema(schema)
        validators[kind] = Draft202012Validator(schema)
    results = []
    for case in read(ROOT / 'manifest.json')['cases']:
        path = ROOT / case['file']
        kind = case['kind']
        try:
            data = read(path)
            errors = list(validators[kind].iter_errors(data))
            reason = 'schema' if errors else ''
        except ValueError:
            reason = 'invalid_json'
        if not reason:
            size_limit = limits['request_body_max_bytes' if kind=='request' else 'response_body_max_bytes']
            if path.stat().st_size > size_limit:
                reason = 'body_size'
            elif kind=='request':
                size = content_size(data['case_context']) + content_size(data['records'])
                size += len((data['current_issue'] or {}).get('question',''))
                if size > limits['request_content_max_codepoints']:
                    reason = 'content_budget'
            elif 'request' in case:
                request = read(ROOT / case['request'])
                validators['request'].validate(request)
                if data['decision'] not in request['allowed_decisions']:
                    reason = 'decision_not_allowed'
                elif data['decision']=='ASK' and data['target'] not in request['allowed_targets']:
                    reason = 'target_not_allowed'
                elif kind=='response' and data['state_version'] != request['state_version']:
                    reason = 'stale_state'
        passed = (not reason)==case['valid'] and (not case.get('reason') or reason==case['reason'])
        results.append({'id':case['id'],'passed':passed,'actual_reason':reason})
    failed = [r for r in results if not r['passed']]
    integrity=ROOT/'integrity.json'
    if integrity.exists():
        for file, expected in read(integrity).items():
            actual=hashlib.sha256((ROOT/file).read_bytes()).hexdigest()
            if actual!=expected:
                failed.append({'id':'integrity:'+file,'passed':False})
    print(json.dumps({'total':len(results),'passed':len(results)-len(failed),'failures':failed},ensure_ascii=False,indent=2))
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
