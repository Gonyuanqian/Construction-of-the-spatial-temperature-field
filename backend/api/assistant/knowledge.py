"""Qdrant adapter. The reviewed local release is authoritative, never vector payload text."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re

import httpx

from . import config


def setting(name, default=None):
    if name in os.environ:
        return os.environ[name]
    return config.knowledge_settings().get(name, default)


def release():
    path = setting('TFIELD_ASSISTANT_KNOWLEDGE_RELEASE')
    if not path:
        return None
    raw = Path(path).read_bytes()
    if len(raw) > 4_000_000:
        raise ValueError('知识发布清单过大')
    data = json.loads(raw)
    if not data.get('release_id') or not data.get('embedding_model'):
        raise ValueError('知识版本或嵌入模型未登记')
    seen = set()
    for item in data['chunks']:
        required = ('id', 'text', 'title', 'locator', 'reviewer', 'reviewed_at', 'crop', 'stage')
        if any(key not in item for key in required) or not all(item[key] for key in required[:6]):
            raise ValueError('知识单元缺少原文、出处或审核信息')
        if item['id'] in seen or len(item['text']) > 6000:
            raise ValueError('知识编号重复或证据单元过大')
        seen.add(item['id'])
        date.fromisoformat(item['reviewed_at'])
        for date_key in ('valid_from', 'valid_to'):
            if item.get(date_key):
                date.fromisoformat(item[date_key])
        if item.get('valid_from') and item.get('valid_to') and item['valid_from'] > item['valid_to']:
            raise ValueError('知识有效期起止错误')
    data['sha256'] = hashlib.sha256(raw).hexdigest()
    return data


def configured():
    return all(setting(k) for k in ('TFIELD_ASSISTANT_QDRANT_URL',
               'TFIELD_ASSISTANT_EMBEDDING_URL', 'TFIELD_ASSISTANT_KNOWLEDGE_RELEASE'))


def index_text(chunk):
    parts = [chunk['title'], chunk['text']]
    if chunk.get('usage_limitations'):
        parts.append('适用边界：' + '；'.join(chunk['usage_limitations']))
    return '\n'.join(parts)


def embedding(text, model, timeout, expected_revision=None):
    headers = {}
    if os.getenv('TFIELD_ASSISTANT_EMBEDDING_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['TFIELD_ASSISTANT_EMBEDDING_KEY']
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(setting('TFIELD_ASSISTANT_EMBEDDING_URL'), headers=headers,
                               json={'model': model, 'input': text})
        response.raise_for_status()
        body = response.json()
        if expected_revision and body.get('revision') != expected_revision:
            raise ValueError('嵌入服务修订与知识版本不一致，请使用匹配索引')
        if body.get('model', model) != model:
            raise ValueError('嵌入服务返回的模型名称不一致')
        vector = body['data'][0]['embedding']
    if not vector or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector):
        raise ValueError('嵌入结果无效')
    return vector


def search(query, crop, stage, timeout=10):
    if not configured():
        return {'status': 'not_configured', 'evidence': [], 'detail': '农业知识库尚未配置，不能提供农业阈值判断。'}
    catalog = release()  # Re-read on each search: withdrawn documents stop being returned.
    vector = embedding(query, catalog['embedding_model'], timeout, catalog.get('embedding_revision'))
    collection = setting('TFIELD_ASSISTANT_QDRANT_COLLECTION', 'agri_temperature')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', collection):
        raise ValueError('知识集合名称无效')
    headers = {'api-key': os.getenv('TFIELD_ASSISTANT_QDRANT_KEY', '')}
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(setting('TFIELD_ASSISTANT_QDRANT_URL').rstrip('/') +
                               f'/collections/{collection}/points/query', headers=headers,
                               json={'query': vector, 'limit': 20, 'with_payload': True,
                                     'filter': {'must': [{'key': 'release_id', 'match': {'value': catalog['release_id']}}]}})
        response.raise_for_status()
        hits = response.json()['result']['points']
    authoritative = {item['id']: item for item in catalog['chunks']}
    sources = {source['id']: source for source in catalog.get('sources', [])}
    evidence = []
    for hit in hits:
        item = authoritative.get(hit.get('payload', {}).get('chunk_id'))
        if not item or item.get('status') != 'published':
            continue
        today = date.today().isoformat()
        if item.get('valid_from', today) > today or item.get('valid_to', today) < today:
            continue
        if item['crop'] not in ('*', crop) or item['stage'] not in ('*', stage):
            continue
        if any(e['id'] == 'K:' + item['id'] for e in evidence):
            continue
        source = sources.get(item.get('source_id'), {})
        evidence.append(dict(item, id='K:' + item['id'], retrieval_score=hit.get('score'), source_title=source.get('title'),
                             source_url=source.get('url'), doi=source.get('doi'),
                             source_access=source.get('access'),
                             release_id=catalog['release_id'],
                             release_sha256=catalog['sha256']))
        if len(evidence) == catalog.get('context_limit', 6):
            break
    threshold = catalog.get('query_score_threshold')
    # Apply the query gate to eligible evidence, never to withdrawn or wrong-stage hits.
    if threshold is not None and (not evidence or evidence[0].get('retrieval_score', -1) < threshold):
        return {'status': 'no_evidence', 'evidence': [], 'release_id': catalog['release_id'],
                'release_sha256': catalog['sha256'], 'approved_scope': catalog.get('approved_scope'),
                'supports_numeric_thresholds': catalog.get('supports_numeric_thresholds'),
                'detail': '未检索到达到本版本相关性门槛的资料；相似度门槛不等于事实正确性。'}
    return {'status': 'ok' if evidence else 'no_evidence', 'evidence': evidence,
            'approved_scope': catalog.get('approved_scope'),
            'supports_numeric_thresholds': catalog.get('supports_numeric_thresholds'),
            'release_id': catalog['release_id'], 'release_sha256': catalog['sha256']}
