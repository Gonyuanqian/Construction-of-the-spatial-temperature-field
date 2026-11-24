"""Frozen-corpus retrieval evaluation; no LLM calls and no claim of answer correctness."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from api.assistant import knowledge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', action='store_true')
    parser.add_argument('--version', choices=['v1','v2','v3'], default='v3')
    args = parser.parse_args()
    base = ROOT / 'knowledge/agri-temperature'
    release_path = base / f'releases/agri-temperature-qualitative-20261030-{args.version}.json'
    benchmark_path = base / 'benchmark-v1.json'
    os.environ.update(TFIELD_ASSISTANT_KNOWLEDGE_RELEASE=str(release_path),
        TFIELD_ASSISTANT_QDRANT_URL='http://127.0.0.1:6333',
        TFIELD_ASSISTANT_EMBEDDING_URL='http://127.0.0.1:8001/v1/embeddings',
        TFIELD_ASSISTANT_QDRANT_COLLECTION='agri_temperature_qualitative_20261030_'+args.version,
        NO_PROXY=os.environ.get('NO_PROXY', '')+',127.0.0.1,localhost', PYTHONUTF8='1')
    collection = os.environ['TFIELD_ASSISTANT_QDRANT_COLLECTION']
    if args.index:
        subprocess.run([sys.executable, str(ROOT/'backend/scripts/publish_assistant_knowledge.py'),
                        '--release', str(release_path)], check=True, timeout=180)
    catalog = knowledge.release()
    benchmark = json.loads(benchmark_path.read_text(encoding='utf-8'))
    authoritative = {c['id']: c for c in catalog['chunks']}
    rows = []
    # Development cases occur first; holdout labels are never used to select thresholds here.
    for case in benchmark['cases']:
        started = time.perf_counter()
        result = knowledge.search(case['question'], case.get('crop'), case.get('stage'), timeout=30)
        elapsed = time.perf_counter()-started
        evidence = result['evidence']
        ids = [e['id'].removeprefix('K:') for e in evidence]
        gold = set(case['gold_ids'])
        rank = next((i+1 for i, identifier in enumerate(ids) if identifier in gold), None)
        valid = all(e['id'].removeprefix('K:') in authoritative and e.get('source_url') and
                    e.get('source_title') and e.get('locator') and e['release_sha256'] == catalog['sha256']
                    for e in evidence)
        rows.append(dict(case, retrieved_ids=ids, scores=[e.get('retrieval_score') for e in evidence],
                         reciprocal_rank=1/rank if rank else 0, gold_rank=rank,
                         citation_metadata_valid=bool(valid), latency_seconds=round(elapsed,4),
                         retrieved_context_is_sufficient=bool(gold and rank),
                         numeric_threshold_support=result.get('supports_numeric_thresholds')))
    summaries = {}
    for split in ('development','holdout'):
        positive = [r for r in rows if r['split']==split and r['gold_ids']]
        negative = [r for r in rows if r['split']==split and not r['gold_ids']]
        summary = {'answerable_count':len(positive), 'unanswerable_count':len(negative)}
        for k in (1,3,6):
            summary[f'hit_rate_at_{k}'] = sum(bool(r['gold_rank'] and r['gold_rank']<=k) for r in positive)/len(positive)
        summary['mrr'] = statistics.mean(r['reciprocal_rank'] for r in positive)
        summary['unanswerable_queries_returning_related_context'] = sum(bool(r['retrieved_ids']) for r in negative)
        summary['unanswerable_query_rejection_rate'] = sum(not r['retrieved_ids'] for r in negative)/len(negative)
        summary['interpretation'] = '有相关资料不等于问题可回答；不可回答标签按证据支持范围人工标注，未测试最终生成答案。'
        summaries[split] = summary
    with httpx.Client(timeout=10, trust_env=False) as client:
        info = client.get(f'http://127.0.0.1:6333/collections/{collection}')
        info.raise_for_status()
        points = info.json()['result']['points_count']
    checks = dict(all_published_qualitative=all(c['status']=='published' and c['evidence_kind']=='qualitative' for c in catalog['chunks']),
        source_count=len(catalog['sources'])==4, index_count_matches=points==len(catalog['chunks']),
        citation_metadata_valid=all(r['citation_metadata_valid'] for r in rows),
        no_numeric_thresholds_advertised=all(r['numeric_threshold_support'] is False for r in rows),
        holdout_hit_rate_at_3=summaries['holdout']['hit_rate_at_3']>=.9)
    report = dict(benchmark_version=benchmark['version'], benchmark_sha256=hashlib.sha256(benchmark_path.read_bytes()).hexdigest(),
        release_id=catalog['release_id'], release_sha256=catalog['sha256'], collection=collection,
        indexing_policy='title_body_limits-v1', embedding_model=catalog['embedding_model'],
        embedding_revision=catalog['embedding_revision'], points=points,
        metrics=summaries, checks=checks, passed=all(checks.values()),
        p50_latency_seconds=statistics.median(r['latency_seconds'] for r in rows),
        limitations=benchmark['limitations'], rows=rows)
    folder = base / 'evaluations'
    folder.mkdir(exist_ok=True)
    output = folder / f'retrieval-{args.version}.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}, ensure_ascii=True,indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
