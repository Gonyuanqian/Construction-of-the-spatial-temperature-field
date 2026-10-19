"""打包本机部署版本，不包含数据、模型、凭据和测试目录。"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    target = args.destination.resolve()
    target.mkdir(parents=True, exist_ok=False)
    jars = [p for p in (project/'backend-java/target').glob('tfield-business-*.jar') if not p.name.endswith('.original')]
    # 读取 pom 的版本，避免拿到以前构建遗留的 jar。
    import xml.etree.ElementTree as ET
    version = ET.parse(project/'backend-java/pom.xml').getroot().find('{*}version').text
    jar = project/f'backend-java/target/tfield-business-{version}.jar'
    if jar not in jars:
        raise FileNotFoundError('请先构建 Java 服务。')
    shutil.copy2(jar, target/'business.jar')
    shutil.copytree(project/'frontend/dist', target/'frontend')
    for folder in ('api', 'src'):
        shutil.copytree(project/'backend'/folder, target/'backend'/folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
    for name in ('requirements.txt', 'requirements-api.txt', 'pyproject.toml'):
        shutil.copy2(project/'backend'/name, target/'backend'/name)
    packages = sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions() if d.metadata.get('Name'))
    (target/'python-environment.txt').write_text('\n'.join(packages)+'\n', encoding='utf-8')
    files = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(target.rglob('*')) if p.is_file()}
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=project, text=True).strip()
    manifest = {'version': version, 'built_at': datetime.now(timezone.utc).isoformat(),
                'source_commit': commit, 'worktree_dirty': bool(subprocess.check_output(
                    ['git', 'status', '--porcelain'], cwd=project, text=True).strip()), 'sha256': files}
    (target/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'部署包：{target}；版本 {version}；{len(files)} 个文件。')


if __name__ == '__main__':
    main()
