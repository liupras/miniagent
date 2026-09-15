"""Run sanitized Judge V2 acceptance probes against a live MiniAgent server."""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


ROOT = (
    Path(__file__).resolve().parents[1]
    / 'app'
    / 'test'
    / 'fixtures'
    / 'judge_v2_split_endpoints'
)


def fixture(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def post(base_url, path, payload, *, timeout=140):
    raw = (
        payload
        if isinstance(payload, bytes)
        else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    )
    request = urllib.request.Request(
        base_url.rstrip('/') + path,
        data=raw,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Integration-Key': settings.virtual_court_api_key.get_secret_value(),
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = json.loads(exc.read().decode('utf-8'))
    elapsed = round(time.perf_counter() - started, 3)
    return {
        'status': status,
        'decision': body.get('decision'),
        'error_code': body.get('error', {}).get('code'),
        'error_reason': body.get('error', {}).get('details', {}).get('reason'),
        'state_version': body.get('state_version'),
        'response_fields': sorted(body),
        'elapsed_seconds': elapsed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:10088')
    args = parser.parse_args()

    law_path = '/api/v2/integrations/virtual-court/judge/law-check'
    next_path = '/api/v2/integrations/virtual-court/judge/next-action'
    probes = {
        'ordinary_statement': {
            'state_version': 801,
            'role': 'PLAINTIFF',
            'text': '我方维持此前意见。',
            'context': '当前争点：涉案图片的商业使用是否构成侵权。',
        },
        'negated_legal_words': {
            'state_version': 802,
            'role': 'DEFENDANT',
            'text': '我没有法律问题需要解释，也不要求说明任何依据。',
            'context': '',
        },
        'question_only_in_context': {
            'state_version': 803,
            'role': 'PLAINTIFF',
            'text': '我方维持此前陈述。',
            'context': '公开下载的图片为什么不能用于商业宣传，法律依据是什么？',
        },
        'explicit_legal_question': {
            'state_version': 804,
            'role': 'DEFENDANT',
            'text': '图片可以公开下载，为什么不能用于商业宣传？法律依据是什么？',
            'context': '当前争点：涉案图片的商业使用是否构成侵权。',
        },
        'deny_old_then_new_question': {
            'state_version': 805,
            'role': 'PLAINTIFF',
            'text': '我不再问赔偿计算问题。但请解释未经许可把摄影作品用于广告，法律依据是什么？',
            'context': '当前争点：作品商业使用的授权范围。',
        },
        'out_of_domain_empty_search': {
            'state_version': 806,
            'role': 'DEFENDANT',
            'text': '请解释海商法共同海损中牺牲金额分摊的具体法律依据。',
            'context': '当前知识库仅包含知识产权资料。',
        },
    }

    results = {}
    for name, payload in probes.items():
        results[name] = post(args.base_url, law_path, payload)

    results['investigation_action'] = post(
        args.base_url,
        next_path,
        fixture('cases/next-investigation-request.json'),
    )
    results['overlong_text'] = post(
        args.base_url,
        law_path,
        {
            'state_version': 809,
            'role': 'PLAINTIFF',
            'text': '法' * 8001,
        },
    )
    results['oversized_body'] = post(
        args.base_url,
        law_path,
        (ROOT / 'cases' / 'law-body-over-max.json').read_bytes(),
    )

    concurrent_payloads = [
        {
            'state_version': 820 + index,
            'role': 'PLAINTIFF' if index % 2 == 0 else 'DEFENDANT',
            'text': f'第 {index + 1} 条普通陈述，我方没有新的问题。',
            'context': '',
        }
        for index in range(3)
    ]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as executor:
        concurrent_results = list(executor.map(
            lambda payload: post(args.base_url, law_path, payload),
            concurrent_payloads,
        ))
    results['concurrency'] = {
        'requests': concurrent_results,
        'wall_seconds': round(time.perf_counter() - started, 3),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
