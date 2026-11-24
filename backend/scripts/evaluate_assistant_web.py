"""Live public-literature acceptance in an isolated conversation DB (no greenhouse observations)."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from api.assistant import config, knowledge, runtime, store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empty-local', action='store_true', help='Simulate a local miss without changing Qdrant')
    parser.add_argument('--report', choices=('web-live-auto', 'web-live-explicit', 'protocol-live'))
    parser.add_argument('--question', default='温室昼夜温差 DIF 为什么会影响植株株高？请说明原理，不给设备设定值。')
    args = parser.parse_args()
    os.environ['DEEPSEEK_API_KEY'] = config.api_key()
    for name, value in config.knowledge_settings().items(): os.environ.setdefault(name, value)
    folder = ROOT / '.local/assistant'
    folder.mkdir(parents=True, exist_ok=True)
    original_project, original_search = store.paths.PROJECT, knowledge.search
    if args.empty_local:
        knowledge.search = lambda *a, **k: {'status': 'no_evidence', 'evidence': [], 'detail': 'Acceptance fixture: local miss.'}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='web-acceptance-', dir=folder) as temporary:
            store.paths.PROJECT = Path(temporary)
            run = store.create_run(str(uuid4()), {'conversation_id': str(uuid4()), 'question': args.question,
                                                 'web_search_enabled': True})[0]
            runner = runtime.Runner(run)
            try:
                out = runner.execute()
            except Exception as exc:
                code = exc.code if isinstance(exc, runtime.ModelProtocolError) else str(exc) if isinstance(exc, runtime.BudgetExceeded) else type(exc).__name__
                out = runner.failure('联网验收未完成。', code)
            record = store.get_run(run['id'])
            citations = (out.get('result') or {}).get('citations', [])
            report = {'question': args.question, 'local_miss_fixture': args.empty_local,
                'status': out['status'], 'error_code': out.get('error_code'),
                'elapsed_seconds': round(time.monotonic()-started, 2),
                'search_calls': runner.online.search_calls, 'read_calls': runner.online.read_calls,
                'evaluations': runner.evaluations, 'model_calls': runner.calls, 'protocol_repairs': runner.protocol_repairs,
                'answer_plan': record.get('answer_plan'),
                'thinking': record.get('thinking'),
                'passed': out['status'] == 'answered' and runner.evaluations >= 2 and (args.report == 'protocol-live' or any(e['id'].startswith('W:') for e in citations)),
                'sources': [{'id': e['id'], 'url': e.get('source_url'), 'review_status': e.get('review_status')} for e in citations],
                'last_evaluation': record.get('last_evaluation'), 'output': out,
                'limitations': 'Public web and model test; does not certify agronomic advice or external source accuracy.'}
    finally:
        store.paths.PROJECT, knowledge.search = original_project, original_search
    target = folder / ((args.report or ('web-live-auto' if args.empty_local else 'web-live-explicit')) + '.json')
    if target.exists(): target.with_name(target.stem+'-'+str(time.time_ns())+'.json').write_bytes(target.read_bytes())
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('output', 'last_evaluation')}, ensure_ascii=True), flush=True)
    print('REPORT', target, flush=True)


if __name__ == '__main__': main()
