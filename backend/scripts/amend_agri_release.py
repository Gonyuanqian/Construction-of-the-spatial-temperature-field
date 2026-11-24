"""Create an immutable amended release; leave published predecessors untouched."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parents[2]/'knowledge/agri-temperature'


def main():
    amendment_path=BASE/'review-amendment-v3.json'
    amendment=json.loads(amendment_path.read_text(encoding='utf-8'))
    base_path=BASE/'releases'/f'{amendment["base_release"]}.json'
    release=json.loads(base_path.read_text(encoding='utf-8'))
    for change in amendment['amendments']:
        chunk=next(c for c in release['chunks'] if c['id']==change['id'])
        chunk['text']=change['text']
        chunk['review_basis']+='；'+change['reason']
    release.update(release_id='agri-temperature-qualitative-20261030-v3',
                   amendment_sha256=hashlib.sha256(amendment_path.read_bytes()).hexdigest(),
                   parent_release_sha256=hashlib.sha256(base_path.read_bytes()).hexdigest())
    content=json.dumps(release,ensure_ascii=False,indent=2)+'\n'
    output=BASE/'releases'/f'{release["release_id"]}.json'
    if output.exists() and output.read_text(encoding='utf-8')!=content:
        raise ValueError('Existing amended release must not be overwritten')
    output.write_text(content,encoding='utf-8')
    print('Created amended qualitative release v3')


if __name__=='__main__':
    main()
