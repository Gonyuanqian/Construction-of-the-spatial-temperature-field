"""Bounded Chat Completions SSE assembly. No tool is executable before settlement."""
from __future__ import annotations

import json
import re


def answer_preview(text):
    """Extract only public claim text from partial JSON, never tool arguments as a whole."""
    if not text.lstrip().startswith(('{','[')):
        return text[:20000]
    parts=[]
    for match in re.finditer(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)',text):
        try:parts.append(json.loads('"'+match[1]+'"'))
        except (ValueError,UnicodeError):pass
    return '\n\n'.join(parts)[:20000]

# SSE envelopes repeat provider metadata for every token. Bound transport and
# assembled content separately; a short answer can have a much larger wire size.
MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024
MAX_MESSAGE_BYTES = 512 * 1024


class ModelProtocolError(ValueError):
    def __init__(self, code, detail, *, metrics=None):
        self.code = code
        self.metrics = metrics or {}
        super().__init__(detail)


def collect(lines, guard, progress=lambda chars, tools: None, *, retain_reasoning=False, reasoning_progress=lambda size: None, answer_progress=lambda text: None):
    content, calls, usage, finish = '', {}, {}, None
    reasoning = ''
    size, message_size, event_size, event_count, data, done = 0, 0, 0, 0, [], False
    def limit(kind):
        return ModelProtocolError('model_stream_size', '模型响应超过允许大小。', metrics={
            'limit_kind':kind,'stream_bytes':size,'message_bytes':message_size,'event_bytes':event_size,'event_count':event_count})
    for line in lines:
        guard()
        line_size=len(line.encode('utf-8'))+1
        size += line_size
        if size > MAX_STREAM_BYTES:
            raise limit('stream')
        if line.startswith(':'):
            continue
        if line.startswith('data:'):
            event_size += line_size
            if event_size > MAX_EVENT_BYTES:
                raise limit('event')
            data.append(line[5:].lstrip(' '))
            continue
        if line or not data:
            continue
        payload, data, event_size = '\n'.join(data), [], 0
        if payload == '[DONE]':
            done = True
            break
        try:
            chunk = json.loads(payload)
            event_count += 1
            if chunk.get('usage'):
                usage = chunk['usage']
            choices = chunk.get('choices', [])
            if not choices:
                continue
            if len(choices) != 1 or choices[0].get('index', 0) != 0:
                raise ValueError('choice')
            choice = choices[0]
            delta = choice.get('delta') or {}
            if finish is not None:
                raise ValueError('delta after settlement')
            for key in ('content','reasoning_content'):
                value=delta.get(key)
                if value is not None:
                    if not isinstance(value,str):raise ValueError('text type')
                    message_size += len(value.encode('utf-8'))
            if message_size > MAX_MESSAGE_BYTES:
                raise limit('message')
            content += delta.get('content') or ''
            if retain_reasoning and delta.get('reasoning_content'):
                reasoning += delta['reasoning_content']
                reasoning_progress(len(reasoning))
            for part in delta.get('tool_calls') or []:
                for value in (part.get('id'),(part.get('function') or {}).get('name'),(part.get('function') or {}).get('arguments')):
                    if value is not None:
                        if not isinstance(value,str):raise ValueError('tool text type')
                        message_size += len(value.encode('utf-8'))
                if message_size > MAX_MESSAGE_BYTES:
                    raise limit('message')
                index = part['index']
                if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < 4:
                    raise ValueError('tool index')
                call = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if part.get('type', 'function') != 'function':
                    raise ValueError('tool type')
                if part.get('id'):
                    if call['id'] and call['id'] != part['id']:
                        raise ValueError('tool identity changed')
                    call['id'] = part['id']
                function = part.get('function') or {}
                # Provider names may be fragmented just like the JSON arguments.
                call['function']['name'] += function.get('name') or ''
                call['function']['arguments'] += function.get('arguments') or ''
                if len(call['function']['arguments']) > 16384 or len(call['function']['name']) > 100:
                    raise ValueError('tool size')
            if choice.get('finish_reason') is not None:
                finish = choice['finish_reason']
            progress(len(content) + sum(len(c['function']['arguments']) for c in calls.values()), len(calls))
            preview=answer_preview(content) if content else '\n\n'.join(
                answer_preview(c['function']['arguments']) for c in calls.values() if c['function']['name']=='finish_answer')
            if preview:answer_progress(preview[:20000])
        except ModelProtocolError:
            raise
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ModelProtocolError('model_stream_protocol', '模型流格式无效，未执行本次工具请求。') from exc
    guard()
    if not done or finish is None:
        raise ModelProtocolError('model_stream_incomplete', '模型流未完整结束，未执行本次工具请求。')
    if finish not in ('stop', 'tool_calls'):
        # Truncated calls are never exposed to the dispatcher.
        calls = {}
    elif calls:
        try:
            if finish != 'tool_calls' or len({c['id'] for c in calls.values()}) != len(calls):
                raise ValueError('settlement')
            for c in calls.values():
                if not c['id'] or not c['function']['name'] or not isinstance(json.loads(c['function']['arguments']), dict):
                    raise ValueError('incomplete tool')
        except (ValueError, TypeError) as exc:
            raise ModelProtocolError('model_stream_tool', '模型工具请求不完整，未执行本次工具请求。') from exc
    elif finish == 'tool_calls':
        raise ModelProtocolError('model_stream_tool', '模型没有返回完整工具请求。')
    message = {'role': 'assistant', 'content': content or None}
    if retain_reasoning:
        message['reasoning_content'] = reasoning
    if calls:
        message['tool_calls'] = [calls[index] for index in sorted(calls)]
    return {'choices': [{'finish_reason': finish, 'message': message}], 'usage': usage,
            'stream_metrics':{'stream_bytes':size,'message_bytes':message_size,'event_count':event_count}}
