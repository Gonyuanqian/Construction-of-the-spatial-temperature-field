"""Select an evaluated immutable release, preserving the previous local selection."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',choices=['v1','v2','v3'],default='v3')
    args=parser.parse_args()
    base=ROOT/'knowledge/agri-temperature'
    report=json.loads((base/f'evaluations/retrieval-{args.version}.json').read_text(encoding='utf-8'))
    release_path=base/'releases'/f'{report["release_id"]}.json'
    release=json.loads(release_path.read_text(encoding='utf-8'))
    if not report['passed'] or hashlib.sha256(release_path.read_bytes()).hexdigest()!=report['release_sha256']:
        raise ValueError('Release did not pass evaluation or changed after evaluation')
    if release['review_sha256'] != hashlib.sha256((base/'review-v1.json').read_bytes()).hexdigest():
        raise ValueError('Review record changed after publication')
    if release.get('amendment_sha256') and release['amendment_sha256'] != hashlib.sha256(
            (base/'review-amendment-v3.json').read_bytes()).hexdigest():
        raise ValueError('Review amendment changed after publication')
    if release.get('supports_numeric_thresholds') is not False:
        raise ValueError('This activation path permits qualitative releases only')
    active={'TFIELD_ASSISTANT_QDRANT_URL':'http://127.0.0.1:6333',
        'TFIELD_ASSISTANT_EMBEDDING_URL':'http://127.0.0.1:8001/v1/embeddings',
        'TFIELD_ASSISTANT_QDRANT_COLLECTION':report['collection'],
        'TFIELD_ASSISTANT_KNOWLEDGE_RELEASE':str(release_path),
        'release_sha256':report['release_sha256'], 'activation_scope':'qualitative_reference_only',
        'supports_numeric_thresholds':False}
    path=ROOT/'.local/assistant/knowledge-active.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and json.loads(path.read_text(encoding='utf-8-sig'))!=active:
        (path.parent/'knowledge-active.previous.json').write_text(path.read_text(encoding='utf-8-sig'),encoding='utf-8')
    path.write_text(json.dumps(active,ensure_ascii=False,indent=2),encoding='utf-8')
    settings_path=ROOT/'.local/system.local.json'
    if settings_path.exists():
        settings=json.loads(settings_path.read_text(encoding='utf-8-sig'))
        environment=settings.setdefault('Environment',{})
        for key,value in active.items():
            if key.startswith('TFIELD_'):
                environment[key]=value
        environment['TFIELD_ASSISTANT_ACTIVE_KNOWLEDGE_FILE']=str(path)
        settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Active qualitative release:',report['release_id'])


if __name__=='__main__':
    main()
