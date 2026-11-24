"""Index an already reviewed release. Never generates or approves agricultural knowledge."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.assistant import knowledge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    args = parser.parse_args()
    os.environ['TFIELD_ASSISTANT_KNOWLEDGE_RELEASE'] = str(args.release.resolve())
    catalog = knowledge.release()
    if not knowledge.configured():
        parser.error('请配置 Qdrant 和兼容 /embeddings 的嵌入服务端点。')
    chunks = [c for c in catalog['chunks'] if c.get('status') == 'published']
    if not chunks:
        parser.error('没有已审核发布的知识单元，未创建空索引。')
    collection = knowledge.setting('TFIELD_ASSISTANT_QDRANT_COLLECTION', 'agri_temperature')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', collection):
        parser.error('知识集合名称无效')
    points = []
    for chunk in chunks:
        vector = knowledge.embedding(knowledge.index_text(chunk), catalog['embedding_model'], 30,
                                     catalog.get('embedding_revision'))
        points.append({'id': str(uuid5(NAMESPACE_URL, catalog['release_id'] + ':' + chunk['id'])),
                       'vector': vector, 'payload': {'chunk_id': chunk['id'], 'release_id': catalog['release_id'],
                           'embedding_revision': catalog.get('embedding_revision'),
                           'indexing_policy': 'title_body_limits-v1'}})
    sizes = {len(p['vector']) for p in points}
    if len(sizes) != 1:
        raise ValueError('嵌入维数不一致，未写入数据库')
    url = knowledge.setting('TFIELD_ASSISTANT_QDRANT_URL').rstrip('/') + '/collections/' + collection
    with httpx.Client(timeout=30, follow_redirects=False, headers={
            'api-key': os.getenv('TFIELD_ASSISTANT_QDRANT_KEY', '')}) as client:
        existing = client.get(url)
        if existing.status_code == 404:
            response = client.put(url, json={'vectors': {'size': sizes.pop(), 'distance': 'Cosine'}})
            response.raise_for_status()
        else:
            existing.raise_for_status()
            if existing.json()['result']['config']['params']['vectors']['size'] not in sizes:
                raise ValueError('已有集合向量维数不匹配，请使用新集合重建索引')
        response = client.put(url + '/points?wait=true', json={'points': points})
        response.raise_for_status()
    print(f'已索引 {len(points)} 个审核单元，版本 {catalog["release_id"]}。')
    print('完成检索验收后，在服务进程中设置 TFIELD_ASSISTANT_KNOWLEDGE_RELEASE 指向该版本清单。')


if __name__ == '__main__':
    main()
