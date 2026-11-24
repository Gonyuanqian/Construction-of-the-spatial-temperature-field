"""Materialize the explicitly reviewed qualitative release without altering original drafts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'knowledge/agri-temperature'


def main():
    seed_path = BASE / 'literature-seed-v1.json'
    review_path = BASE / 'review-v1.json'
    seed = json.loads(seed_path.read_text(encoding='utf-8'))
    review = json.loads(review_path.read_text(encoding='utf-8'))
    originals = {c['id']: c for c in seed['chunks']}
    if {d['id'] for d in review['decisions']} != set(originals):
        raise ValueError('Every original unit must have an explicit decision')
    chunks = []
    for decision in review['decisions']:
        if decision['decision'] != 'publish':
            continue
        chunk = dict(originals[decision['id']], text=decision['text'], status='published',
            review_status='source_verified_qualitative', reviewer=review['reviewer'],
            reviewed_at=review['reviewed_at'], review_basis=decision['basis'],
            usage_limitations=decision['limits'], evidence_kind='qualitative',
            can_support_numeric_thresholds=False)
        if chunk['id'] == 'GUZMAN2019-virtual-sensing':
            chunk['locator'] = 'Publisher PDF pp.2–3, Sections 1–2'
        if chunk['id'] == 'GUZMAN2019-transfer-limit':
            chunk['locator'] = 'Publisher PDF p.3, Section 1, final paragraph'
        chunks.append(chunk)
    used = {c['source_id'] for c in chunks}
    data = dict(release_id='agri-temperature-qualitative-20261030-v1', status='published',
        embedding_model='BAAI/bge-small-zh-v1.5', embedding_dimension=512,
        embedding_revision='7999e1d3359715c523056ef9478215996d62a620',
        approved_scope=review['approved_scope'], supports_numeric_thresholds=False,
        query_score_threshold=None,
        review_sha256=hashlib.sha256(review_path.read_bytes()).hexdigest(),
        seed_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
        sources=[s for s in seed['sources'] if s['id'] in used], chunks=chunks)
    output = BASE / 'releases' / (data['release_id'] + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if output.exists() and output.read_text(encoding='utf-8') != content:
        raise ValueError('Release already exists with different content; create a new version')
    output.write_text(content, encoding='utf-8')
    print(f'Release {data["release_id"]}: {len(chunks)} units from {len(used)} sources')


if __name__ == '__main__':
    main()
