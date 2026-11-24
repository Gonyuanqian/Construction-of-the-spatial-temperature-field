"""Private local configuration, never copied into API responses or deployment artifacts."""
import json
import os
from pathlib import Path

from .. import paths


def knowledge_settings():
    configured = os.getenv('TFIELD_ASSISTANT_ACTIVE_KNOWLEDGE_FILE')
    path = Path(configured) if configured else paths.PROJECT / '.local/assistant/knowledge-active.json'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        allowed = ('TFIELD_ASSISTANT_QDRANT_URL', 'TFIELD_ASSISTANT_EMBEDDING_URL',
                   'TFIELD_ASSISTANT_QDRANT_COLLECTION', 'TFIELD_ASSISTANT_KNOWLEDGE_RELEASE')
        return {key: data[key] for key in allowed if isinstance(data.get(key), str)}
    except (ValueError, OSError):
        return {}


def api_key():
    explicit = os.getenv('DEEPSEEK_API_KEY', '').strip()
    if explicit:
        return explicit
    configured = os.getenv('TFIELD_ASSISTANT_CREDENTIALS_FILE')
    path = Path(configured) if configured else paths.PROJECT / '.local/assistant/credentials.json'
    if not path.is_file():
        return ''
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        value = data.get('deepseek_api_key', '')
        return value.strip() if isinstance(value, str) else ''
    except (ValueError, OSError):
        return ''
