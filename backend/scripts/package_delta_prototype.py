"""Verify a trained delta G against its holdout and package it with a frozen F.

Produces a new trusted model directory; does not change the running configuration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import sys

import numpy as np
import pandas as pd

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src')]
from tfield import config as C, prototype_runtime
from tfield.data.loader import load_dataset
from tfield.independent_training import GEOMETRY, PROTOCOL, SectionFieldModel, local_positions
from tfield.weather_chain import WeatherNodeModel
from tfield.weather_training import arrays, scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidate, reference = args.candidate.resolve(), args.reference.resolve()
    report = json.loads((candidate / 'report.json').read_text(encoding='utf-8'))
    old_report = json.loads((reference / 'report.json').read_text(encoding='utf-8'))
    manifest = json.loads((reference / 'model-manifest.json').read_text(encoding='utf-8'))
    raw = {name: (reference / name).read_bytes() for name in ('current.pkl', 'history.pkl', 'field.pkl')}
    assert manifest['protocol'] == report['spatial_protocol'] == PROTOCOL
    assert report['geometry'] == manifest['geometry'] == GEOMETRY
    assert all(hashlib.sha256(value).hexdigest() == manifest['files'][name] for name, value in raw.items())
    raw['current.pkl'] = (candidate / 'current.pkl').read_bytes()
    node, field = pickle.loads(raw['current.pkl']), pickle.loads(raw['field.pkl'])
    assert isinstance(node, WeatherNodeModel) and node.prediction_target == 'delta'
    assert node.n_nodes == 8 and not node.spec.history and node.spec.humidity
    assert isinstance(field, SectionFieldModel) and field.protocol == PROTOCOL
    assert report['prediction_target'] == report['mapping_comparison']['selected'] == 'delta'

    dataset = load_dataset(args.dataset.resolve())
    weather, labels, _ = arrays(dataset)
    inside = weather.timestamp.between(pd.Timestamp(report['dataset']['time_start']), pd.Timestamp(report['dataset']['time_end']))
    weather, labels = weather.loc[inside].reset_index(drop=True), labels[inside]
    assert len(weather) == report['dataset']['n_frames']
    split = report['split']['train_frames']
    future = weather.iloc[split:].reset_index(drop=True)
    assert future.timestamp.iloc[0].isoformat() == report['split']['validation_start']
    assert len(future) == report['split']['validation_frames']
    virtual = node.predict(future)
    reconstructed = field.predict(future, virtual, target_positions=local_positions())
    np.testing.assert_allclose(reconstructed, virtual, atol=1e-7)
    actual = np.concatenate([labels[split:, i*8:(i+1)*8] for i in range(len(C.SHED_ORDER))])
    validation = scores(actual, np.tile(reconstructed, (len(C.SHED_ORDER), 1)))
    for key in ('mae', 'rmse', 'r2', 'n'):
        assert np.isclose(validation[key], report['test'][key], rtol=1e-8, atol=1e-10), key

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name, value in raw.items():
        (output / name).write_bytes(value)
    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
    deployment = dict(created_at=datetime.now(timezone.utc).isoformat(), prediction_target='delta',
        candidate_directory=str(candidate), previous_directory=str(reference), active_stage1='current',
        history_active=False, history_note='Retained legacy artifact; prototype runtime uses current only.',
        candidate_report_sha256=hashlib.sha256((candidate / 'report.json').read_bytes()).hexdigest(),
        source_dataset_sha256=hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        frozen_field_sha256=hashes['field.pkl'], chain_node_holdout=validation)
    save('model-manifest.json', dict(protocol=PROTOCOL, geometry=GEOMETRY, files=hashes,
                                    prediction_target='delta', active_stage1='current'))
    deployed_report = dict(report)
    deployed_report['options'] = {**report['options'], 'name': '温差 G → 冻结 F'}
    deployed_report['field_validation'] = old_report['field_validation']
    deployed_report['deployment'] = deployment
    save('report.json', deployed_report)
    shutil.copy2(candidate / 'report.json', output / 'g-validation-report.json')

    os.environ['TFIELD_PROTOTYPE_MODEL_DIR'] = str(output)
    info = prototype_runtime.info()
    assert info['ready'] and info['prediction_target'] == 'delta'
    probes = []
    for outside in (-15., -5., 0., 10., 25., 35.):
        frames = [dict(timestamp='2026-11-22T02:10:00Z', bg_temp=outside, bg_rh=29., bg_light=47795.)]
        result = prototype_runtime.infer(frames, {key: GEOMETRY[key] for key in ('length_m', 'width_m', 'height_m')}, info['reference_id'])
        summary = result['summary']
        assert summary['prediction_target'] == 'delta' and summary['warnings'] == []
        assert np.isfinite(summary['mean']) and len(summary['node_temperatures']) == 8
        probes.append(dict(outside=outside, node_mean=float(np.mean(summary['node_temperatures'])),
                           field_mean=summary['mean'], vmin=summary['vmin'], vmax=summary['vmax']))
    assert probes[0]['field_mean'] < probes[-1]['field_mean'] - 20
    acceptance = dict(model_directory=str(output), reference_id=info['reference_id'],
        prediction_target='delta', holdout=validation, probes=probes,
        frozen_field_unchanged=hashes['field.pkl'] == manifest['files']['field.pkl'])
    save('acceptance.json', acceptance)
    print(json.dumps(acceptance, ensure_ascii=False))


if __name__ == '__main__':
    main()
