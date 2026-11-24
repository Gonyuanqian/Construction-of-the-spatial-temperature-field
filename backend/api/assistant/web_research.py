"""Per-run public web research through DeepSeek Search/Fetch; never write into Qdrant."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from . import config

API = 'https://api.deepseek.com/v1/tools/'
# Discovery of a domain does not certify a claim. Read its original text, then review applicability.
INSTITUTIONS = ('fao.org', 'wmo.int', 'cgiar.org', 'irri.org', 'icrisat.org', 'worldveg.org',
                'caas.cn', 'caas.net.cn', 'agri.cn', 'usda.gov', 'wur.nl', 'wurnet.nl',
                'inrae.fr', 'csiro.au', 'ipcc.ch')
PUBLISHERS = ('sciencedirect.com', 'link.springer.com', 'nature.com', 'science.org',
              'onlinelibrary.wiley.com', 'mdpi.com', 'frontiersin.org', 'journals.plos.org',
              'academic.oup.com', 'tandfonline.com', 'cambridge.org', 'ishs.org')
ACADEMIC_SUFFIXES = ('.edu', '.edu.cn', '.ac.cn', '.ac.uk', '.ac.jp', '.ac.nz', '.gov',
                     '.gov.cn', '.gov.uk', '.gov.au', '.gov.nz', '.gc.ca')


def configured():
    return bool(config.api_key()) and os.getenv('TFIELD_ASSISTANT_WEB_SEARCH', 'true').lower() != 'false'


def retrieval_opt_out(question):
    return bool(re.search(r'(?:不必|不需要|无需|不用|不要|禁止|别)(?:再|进行|额外|任何|使用)?'
                          r'(?:联网|搜索|检索|查资料|查文献)', re.sub(r'\s+', '', question)))


def required(question):
    return not retrieval_opt_out(question) and bool(re.search(r'联网|网搜|网上|搜索|检索|最新|近期|研究进展|近年|20[2-9]\d年.*(?:论文|文献|研究)', question))


def public_url(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower().rstrip('.')
        if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443):
            return None
        if not host or len(value) > 2000 or any(c in value for c in ('\\', '\r', '\n', '\t')):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        approved = any(host == d or host.endswith('.' + d) for d in INSTITUTIONS + PUBLISHERS)
        approved = approved or host.endswith(ACADEMIC_SUFFIXES)
        if not approved:
            return None
        query = urlencode([(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                           if not k.lower().startswith('utm_')])
        return urlunsplit(('https', host, url.path or '/', query, ''))
    except (ValueError, TypeError, AttributeError):
        return None


def public_query(value):
    if not isinstance(value, str):
        raise ValueError('联网查询需要公开农业关键词。')
    value = re.sub(r'[xyz]\s*[=：:为]\s*[-+\d.eE]+', '', value, flags=re.I)
    value = re.sub(r'[-+]?\d+(?:\.\d+)?\s*(?:°\s*C|℃|摄氏度)', '', value, flags=re.I).strip()
    if not value or len(value) > 128 or re.search(
            r'sk-[\w-]{8,}|[\w.+-]+@[\w.-]+|https?://|[a-f\d]{8}-[a-f\d-]{27,}|(?:密钥|密码|token)\s*[:：=]', value, re.I):
        raise ValueError('请仅使用不含凭据、链接、个人信息或会话编号的公开农业检索词（最多128字）。')
    return value


def _post(operation, body, timeout, guard):
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=timeout, follow_redirects=False,
            trust_env=os.getenv('TFIELD_ASSISTANT_MODEL_TRUST_ENV', 'true').lower() != 'false') as client:
        with client.stream('POST', API + operation, json=body,
                           headers={'Authorization': 'Bearer ' + config.api_key()}) as response:
            response.raise_for_status()
            parts, size = [], 0
            for chunk in response.iter_bytes():
                guard()
                if time.monotonic() > deadline:
                    raise httpx.ReadTimeout('web deadline')
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError('联网响应过大。')
                parts.append(chunk)
            return json.loads(b''.join(parts))


def excerpt(content, focus, limit=2200):
    """Select bounded original paragraphs, in original order; never use search summaries as evidence."""
    content = re.sub(r'<script\b[^>]*>.*?</script>', '', content, flags=re.S | re.I)
    content = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', content)
    content = re.sub(r'https?://\S+', '', content)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content[:150000]) if p.strip()]
    terms = set(re.findall(r'[a-z]{3,}', focus.lower()))
    for segment in re.findall(r'[\u4e00-\u9fff]+', focus):
        terms.update(segment[i:i+2] for i in range(len(segment)-1))
    ranked = sorted(range(len(paragraphs)), key=lambda i: (
        sum(1 for term in terms if term in paragraphs[i].lower()),
        bool(re.search(r'temperatur|温度|root|根区|DIF|thermoperiod', paragraphs[i], re.I)), -i), reverse=True)
    chosen, remaining = {}, limit
    for i in ranked:
        if remaining < 150 or len(chosen) >= 3:
            break
        # Truncation remains an original prefix, with an explicit display marker.
        raw = paragraphs[i].encode('utf-8')
        text = raw[:remaining-8].decode('utf-8', errors='ignore')
        if len(text.strip()) < 40:
            continue
        chosen[i] = text + (' […]' if len(raw) > remaining-8 else '')
        remaining -= len(chosen[i].encode('utf-8')) + 2
    return '\n\n'.join(chosen[i] for i in sorted(chosen)), [i+1 for i in sorted(chosen)]


class WebResearch:
    def __init__(self, guard=lambda: None):
        self.guard = guard
        self.sources, self.search_cache, self.read_cache = {}, {}, {}
        self.originals = {}
        self.search_calls = 0
        self.read_calls = 0

    def search(self, query, timeout=8):
        query = public_query(query)
        if query in self.search_cache:
            return dict(self.search_cache[query], cached=True)
        if not configured():
            return {'status': 'not_configured', 'sources': [], 'detail': '联网搜索未启用或未配置。'}
        if self.search_calls >= 2:
            return {'status': 'budget_exhausted', 'sources': [], 'detail': '本轮联网搜索次数已达到上限。'}
        self.guard()
        self.search_calls += 1
        try:
            result = _post('search', {'query': query, 'count': 8, 'need_content': True}, timeout, self.guard)
            sources, seen = [], set()
            for item in result.get('results', []):
                url = public_url(item.get('url'))
                if not url or url in seen or not isinstance(item.get('title'), str):
                    continue
                seen.add(url)
                identifier = 'S:' + hashlib.sha256(url.encode()).hexdigest()[:16]
                lead = {'source_id': identifier, 'title': item['title'][:160], 'url': url,
                        'published_at': str(item.get('date') or '')[:40], 'query': query}
                self.sources[identifier] = lead
                if isinstance(item.get('content'), str) and len(item['content'].strip()) >= 80:
                    self.originals[identifier] = item['content'][:150000]
                sources.append({k: v for k, v in lead.items() if k != 'query'})
                if len(sources) == 4:
                    break
            out = {'status': 'ok' if sources else 'no_sources', 'sources': sources,
                   'detail': '搜索结果只是线索，必须调用 read_web_source 读取原文后引用 W: 证据；排名不表示结论正确。'}
            self.search_cache[query] = out
            return out
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return {'status': 'unavailable', 'sources': [], 'detail': '联网搜索暂时不可用，未取得可核验的原文。'}

    def read(self, source_id, timeout=8):
        if not isinstance(source_id, str):
            raise ValueError('来源编号需要是本轮返回的字符串。')
        if source_id in self.read_cache:
            return dict(self.read_cache[source_id], cached=True)
        source = self.sources.get(source_id)
        if not source:
            raise ValueError('只能读取本轮搜索返回的来源编号，不能提供任意网址。')
        if not configured():
            return {'status': 'not_configured', 'evidence': [], 'detail': '联网搜索未启用或未配置。'}
        if self.read_calls >= 3:
            return {'status': 'budget_exhausted', 'evidence': [], 'detail': '本轮原文读取次数已达到上限。'}
        self.guard()
        self.read_calls += 1
        try:
            cached_original = self.originals.get(source_id)
            page = {'content': cached_original} if cached_original else _post('fetch', {'url': source['url']}, timeout, self.guard)
            content = page.get('content')
            if not isinstance(content, str) or len(content.strip()) < 80:
                raise ValueError('no readable content')
            text, paragraphs = excerpt(content, source['query'])
            if len(text) < 80:
                raise ValueError('no excerpt')
            digest = hashlib.sha256(content.encode()).hexdigest()
            identifier = 'W:' + hashlib.sha256((source['url'] + digest).encode()).hexdigest()[:20]
            evidence = {'id': identifier, 'text': text, 'title': source['title'], 'source_title': source['title'],
                        'source_url': source['url'], 'source_access': 'live_original_excerpt',
                        'retrieval_channel': 'search_original_content' if cached_original else 'fetch_original_content',
                        'published_at': source['published_at'] or None,
                        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'content_sha256': digest,
                        'locator': '联网读取原文；段落 ' + ', '.join(map(str, paragraphs)),
                        'origin': 'web_original', 'evidence_kind': 'external_original',
                        'original_verified': True, 'review_status': 'requires_claim_review',
                        'usage_limitations': ['未入本地已审校知识库；仅用于本轮带出处的说明。',
                            '保留研究对象、作物、设施与实验条件；不能直接作为本棚温度处方或现场读数。']}
            out = {'status': 'ok', 'evidence': [evidence]}
            self.read_cache[source_id] = out
            return out
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return {'status': 'unavailable', 'evidence': [], 'detail': '该来源原文未能完整读取，不能仅凭搜索摘要作结论。'}
