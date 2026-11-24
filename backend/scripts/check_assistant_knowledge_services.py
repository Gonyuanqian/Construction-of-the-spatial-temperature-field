"""Exercise real local embeddings, Qdrant persistence and the production retrieval adapter.

All writes use a uniquely named test collection and synthetic non-agronomic facts.
No literature approval is granted and no production release is changed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.assistant import knowledge

ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / '.local/assistant/services'


def wait_ready(client):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if client.get('http://127.0.0.1:6333/', timeout=2).status_code == 200 and \
               client.get('http://127.0.0.1:8001/health', timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError('Local services were not ready within 120 seconds; inspect service logs.')


def verify_restart():
    path = SERVICE_ROOT / 'integration-result.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    with httpx.Client(timeout=10, trust_env=False) as client:
        wait_ready(client)
        result = client.get(f'http://127.0.0.1:6333/collections/{report["collection"]}')
        result.raise_for_status()
        report['persisted_points_after_restart'] = result.json()['result']['points_count']
        report['checks']['persistence_after_service_restart'] = report['persisted_points_after_restart'] == 3
        report['checks']['embedding_ready_after_restart'] = client.get('http://127.0.0.1:8001/health').status_code == 200
        wrong = client.post(f'http://127.0.0.1:6333/collections/{report["collection"]}/points/query',
                            json={'query': [1.0, 0.0], 'limit': 1})
        report['checks']['wrong_vector_dimension_rejected'] = wrong.status_code == 400
    report['passed'] = all(report['checks'].values())
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not report['passed']:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-restart', action='store_true')
    args = parser.parse_args()
    if args.verify_restart:
        return verify_restart()
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'checks': {}, 'kind': 'integration_fixture'}
    collection = 'assistant_integration_' + uuid4().hex[:12]
    work = SERVICE_ROOT / 'checks' / collection
    work.mkdir(parents=True, exist_ok=False)
    with httpx.Client(timeout=30, trust_env=False) as client:
        wait_ready(client)
        qdrant = client.get('http://127.0.0.1:6333/'); qdrant.raise_for_status()
        health = client.get('http://127.0.0.1:8001/health'); health.raise_for_status()
        report['qdrant'] = qdrant.json()
        report['embedding'] = health.json()
        model_id = health.json()['model_id']
        request = {'model': model_id, 'input': ['蓝色盒子存放铅笔。', '红色盒子存放橡皮。']}
        started = time.perf_counter()
        vectors = client.post('http://127.0.0.1:8001/v1/embeddings', json=request)
        vectors.raise_for_status()
        report['embedding_batch_seconds'] = round(time.perf_counter()-started, 3)
        rows = vectors.json()['data']
        dimension = health.json()['dimension']
        report['checks']['finite_normalized_vectors'] = len(rows) == 2 and all(
            len(row['embedding']) == dimension and all(math.isfinite(v) for v in row['embedding']) and
            abs(sum(v*v for v in row['embedding'])-1) < 1e-4 for row in rows)
        again = client.post('http://127.0.0.1:8001/v1/embeddings', json={'model': model_id, 'input': request['input'][0]})
        again.raise_for_status()
        report['checks']['deterministic_embeddings'] = max(abs(a-b) for a,b in zip(
            rows[0]['embedding'], again.json()['data'][0]['embedding'])) < 1e-5
        wrong = client.post('http://127.0.0.1:8001/v1/embeddings', json={'model': 'wrong-model', 'input': 'test'})
        report['checks']['wrong_model_rejected'] = wrong.status_code == 422
        empty = client.post('http://127.0.0.1:8001/v1/embeddings', json={'model': model_id, 'input': ''})
        report['checks']['empty_input_rejected'] = empty.status_code == 422
        long_text = client.post('http://127.0.0.1:8001/v1/embeddings', json={'model': model_id, 'input': '温度'*1000})
        report['checks']['overlength_not_truncated'] = long_text.status_code == 422

    base = {'title': '服务联调夹具，非农业资料', 'locator': 'synthetic fixture',
            'reviewer': 'engineering test fixture only', 'reviewed_at': datetime.now().date().isoformat(),
            'crop': '*', 'stage': '*', 'status': 'published'}
    chunks = [dict(base, id='blue', text='蓝色盒子存放铅笔。'),
              dict(base, id='red', text='红色盒子存放橡皮。'),
              dict(base, id='crop-specific', text='测试作物甲的专属测试资料。', crop='测试作物甲')]
    release = {'release_id': collection, 'embedding_model': model_id, 'chunks': chunks}
    path = work / 'release.json'
    path.write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding='utf-8')
    os.environ.update(TFIELD_ASSISTANT_KNOWLEDGE_RELEASE=str(path),
        TFIELD_ASSISTANT_QDRANT_URL='http://127.0.0.1:6333',
        TFIELD_ASSISTANT_EMBEDDING_URL='http://127.0.0.1:8001/v1/embeddings',
        TFIELD_ASSISTANT_QDRANT_COLLECTION=collection)
    # Local services must not go through a user's external proxy.
    os.environ['NO_PROXY'] = os.environ.get('NO_PROXY', '') + ',127.0.0.1,localhost'
    os.environ['PYTHONUTF8'] = '1'
    command = [sys.executable, str(ROOT / 'backend/scripts/publish_assistant_knowledge.py'), '--release', str(path)]
    publish = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    report['checks']['actual_publisher_succeeds'] = publish.returncode == 0
    if publish.returncode:
        raise RuntimeError(publish.stderr[-1500:])
    result = knowledge.search('蓝色盒子里放的是什么？', None, None, timeout=30)
    ids = [item['id'] for item in result['evidence']]
    report['checks']['semantic_retrieval'] = bool(ids) and ids[0] == 'K:blue'
    report['checks']['crop_condition_filter'] = 'K:crop-specific' not in ids
    report['retrieved_ids'] = ids
    # Withdraw in the authority catalog while deliberately retaining the Qdrant point.
    release['chunks'][0]['status'] = 'withdrawn'
    release['chunks'][1]['status'] = 'draft'
    path.write_text(json.dumps(release, ensure_ascii=False), encoding='utf-8')
    removed = knowledge.search('蓝色盒子里放的是什么？', None, None, timeout=30)
    report['checks']['withdrawal_and_draft_gate'] = removed['evidence'] == []
    # A publisher must refuse the real draft literature without creating/promoting a collection.
    refused = subprocess.run([sys.executable, str(ROOT / 'backend/scripts/publish_assistant_knowledge.py'),
        '--release', str(ROOT / 'knowledge/agri-temperature/literature-seed-v1.json')],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    report['checks']['real_literature_drafts_rejected'] = refused.returncode == 2 and '没有已审核发布的知识单元' in refused.stderr
    with httpx.Client(timeout=10, trust_env=False) as client:
        mismatch = client.post(f'http://127.0.0.1:6333/collections/{collection}/points/query',
                               json={'query': [1.0, 0.0], 'limit': 1})
        report['checks']['wrong_vector_dimension_rejected'] = mismatch.status_code == 400
    report.update(collection=collection, release_path=str(path), passed=all(report['checks'].values()))
    destination = SERVICE_ROOT / 'integration-result.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
