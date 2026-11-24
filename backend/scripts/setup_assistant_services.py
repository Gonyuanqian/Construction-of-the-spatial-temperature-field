"""Download pinned official Windows Qdrant and a small Chinese embedding model into this workspace."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[2]
QDRANT_VERSION = '1.20.0'
QDRANT_SHA256 = '6d13553584fd0411f00637519e293331ff0aa1fb79bd9e30db45839bb75de2be'
MODEL_ID = 'BAAI/bge-small-zh-v1.5'
REVISION = '7999e1d3359715c523056ef9478215996d62a620'


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and (not expected or hashlib.sha256(target.read_bytes()).hexdigest() == expected):
        return
    temporary = target.with_suffix(target.suffix + '.part')
    with httpx.Client(timeout=httpx.Timeout(60, connect=30), follow_redirects=True) as client:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            digest = hashlib.sha256()
            with temporary.open('wb') as out:
                for block in response.iter_bytes(1024 * 1024):
                    digest.update(block)
                    out.write(block)
    if expected and digest.hexdigest() != expected:
        raise ValueError('Downloaded file checksum mismatch: ' + target.name)
    temporary.replace(target)
    print('Downloaded', target.name, target.stat().st_size, flush=True)


def main():
    binary = ROOT / '.tools/assistant/qdrant' / QDRANT_VERSION
    archive = binary / 'qdrant.zip'
    download(f'https://github.com/qdrant/qdrant/releases/download/v{QDRANT_VERSION}/qdrant-x86_64-pc-windows-msvc.zip',
             archive, QDRANT_SHA256)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if not (binary / member.filename).resolve().is_relative_to(binary.resolve()):
                raise ValueError('Archive entry escapes installation directory')
        package.extractall(binary)
    model = ROOT / '.tools/assistant/models/bge-small-zh-v1.5' / REVISION
    for name in ('config.json', 'model.safetensors', 'special_tokens_map.json', 'tokenizer.json',
                 'tokenizer_config.json', 'vocab.txt'):
        download(f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}?download=true', model / name)
    state = ROOT / '.local/assistant/services'
    state.mkdir(parents=True, exist_ok=True)
    manifest = {'qdrant_version': QDRANT_VERSION, 'qdrant_zip_sha256': QDRANT_SHA256,
                'qdrant_exe': str(binary / 'qdrant.exe'), 'model_id': MODEL_ID, 'revision': REVISION,
                'model_path': str(model), 'model_files_sha256': {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model.iterdir() if p.is_file()}}
    (state / 'installation.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Pinned installation ready', flush=True)


if __name__ == '__main__':
    main()
