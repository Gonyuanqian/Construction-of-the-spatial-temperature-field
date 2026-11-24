"""Package saved G/F artifacts selected by the authenticated Java business layer."""
import base64
import copy
import json
import os
import threading
from uuid import uuid4

import pandas as pd
from tfield.artifact import ArtifactError, PipelineArtifact
from tfield.features import FEATURE_GROUPS, add_feature_groups
from tfield import weather_runtime as runtime
from . import weather_training as jobs
from .dataset_context import DatasetContextError

LOCK = threading.RLock()


def package(job_id, body):
    allowed = {'package_id', 'name', 'model_id', 'artifact_base64', 'artifact_sha256'}
    if set(body) != allowed:
        raise DatasetContextError(422, '组合发布参数无效。')
    try:
        identifier = runtime.identifier(body['package_id'])
        model_id, name = body['model_id'], body['name']
        if isinstance(model_id, bool) or not isinstance(model_id, int) or model_id <= 0:
            raise ValueError()
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError()
        if not isinstance(body['artifact_base64'], str) or len(body['artifact_base64']) > 44739244:
            raise ValueError()
        field = base64.b64decode(body['artifact_base64'], validate=True)
        if not field or len(field) > 32 * 1024 * 1024 or runtime.digest(field) != body['artifact_sha256']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise DatasetContextError(422, 'F 成品或发布参数校验失败。')
    with LOCK:
        with jobs.LOCK:
            jobs.get(job_id)
            state = copy.deepcopy(jobs.STATES[job_id])
        if state['state'] != 'done' or not state.get('artifacts'):
            raise DatasetContextError(409, '只能发布训练完成且成品完整的 G 模型。')
        if state.get('result', {}).get('spatial_protocol') == 'independent_house_section_v2':
            raise DatasetContextError(409, '该成品是单棚 8 点横截面协议，不能与旧版 24 点三棚构场协议组合发布。请使用对应的单棚运行链路。')
        identity = dict(g_training_job_id=job_id, publication_name=name.strip(),
                        model_id=model_id, external_schema=state['options']['external_schema'],
                        g_dataset_id=state['dataset_id'], g_dataset_sha256=state['dataset_sha256'],
                        g_artifacts=state['artifacts'])
        root = runtime.model_root().resolve()
        destination = root / identifier
        if destination.is_symlink() or destination.resolve().parent != root:
            raise DatasetContextError(409, '模型部署目录无效。')
        if destination.exists():
            try:
                existing = runtime.inspect_package(identifier)
                if any(existing.get(k) != v for k, v in identity.items()) or existing['files']['field.bin'] != runtime.digest(field):
                    raise DatasetContextError(409, '同一操作编号不能发布不同的 G/F 组合或名称。')
                return existing
            except (ValueError, KeyError, OSError):
                raise DatasetContextError(409, '已存在的模型包校验失败，请使用新的发布操作。')
        contents = {'field.bin': field}
        for key in ('current', 'history'):
            source = jobs.folder(job_id) / f'{key}.pkl'
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 32 * 1024 * 1024:
                raise DatasetContextError(409, 'G 成品文件缺失或大小无效，请重新训练。')
            raw = source.read_bytes()
            if runtime.digest(raw) != state['artifacts'].get(key):
                raise DatasetContextError(409, 'G 成品与训练记录摘要不一致，不能发布。')
            contents[f'{key}.pkl'] = raw
        try:
            artifact = PipelineArtifact.from_bytes(field)
            columns = pd.DataFrame({k: [0.] for k in ('x', 'y', 'z', 'bg_temp', 'bg_rh', 'bg_light', 'hour', 'frac_day')})
            if (not artifact.feature_groups or not set(artifact.feature_groups) <= set(FEATURE_GROUPS)
                    or tuple(add_feature_groups(columns, artifact.feature_groups).columns) != artifact.feature_names):
                raise ValueError('F 特征与当前构场协议不兼容。')
        except (ArtifactError, ValueError, TypeError, AttributeError) as exc:
            raise DatasetContextError(409, 'F 成品不能用于当前气象构场协议，请重新训练并保存 F。') from exc
        manifest = dict(version=1, package_id=identifier, geometry_key='ginseng_arch_v1',
                        timezone='Asia/Shanghai', history_frames=13, bounds=copy.deepcopy(state.get('result', {}).get('bounds', {})), **identity,
                        g_name=state['name'], g_filename=state['filename'],
                        files={name: runtime.digest(raw) for name, raw in contents.items()})
        raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')
        # Stage an entire package before making its immutable UUID visible.
        staging_base = root / '.staging'
        if staging_base.is_symlink() or staging_base.resolve().parent != root:
            raise DatasetContextError(409, '模型临时目录无效。')
        stage_root = staging_base / str(uuid4())
        stage = stage_root / identifier
        stage.mkdir(parents=True, exist_ok=False)
        try:
            for name, content in contents.items():
                (stage / name).write_bytes(content)
            (stage / 'manifest.json').write_bytes(raw)
            try:
                runtime._load.__wrapped__(str(stage_root), identifier, runtime.digest(raw))
            except Exception as exc:
                raise DatasetContextError(409, 'G/F 成品不能组成有效气象模型包，请检查训练成品。') from exc
            if not stage.resolve().is_relative_to(root) or destination.resolve().parent != root:
                raise DatasetContextError(409, '模型包目标目录无效。')
            os.replace(stage, destination)
        finally:
            # Only remove the exact, newly allocated staging files.
            if stage.exists():
                for name in (*runtime.FILES, 'manifest.json'):
                    (stage / name).unlink(missing_ok=True)
                stage.rmdir()
            stage_root.rmdir()
        return {**manifest, 'package_sha256': runtime.digest(raw)}
