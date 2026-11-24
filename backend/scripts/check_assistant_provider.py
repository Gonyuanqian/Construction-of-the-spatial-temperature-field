"""Probe provider authentication and optionally exercise the real harness on non-project facts."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.assistant import config, runtime, store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-harness', action='store_true')
    args = parser.parse_args()
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get('https://api.deepseek.com/models',
                              headers={'Authorization': 'Bearer ' + config.api_key()})
    print(json.dumps({'authentication_status': response.status_code,
                      'models': [m['id'] for m in response.json().get('data', [])]
                      if response.status_code == 200 else []}))
    if response.status_code != 200 or not args.run_harness:
        return
    # Materialize credentials before switching the isolated journal root.
    import os
    os.environ['DEEPSEEK_API_KEY'] = config.api_key()
    original = store.paths.PROJECT
    root = original / '.local/assistant'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='smoke-', dir=root) as temp:
        store.paths.PROJECT = Path(temp)
        try:
            snapshot = store.snapshot({'source_time': 'validation fixture; no live data',
                'facts': [{'id': 'F:context', 'text': '这是接口验证夹具，不含现场温度或农业知识。'},
                          {'id': 'F:limitations', 'text': '没有作物、生育期、实测温度或审核阈值，不能判断作物是否适温。'}]})
            run, _ = store.create_run(str(uuid4()), {'snapshot_id': snapshot['snapshot_id'],
                'question': '当前资料能判断番茄是否适温吗？请只说明已有依据与缺失条件。'})
            runner = runtime.Runner(run)
            try:
                result = runner.execute()
                report = {'status': result['status'], 'cycles': store.get_run(run['id'])['cycle'],
                          'evaluations': runner.evaluations, 'model_calls': runner.calls,
                          'tool_calls': runner.tool_calls, 'tokens': runner.tokens,
                          'claims': result['result']['claims']}
            except Exception as exc:
                report = {'status': 'failed', 'error_type': type(exc).__name__,
                          'failure_reason': str(exc)[:300] if isinstance(exc, ValueError) else type(exc).__name__,
                          'last_evaluation': store.get_run(run['id']).get('last_evaluation'),
                          'cycles': store.get_run(run['id'])['cycle'],
                          'evaluations': runner.evaluations, 'model_calls': runner.calls,
                          'tokens': runner.tokens}
        finally:
            store.paths.PROJECT = original
    (root / 'provider-smoke-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
