"""Use development labels only to set the lowest cutoff rejecting all development negatives."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'knowledge/agri-temperature'


def main():
    report_path = BASE/'evaluations/retrieval-v1.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    dev = [r for r in report['rows'] if r['split']=='development']
    negative_max = max(r['scores'][0] for r in dev if not r['gold_ids'] and r['scores'])
    threshold = round(negative_max+1e-6,8)
    if any(r['scores'][0] < threshold for r in dev if r['gold_ids']):
        raise ValueError('No development cutoff preserves positive recall while rejecting negatives')
    release = json.loads((BASE/'releases/agri-temperature-qualitative-20261030-v1.json').read_text(encoding='utf-8'))
    release.update(release_id='agri-temperature-qualitative-20261030-v2',
                   query_score_threshold=threshold, context_limit=3,
                   calibration={'policy':'lowest_threshold_above_max_development_negative',
                       'case_ids':[r['id'] for r in dev],
                       'baseline_report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
                       'note':'首轮留出结果已查看；本次对比复测不是新的盲测，未用留出标签选择阈值。'})
    content = json.dumps(release,ensure_ascii=False,indent=2)+'\n'
    output = BASE/'releases'/f'{release["release_id"]}.json'
    if output.exists() and output.read_text(encoding='utf-8') != content:
        raise ValueError('Use a new release version instead of overwriting existing content')
    output.write_text(content,encoding='utf-8')
    print('Development-only cutoff:',threshold,'context limit:',3)


if __name__=='__main__':
    main()
