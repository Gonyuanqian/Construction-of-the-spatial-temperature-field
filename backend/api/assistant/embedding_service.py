"""Local, offline, CPU embedding endpoint; no model-code execution or silent truncation."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .. import paths

os.environ.setdefault('USE_TF', '0')
os.environ.setdefault('USE_FLAX', '0')
_state = {}
_lock = Lock()


@asynccontextmanager
async def lifespan(app):
    import torch
    from transformers import AutoModel, AutoTokenizer
    manifest_path = Path(os.environ.get('TFIELD_ASSISTANT_INSTALLATION_FILE',
        str(paths.PROJECT / '.local/assistant/services/installation.json')))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(manifest['model_path'], local_files_only=True,
                                              trust_remote_code=False)
    model = AutoModel.from_pretrained(manifest['model_path'], local_files_only=True,
                                     trust_remote_code=False, use_safetensors=True).to('cpu').eval()
    _state.update(tokenizer=tokenizer, model=model, torch=torch, model_id=manifest['model_id'],
                  revision=manifest['revision'], dimension=model.config.hidden_size,
                  max_tokens=min(tokenizer.model_max_length, model.config.max_position_embeddings))
    yield
    _state.clear()


app = FastAPI(title='Local agricultural assistant embeddings', lifespan=lifespan)


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str = Field(max_length=120)
    input: str | list[str]


@app.get('/health')
def health():
    return {k: _state[k] for k in ('model_id', 'revision', 'dimension', 'max_tokens')} | {'status': 'ready', 'device': 'cpu'}


@app.post('/v1/embeddings')
def embeddings(body: EmbeddingRequest):
    if body.model != _state['model_id']:
        raise HTTPException(422, '模型名称不匹配；不能在同一向量空间内混用模型。')
    texts = [body.input] if isinstance(body.input, str) else body.input
    if not 1 <= len(texts) <= 8 or any(not t.strip() or len(t) > 6000 for t in texts):
        raise HTTPException(422, '单批需包含 1–8 条非空文本，每条最多 6000 字符。')
    with _lock:
        encoded = _state['tokenizer'](texts, padding=True, truncation=False, return_tensors='pt')
        if encoded['input_ids'].shape[1] > _state['max_tokens']:
            raise HTTPException(422, '证据超过模型长度限制；请先按完整知识单元切分，服务不会截断适用条件。')
        torch = _state['torch']
        with torch.inference_mode():
            output = _state['model'](**encoded).last_hidden_state[:, 0]
            vectors = torch.nn.functional.normalize(output, p=2, dim=1).tolist()
    count = int(encoded['attention_mask'].sum())
    return {'object': 'list', 'model': _state['model_id'], 'revision': _state['revision'],
            'data': [{'object': 'embedding', 'index': i, 'embedding': vector} for i, vector in enumerate(vectors)],
            'usage': {'prompt_tokens': count, 'total_tokens': count}}
