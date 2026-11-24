"""Offline acceptance bridge: evaluate an already-published package without MySQL writes.

Input is the exact internal /weather/infer request produced by Java. No weather is
invented, no models are trained, and result files stay under the requested output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from tfield import weather_runtime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ['TFIELD_WEATHER_RESULT_ROOT'] = str(folder / 'results')
    request = json.loads(args.request.read_text(encoding='utf-8'))
    result = weather_runtime.infer(request['package_id'], request['package_sha256'], request['frames'])
    nodes = result['summary']['node_temperatures']
    assert len(nodes) == 24 and np.isfinite(nodes).all()
    assert result['summary']['stage1_mode'] == 'current_only'
    assert result['field']['planes'] and all(not p['measured'] for p in result['field']['planes'])
    assert result['summary']['mean'] is not None and np.isfinite(result['summary']['mean'])
    weather_runtime.save_result(request['frame_id'], result)
    assert weather_runtime.read_result(request['frame_id'])['summary'] == result['summary']
    for name, value in [('computed', result), ('summary', result['summary'])]:
        (folder / f'{name}.json').write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    from api import weather_views
    for name, payload in [('sections', weather_views.sections(request['frame_id'])),
                          ('volume', weather_views.saved_volume(request['frame_id'])[1]),
                          ('volume-summary', weather_views.saved_volume(request['frame_id'], y_step=3.)[1])]:
        (folder / f'{name}.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    report = {'passed': True, 'node_count': len(nodes), 'plane_count': len(result['field']['planes']),
              'stage1_mode': result['summary']['stage1_mode'], 'model_id': result['summary']['model_id'],
              'mean': result['summary']['mean'], 'vmin': result['summary']['vmin'], 'vmax': result['summary']['vmax'],
              'warnings': result['summary']['warnings'], 'training_bounds': result['summary']['training_bounds'],
              'input_time': request['frames'][-1]['timestamp'], 'offline_replay': True,
              'database_writes': 0, 'extra_paid_weather_requests': 0,
              'note': '历史真实气象响应回放的链路验收，不是准确率评估或实时传感器实测。'}
    (folder / 'compute-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
