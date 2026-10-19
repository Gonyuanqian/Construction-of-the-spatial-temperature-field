"""独立环境的 HTTP 全流程联调。只有 acceptance_mode 服务接受写入检查。"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4


def normalized(value):
    if isinstance(value, dict): return {k: normalized(v) for k, v in value.items() if k != 'elapsed_ms'}
    if isinstance(value, list): return [normalized(v) for v in value]
    return value


class Flow:
    def __init__(self, args):
        self.args = args
        self.path = args.report.resolve()
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {
            'run_id': str(uuid4()), 'deployment_id': args.deployment_id, 'checks': [], 'context': {}}
        if self.state['deployment_id'] != args.deployment_id: raise ValueError('报告与部署编号不匹配。')
        info = self.call('GET', '/ops/info')
        if not info.get('acceptance_mode') or info.get('deployment_id') != args.deployment_id:
            raise ValueError('拒绝写入：目标服务未开启独立联调模式，或部署编号不匹配。')
        self.context = self.state['context']

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    def check(self, name, condition, detail=None):
        self.state['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        self.save()
        print(('PASS ' if condition else 'FAIL ')+name, flush=True)
        if not condition: raise AssertionError(name)

    def call(self, method, path, body=None, *, expected=(200,), key=None):
        headers = {'X-Request-ID': str(uuid4())}
        if body is not None:
            if not isinstance(body, bytes): body = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
            else: headers['Content-Type'] = 'application/octet-stream'
        if key: headers['Idempotency-Key'] = self.state['run_id']+':'+key
        try:
            response = urlopen(Request(self.args.base_url.rstrip('/')+path, data=body, headers=headers, method=method), timeout=600)
        except HTTPError as exc: response = exc
        with response:
            raw = response.read()
            try: value = json.loads(raw)
            except (ValueError, UnicodeDecodeError): value = raw
            if response.status not in expected:
                raise AssertionError(f'{method} {path}: HTTP {response.status}: {str(value)[:600]}')
            return value

    def wait(self, job_id, terminal, timeout=900):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            job = self.call('GET', '/api/calibration/jobs/'+job_id)
            if job['state'] != 'running':
                self.check('训练终态 '+terminal, job['state'] == terminal, job)
                return job
            time.sleep(1)
        raise TimeoutError('任务未在等待时间内确认终态。')

    def model(self):
        if not self.args.job: raise ValueError('model 阶段需要 --job，或先执行 train 阶段。')
        job = self.wait(self.args.job, 'done')
        before = self.call('GET', '/api/models')
        self.context.setdefault('original_model', before['current_id'])
        self.context.setdefault('original_model_count', len(before['rows']))
        self.check('完成结果可查询', self.call('GET', '/api/calibration')['present'])
        name='联调模型 '+self.state['run_id'][:8]
        saved = self.call('POST', '/api/models', {'name': name}, expected=(201,))
        again = self.call('POST', '/api/models', {'name': name}, expected=(201,))
        self.context['saved_model'] = saved['id']; self.context['training_job'] = job['id']; self.save()
        self.check('重复保存不新增模型', saved['id'] == again['id'] and len(self.call('GET', '/api/models')['rows']) == self.context['original_model_count']+1)
        self.call('POST', '/api/models', {'name': name+'不同'}, expected=(409,))
        detail = self.call('GET', '/api/models/'+str(saved['id']))
        self.check('完整 40 次真实参数搜索已保存成品', detail['n_trials'] == 40 and detail['has_artifact'], {'model_id': saved['id'], 'n_trials': detail['n_trials']})
        volume = self.call('GET', '/api/field/volume?t_index=0&y_step=3&preset=interactive&monotonic=true')
        self.context['model_volume_sha256'] = hashlib.sha256(json.dumps(normalized(volume),sort_keys=True).encode()).hexdigest(); self.save()
        self.check('新模型可构建三维温度场', bool(volume.get('planes')))
        sections = self.call('GET', '/api/field/sections?t_index=0')
        self.check('新模型可构建断面', bool(sections.get('sheds')) or bool(sections.get('sections')))
        self.call('POST', '/api/models/'+str(self.context['original_model'])+'/current')
        self.call('POST', '/api/models/'+str(saved['id'])+'/current')
        self.check('模型切换可恢复当前项', self.call('GET', '/api/models')['current_id'] == saved['id'])

    def data(self):
        if not self.args.source: raise ValueError('data 阶段需要 --source。')
        workspace = self.call('GET', '/api/workspaces/default')
        self.context['dataset_id'] = workspace['dataset_id']; self.save()
        uploaded = self.call('POST', '/api/dataset/upload?name='+quote('联调_中文文件.xlsx'), self.args.source.read_bytes())
        current = self.call('GET', '/api/workspaces/default')
        self.check('真实 XLSX 和中文文件名上传', uploaded['file'] == '联调_中文文件.xlsx' and current['dataset_id'] != workspace['dataset_id'])
        self.call('POST', '/api/dataset/upload?name=invalid.xlsx', b'invalid-xlsx', expected=(400,))
        self.check('无效上传保持当前数据选择', self.call('GET', '/api/workspaces/default')['dataset_id'] == current['dataset_id'])
        self.call('POST', '/api/workspaces/default/dataset', {'dataset_id': workspace['dataset_id']})
        self.check('旧数据版本可切回', self.call('GET', '/api/workspaces/default')['dataset_id'] == workspace['dataset_id'])

    def live(self):
        self.call('POST', '/api/live/prepare', key='restore-original-live')
        first = self.call('GET', '/api/live/status')
        if first['running']: self.call('POST', '/api/live/pause', key='pause-original-live')
        self.call('POST', '/api/live/start?from_n=2', key='start-at-2')
        self.call('POST', '/api/live/pause', key='pause-at-2')
        once = self.call('POST', '/api/live/next', key='step-once')
        twice = self.call('POST', '/api/live/next', key='step-once')
        self.check('同编号步进只执行一次', once['cursor'] == 3 and twice['cursor'] == 3 and not twice['running'])
        self.call('POST', '/api/live/start', key='step-once', expected=(409,))
        self.call('GET', '/api/live/volume/4', expected=(409,400))
        sid = twice['session_id']; self.context['live_session'] = sid; self.context['live_cursor'] = 3
        self.context['live_volume'] = self.call('GET', '/api/live/volume/3?y_step=3&session_id='+sid)
        frame = self.call('GET', '/api/live/frame/3?session_id='+sid)
        self.check('实时断面与三维来自同一帧', frame['frame']['time'] == self.context['live_volume']['frame']['time'])
        self.save()

    def recover(self):
        before = self.call('GET', '/api/live/status')
        self.check('重启后原会话明确需要恢复', before['session_id'] == self.context['live_session'] and before['recovery_required'] and before['cursor'] == 3)
        self.call('POST', '/api/live/prepare', key='recover-after-restart')
        after = self.call('GET', '/api/live/status')
        self.check('恢复到非零确认帧并保持暂停', after['state'] == 'ready' and after['cursor'] == 3 and not after['running'])
        volume = self.call('GET', '/api/live/volume/3?y_step=3&session_id='+after['session_id'])
        self.check('恢复前后三维结果一致', normalized(volume) == normalized(self.context['live_volume']))
        self.call('POST', '/api/live/sessions', key='fresh-session')
        fresh = self.call('GET', '/api/live/status')
        self.check('重新准备创建新会话且首帧暂停', fresh['session_id'] != after['session_id'] and fresh['cursor'] == 0 and not fresh['running'])
        self.call('GET', '/api/live/volume/0?session_id='+after['session_id'], expected=(409,))
        self.check('旧会话查询被拒绝', True)

    def cancel(self):
        job = self.call('POST', '/api/calibration/jobs', expected=(202,), key='cancel-job')
        same = self.call('POST', '/api/calibration/jobs', expected=(202,), key='cancel-job')
        self.check('相同训练键返回同一任务', job['id'] == same['id'])
        self.call('POST', '/api/calibration/jobs', expected=(409,), key='conflicting-job')
        self.call('DELETE', '/api/calibration/jobs/'+job['id'])
        self.wait(job['id'], 'cancelled', timeout=120)
        self.check('取消不新增模型', len(self.call('GET', '/api/models')['rows']) == self.context['original_model_count']+1)

    def interrupt_start(self):
        job = self.call('POST', '/api/calibration/jobs', expected=(202,), key='interrupted-job')
        self.context['interrupted_job'] = job['id']; self.save()
        self.check('已登记待中断训练', job['state'] == 'running')

    def interrupt_check(self):
        self.wait(self.context['interrupted_job'], 'failed', timeout=30)
        self.check('重启未重复入库', len(self.call('GET', '/api/models')['rows']) == self.context['original_model_count']+1)
        volume = self.call('GET', '/api/field/volume?t_index=0&y_step=3&preset=interactive&monotonic=true')
        digest = hashlib.sha256(json.dumps(normalized(volume),sort_keys=True).encode()).hexdigest()
        self.check('新模型跨重启构场数值一致', digest == self.context['model_volume_sha256'])

    def outage(self):
        status = self.call('GET', '/api/live/status')
        self.check('计算失联时保留会话并停止就绪展示', status['state'] == 'idle' and status['cursor'] == 3
                   and status['recovery_required'] and status['available'] is False)
        job = self.call('GET', '/api/calibration/jobs/'+self.context['interrupted_job'])
        self.check('未确认重启前任务等待核对', job['state'] == 'running')

    def auto_start(self):
        self.call('POST', '/api/live/start?from_n=0', key='auto-start')
        self.context['auto_started'] = time.time(); self.save()
        self.check('开始按真实间隔自动播放', self.call('GET','/api/live/status')['running'])

    def auto_check(self):
        elapsed = time.time()-self.context['auto_started']
        if elapsed < 301: raise ValueError('请至少等待 301 秒后核对真实自动播放，不加速时钟。')
        status = self.call('GET','/api/live/status')
        self.check('按 300 秒间隔自动推进', status['running'] and status['cursor'] >= 1, {'elapsed_s':round(elapsed,1),'cursor':status['cursor']})
        self.call('POST','/api/live/pause',key='auto-pause')
        n=status['cursor']
        frame=self.call('GET','/api/live/frame/'+str(n))
        volume=self.call('GET','/api/live/volume/'+str(n)+'?y_step=3')
        self.check('自动播放后图形时间一致',frame['frame']['time']==volume['frame']['time'])

    def web(self):
        index = self.call('GET', '/')
        self.check('同源首页是 HTML', isinstance(index,bytes) and b'<div id="app">' in index)
        for route in ('/data','/train','/field','/live','/models','/models/1'):
            self.check('刷新前端路径 '+route, self.call('GET',route) == index)
        asset = re.search(rb'(?:src|href)="(/assets/[^\"]+)"', index).group(1).decode()
        self.check('部署静态资源可访问', bool(self.call('GET',asset)))
        for route in ('/api','/api/not-found','/ops/not-found','/internal/not-found','/assets/not-found.js','/assets/no-extension','/not-found.js'):
            error = self.call('GET',route,expected=(404,))
            self.check('错误地址不回退 HTML '+route, isinstance(error,dict))
        self.call('POST','/api/live/status',expected=(405,))
        self.check('不支持的方法保持 405', True)

    def train(self):
        job = self.call('POST','/api/calibration/jobs',expected=(202,),key='full-training')
        self.context['training_job'] = job['id']; self.save()
        self.wait(job['id'],'done')
        self.args.job=job['id']; self.model()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True); p.add_argument('--deployment-id',required=True)
    p.add_argument('--report',type=Path,required=True); p.add_argument('--source',type=Path)
    p.add_argument('--job'); p.add_argument('--phase',choices=('train','model','data','live','recover','cancel','interrupt-start','interrupt-check','outage','auto-start','auto-check','web'),required=True)
    args=p.parse_args()
    flow=Flow(args)
    getattr(flow,args.phase.replace('-','_'))()
    print(f'本阶段通过，报告：{flow.path}',flush=True)


if __name__ == '__main__': main()
