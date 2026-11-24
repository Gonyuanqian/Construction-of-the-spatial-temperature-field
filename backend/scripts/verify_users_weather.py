"""Real Java/Python/MySQL acceptance in a new, isolated database and free ports.

No production records are read or modified. Keeps the test database and logs for
review. Requires the prior weather-chain archive as explicitly supplied input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid

import pymysql
import requests

from tfield.weather_runtime import package_models


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation-root', type=Path, required=True)
    parser.add_argument('--java', required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--interactive', action='store_true', help='Pause before cleanup for local browser QA; create continue file to resume')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    archive = args.evaluation_root.resolve()
    run = project / '.local' / f'backend-users-test-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}'
    run.mkdir(parents=True)
    database = 'tfield_users_test_' + uuid.uuid4().hex[:12]
    java_port, python_port = free_port(), free_port()
    while java_port == python_port:
        python_port = free_port()
    admin_secret = secrets.token_urlsafe(24)
    user_secret = secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update(TFIELD_MYSQL_DB=database, TFIELD_JAVA_PORT=str(java_port),
               TFIELD_JAVA_HOST='127.0.0.1', TFIELD_PYTHON_URL=f'http://127.0.0.1:{python_port}',
               TFIELD_BUSINESS_URL=f'http://127.0.0.1:{java_port}',
               TFIELD_INTERNAL_TOKEN=secrets.token_urlsafe(32), TFIELD_MODEL_STORE_MODE='java',
               TFIELD_BOOTSTRAP_ADMIN_USERNAME='acceptadmin', TFIELD_BOOTSTRAP_ADMIN_PASSWORD=admin_secret,
               PYTHONPATH=str(project / 'backend/src'), PYTHONUNBUFFERED='1')
    env.pop('TFIELD_JDBC_URL', None)  # Cannot accidentally point at an existing production URL.
    if args.interactive:
        env['TFIELD_FRONTEND_ORIGINS'] = 'http://127.0.0.1:5174'
    for key, folder in [('TFIELD_DATASET_STORAGE_ROOT', 'datasets'), ('TFIELD_TRAINING_ROOT', 'training'),
                        ('TFIELD_LIVE_SESSION_ROOT', 'live'), ('TFIELD_LIVE_SOURCE_ROOT', 'live-source'),
                        ('TFIELD_WEATHER_MODEL_ROOT', 'models'), ('TFIELD_WEATHER_RESULT_ROOT', 'results'),
                        ('TFIELD_ASSISTANT_STATE_ROOT','assistant')]:
        env[key] = str(run / folder)
    db_args = dict(host=env.get('TFIELD_MYSQL_HOST', '127.0.0.1'), port=int(env.get('TFIELD_MYSQL_PORT', '3306')),
                   user=env.get('TFIELD_MYSQL_USER', 'root'), password=env.get('TFIELD_MYSQL_PASSWORD', '123456'),
                   charset='utf8mb4', autocommit=True)
    with pymysql.connect(**db_args) as conn, conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4')
    packages = {}
    for schema in ('two', 'full'):
        packages[schema] = package_models(run / 'models', archive / f'models/{schema}_current_00.pkl',
            archive / f'models/{schema}_history_00.pkl', archive / 'inputs/saved.artifact.bin', 3, schema)
    checks, children, logs = [], [], []
    http = requests.Session()
    http.trust_env = False
    base = f'http://127.0.0.1:{java_port}'

    def check(label, condition):
        checks.append({'check': label, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(label)

    def api(label, method, path, status=200, token=None, body=None):
        response = http.request(method, base + path, json=body,
            headers={'Authorization': f'Bearer {token}'} if token else {}, timeout=180)
        check(f'{label} (HTTP {status})', response.status_code == status)
        return response.json()

    def login(name, password):
        return api('login ' + name, 'POST', '/api/auth/login', body={'username': name, 'password': password})['access_token']

    report = {'database': database, 'checks': checks, 'run_directory': str(run)}
    try:
        for name, command, cwd in [('python', [sys.executable, '-X', 'utf8', '-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', str(python_port)], project / 'backend'),
                                   ('java', [args.java, '-jar', str(args.jar.resolve())], project)]:
            stream = (run / f'{name}.log').open('w', encoding='utf-8')
            logs.append(stream)
            children.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('An isolated service exited; inspect logs')
            try:
                if http.get(base + '/ops/health', timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Isolated services did not become ready')
        origin = env.get('TFIELD_FRONTEND_ORIGINS', 'http://127.0.0.1:5173').split(',')[0]
        response = http.options(base + '/api/auth/login', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
        check('configured frontend origin accepted', response.status_code == 200 and response.headers.get('Access-Control-Allow-Origin') == origin)
        response = http.options(base + '/api/auth/login', headers={'Origin': 'https://untrusted.invalid', 'Access-Control-Request-Method': 'POST'})
        check('unconfigured frontend origin rejected', response.status_code == 403)
        with pymysql.connect(**db_args, database=database) as conn, conn.cursor() as cur:
            metadata = json.loads((archive / 'inputs/selected-model.json').read_text('utf-8'))
            cur.execute('INSERT INTO model(id,name,saved_at,dataset_sig,groups_sig,data_file,data_start,data_end,mae,rmse,r2,is_current,bundle,artifact) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s)',
                tuple(metadata[k] for k in ['id', 'name', 'saved_at', 'dataset_sig', 'groups_sig', 'data_file', 'data_start', 'data_end', 'mae', 'rmse', 'r2']) +
                ((archive / 'inputs/bundle.json').read_text('utf-8'), (archive / 'inputs/saved.artifact.bin').read_bytes()))
            cur.execute("SELECT COUNT(*) FROM tfield_java_schema_history WHERE success=1 AND version='5'")
            check('MySQL V5 migration installed', cur.fetchone()[0] == 1)
            cur.execute("SELECT COUNT(*) FROM tfield_java_schema_history WHERE success=1 AND version='6'")
            check('MySQL V6 archive migration installed', cur.fetchone()[0] == 1)
        api('anonymous legacy blocked', 'GET', '/api/models', 401)
        api('wrong password', 'POST', '/api/auth/login', 401, body={'username': 'acceptadmin', 'password': 'incorrect'})
        admin = login('acceptadmin', admin_secret)
        api('administrator legacy geometry passes compute boundary', 'GET', '/api/field/arch', token=admin)
        api('administrator legacy model context passes compute boundary', 'GET', '/api/models', token=admin)
        me = api('administrator identity', 'GET', '/api/auth/me', token=admin)
        api('last active administrator cannot be disabled', 'PATCH', '/api/admin/users/' + me['id'], 409, admin,
            {'display_name': '管理员', 'role': 'ADMIN', 'enabled': False})
        users, houses, tokens = [], [], []
        locations = [dict(province_code='220000', city_code=city) for city in ('220600', '220200')]
        dimensions = dict(length_m=18., width_m=2.1, height_m=1.3017)
        for index in (1, 2):
            user = api('create user', 'POST', '/api/admin/users', token=admin,
                body={'username': f'acceptuser{index}', 'display_name': f'用户{index}', 'password': user_secret, 'role': 'USER'})
            users.append(user)
            tokens.append(login(user['username'], user_secret))
            house = api('create greenhouse', 'POST', '/api/admin/greenhouses', token=admin, body={'name': f'棚体{index}', 'location': locations[index-1], **dimensions})
            houses.append(house)
        user = tokens[0]
        idle=api('weather live idle without sensor files','GET','/api/live/status',token=user)
        check('weather live begins idle',idle['state']=='idle' and idle['total']==0 and idle['input_mode']=='external_weather')
        api('prepare no longer reads a 24-sensor file','POST','/api/live/prepare',422,user)
        api('file replay remains administrator only','GET','/api/replay/status',403,user)
        capabilities=api('user can open AgriSeek','GET','/api/assistant/capabilities',token=user)
        check('user assistant follows weather data',capabilities['data_mode']=='external_weather')
        api('user conversation list initially empty','GET','/api/assistant/conversations',token=user)
        api('user cannot list accounts', 'GET', '/api/admin/users', 403, user)
        api('user cannot train', 'POST', '/api/calibration/run', 403, user, {})
        api('user cannot read legacy shared workspace', 'GET', '/api/models', 403, user)
        visible = api('user greenhouse list', 'GET', '/api/user/greenhouses', token=user)
        check('shared catalog visible without grants', len(visible) == 2)
        api('shared archive is accessible', 'GET', '/api/user/greenhouses/' + houses[1]['id'], token=user)
        regions = api('shared region dictionary', 'GET', '/api/user/regions', token=user)
        check('official dictionary 9 cities 60 districts', len(regions['cities']) == 9 and sum(len(c['districts']) for c in regions['cities']) == 60)
        model_ids = {}
        for schema in ('two', 'full'):
            model = api('register ' + schema, 'POST', '/api/admin/weather-models', token=admin,
                body={'name': schema, 'package_id': packages[schema]['package_id']})
            model_ids[schema] = model['id']
            api('draft cannot be assigned', 'PUT', f"/api/admin/greenhouses/{houses[0]['id']}/weather-model", 409, admin, {'weather_model_id': model['id']})
            api('publish ' + schema, 'PATCH', '/api/admin/weather-models/' + model['id'], token=admin, body={'status': 'PUBLISHED'})
            api('assign ' + schema, 'PUT', f"/api/admin/greenhouses/{houses[0 if schema == 'two' else 1]['id']}/weather-model", token=admin,
                body={'weather_model_id': model['id']})
        path = f"/api/user/greenhouses/{houses[0]['id']}"
        start = datetime(2026, 11, 4, 4, tzinfo=timezone.utc)
        frames = []
        for i in range(13):
            body = {'location': locations[0], 'timestamp': (start + timedelta(minutes=5*i)).isoformat(), 'bg_temp': 25. + i*.05, 'bg_light': 1000.}
            frame = api(f'two-input frame {i}', 'POST', '/api/live/weather' if i%2==0 else '/api/user/weather', token=user, body=body)
            frames.append(frame)
        check('cold start uses current model', frames[0]['summary']['stage1_mode'] == 'current_only')
        check('one hour switches to history model', frames[-1]['summary']['stage1_mode'] == 'history_1h')
        check('24 predicted nodes and humidity provenance', len(frames[-1]['summary']['node_temperatures']) == 24 and frames[-1]['summary']['humidity_source'] == 'predicted_external')
        current=api('live observes same canonical weather result','GET','/api/live/status',token=user)
        check('live and weather observation identical',current['session_id']==frames[-1]['id'] and current['cursor']==0 and current['total']==1)
        prepared=api('prepare accepts external weather body','POST','/api/live/prepare',token=user,body=body)
        check('prepare reuses same weather result',prepared['session_id']==frames[-1]['id'])
        other_idle=api('other user live state isolated','GET','/api/live/status',token=tokens[1])
        check('other user cannot see current live observation',other_idle['state']=='idle')
        sid=frames[-1]['id']
        section=api('legacy section shape now weather based','GET',f'/api/live/frame/0?session_id={sid}',token=user)
        check('virtual nodes never labeled measured sensors',section['frame']['sensor_temps']==[None]*24 and len(section['frame']['predicted_sensor_temps'])==24 and section['frame']['bg_temp']==body['bg_temp'])
        volume=api('legacy volume shape now weather based','GET',f'/api/live/volume/0?session_id={sid}',token=user)
        check('all live source planes virtual',len(volume['planes'])==37 and all(not p['measured'] for p in volume['planes']))
        check('legacy views keep local time consistent',section['time']==volume['time'] and section['time'].endswith('+08:00'))
        reduced=api('existing mean-curve query supported','GET',f'/api/live/volume/0?session_id={sid}&y_step=3',token=user)
        check('mean-curve has seven saved planes',len(reduced['planes'])==7)
        api('live point reads same snapshot grid','GET',f'/api/live/point/0?session_id={sid}&x=1&y=9&z=.7&expected_ref={volume["field_ref"]}',token=user)
        api('live point rejects another field reference','GET',f'/api/live/point/0?session_id={sid}&x=1&y=9&z=.7&expected_ref=wrong',409,user)
        api('cannot select another account result via session id','GET',f'/api/live/volume/0?session_id={sid}',409,tokens[1])
        api('stale live observation rejected','GET',f'/api/live/volume/0?session_id={frames[0]["id"]}',409,user)
        api('no fabricated next weather frame','POST','/api/live/next',409,user)
        api('unsupported live grid rejected','GET','/api/live/volume/0?y_step=.25',422,user)
        api('24 measured node input rejected by live','POST','/api/live/weather',422,user,{**body,'sensor_temps':[25.]*24})
        retry = api('identical input idempotent', 'POST', '/api/user/weather', token=user, body=body)
        check('retry returns original id', retry['id'] == frames[-1]['id'])
        api('conflicting input rejected', 'POST', '/api/user/weather', 409, user, {**body, 'bg_temp': 99.})
        api('naive timestamp rejected', 'POST', '/api/user/weather', 422, user, {**body, 'timestamp': '2026-11-04T13:00:00'})
        api('indoor input rejected', 'POST', '/api/user/weather', 422, user, {**body, 'indoor_temp': [25.]*24})
        field = api('persisted field', 'GET', path + f"/frames/{frames[-1]['id']}/field", token=user)
        check('37 planes all marked virtual', len(field['field']['planes']) == 37 and all(not p['measured'] for p in field['field']['planes']))
        api('cross-user result blocked', 'GET', path + f"/frames/{frames[-1]['id']}/field", 404, tokens[1])
        api('result cannot be relabeled as another house', 'GET', f"/api/user/greenhouses/{houses[1]['id']}/frames/{frames[-1]['id']}/field", 404, tokens[1])
        path2 = f"/api/user/greenhouses/{houses[1]['id']}"
        api('full model requires humidity', 'POST', '/api/user/weather', 422, tokens[1], {**body, 'location': locations[1]})
        full = api('full input constructs field', 'POST', '/api/user/weather', token=tokens[1], body={**body, 'location': locations[1], 'bg_rh': 70.})
        check('full schema uses observed external humidity', full['summary']['humidity_source'] == 'observed_external')
        updated=api('new weather submission updates live current','GET','/api/live/status',token=tokens[1])
        check('user weather endpoint drives same live state',updated['session_id']==full['id'])
        check('full model advertises humidity requirement','bg_rh' in updated['required_inputs'])
        # Administrator preview and assistant bind to the administrator's own weather, not global replay.
        admin_frame=api('administrator weather monitoring','POST','/api/live/weather',token=admin,body=body)
        snapshot=api('assistant snapshot uses weather result','POST','/api/assistant/snapshots',token=admin,body={'frame_index':0})
        check('assistant provenance is weather prediction',snapshot['source']=='virtual_weather_prediction' and snapshot['session_id']==admin_frame['id'])
        check('assistant facts never claim recorded sensors',all(f.get('origin')!='recorded_sensor' for f in snapshot['facts']))
        user_snapshot=api('user captures own weather snapshot','POST','/api/assistant/snapshots',token=user,body={'frame_index':0})
        other_snapshot=api('other user captures own weather snapshot','POST','/api/assistant/snapshots',token=tokens[1],body={'frame_index':0})
        api('user reads own assistant snapshot','GET','/api/assistant/snapshots/'+user_snapshot['snapshot_id'],token=user)
        api('other user cannot read assistant snapshot','GET','/api/assistant/snapshots/'+user_snapshot['snapshot_id'],404,tokens[1])
        api('user cannot read administrator snapshot','GET','/api/assistant/snapshots/'+snapshot['snapshot_id'],404,user)
        api('other user cannot attach foreign snapshot to question','POST','/api/assistant/runs',404,tokens[1],{'request_key':str(uuid.uuid4()),'question':'查询点温','snapshot_id':user_snapshot['snapshot_id']})
        seed_code = """
import json,sys,uuid
from api.assistant import store
from api.assistant.ownership import owner_scope
output=[]
for index,owner in enumerate(json.loads(sys.argv[1])):
    with owner_scope(owner):
        chat=str(uuid.uuid4())
        run,_=store.create_run(str(uuid.uuid4()),{'conversation_id':chat,'question':'隔离测试私有会话'+str(index)})
        store.update_run(run['id'],status='answered',result={'claims':[],'citations':[],'snapshot':{}})
        output.append({'conversation_id':chat,'run_id':run['id']})
print(json.dumps(output))
"""
        seeded = json.loads(subprocess.check_output([sys.executable,'-X','utf8','-c',seed_code,json.dumps([u['id'] for u in users])],cwd=project/'backend',env=env,text=True))
        for index in (0,1):
            chats=api('user private conversations','GET','/api/assistant/conversations',token=tokens[index])
            check('only own assistant conversation visible',len(chats)==1 and chats[0]['id']==seeded[index]['conversation_id'])
            api('own assistant run','GET','/api/assistant/runs/'+seeded[index]['run_id'],token=tokens[index])
        for suffix in ('','/events','/stream'):
            api('cross-account conversation protected','GET','/api/assistant/conversations/'+seeded[0]['conversation_id']+suffix,404,tokens[1])
        api('cross-account run cancel protected','POST','/api/assistant/runs/'+seeded[0]['run_id']+'/cancel',404,tokens[1])
        forged=http.get(base+'/api/assistant/runs/'+seeded[0]['run_id'],headers={'Authorization':'Bearer '+tokens[1],'X-TField-Assistant-Owner':users[0]['id']},timeout=15)
        check('caller cannot forge assistant owner',forged.status_code==404)
        # Same archive, same time, different users: independent input and results.
        other = api('second account uses same archive', 'POST', '/api/user/weather', token=tokens[1], body=body)
        check('separate result id and cold start', other['id'] != frames[-1]['id'] and other['summary']['stage1_mode'] == 'current_only')
        own = api('private history', 'GET', path + '/frames', token=user)
        theirs = api('other account private history', 'GET', path + '/frames', token=tokens[1])
        check('histories are isolated', len(own) == 13 and len(theirs) == 1 and theirs[0]['id'] == other['id'])
        match = api('match city default', 'POST', '/api/user/weather/match', token=user, body={'location': locations[0]})
        check('city matched automatically', match['archive']['id'] == houses[0]['id'] and match['match_level'] == 'city')
        county = {**locations[0], 'district_code': '220621'}
        fallback = api('district falls back to city', 'POST', '/api/user/weather/match', token=user, body={'location': county})
        check('explicit city fallback', fallback['match_level'] == 'city')
        # Different locations that share a city archive must not share weather history.
        same_time = api('district stream separate from city', 'POST', '/api/user/weather', token=user, body={**body, 'location': county})
        check('district stream cold start', same_time['summary']['stage1_mode'] == 'current_only')
        scoped = api('location filtered history', 'GET', path + '/frames?region_code=220621', token=user)
        check('location filter retained', len(scoped) == 1 and scoped[0]['id'] == same_time['id'])
        api('duplicate city coverage rejected', 'POST', '/api/admin/greenhouses', 409, admin, {'name': '重复', 'location': locations[0], **dimensions})
        api('cross-city code rejected', 'POST', '/api/user/weather/match', 422, user, {'location': {**locations[1], 'district_code': '220621'}})
        api('uncovered city reported', 'POST', '/api/user/weather/match', 404, user, {'location': {'province_code': '220000', 'city_code': '220800'}})
        dedicated = api('create district archive', 'POST', '/api/admin/greenhouses', token=admin, body={'name': '抚松县专用', 'location': county, **dimensions})
        exact = api('district takes precedence', 'POST', '/api/user/weather/match', token=user, body={'location': county})
        check('district precedence including unready archives', exact['archive']['id'] == dedicated['id'] and not exact['archive']['ready'])
        api('unready district must not silently use city', 'POST', '/api/user/weather', 409, user, {**body, 'location': county})
        api('configure district model', 'PUT', f"/api/admin/greenhouses/{dedicated['id']}/weather-model", token=admin, body={'weather_model_id': model_ids['two']})
        api('stop district matching', 'PATCH', f"/api/admin/greenhouses/{dedicated['id']}", token=admin, body={'name': '抚松县专用', 'location': county, **dimensions, 'enabled': False})
        reverted = api('disabled district uses explicit city default', 'POST', '/api/user/weather/match', token=user, body={'location': county})
        check('disabled archive excluded', reverted['archive']['id'] == houses[0]['id'])
        changed = api('edit archive after result', 'PATCH', '/api/admin/greenhouses/' + houses[0]['id'], token=admin, body={'name': '新档案名称', 'location': locations[0], **dimensions, 'enabled': True})
        prior = api('read original immutable snapshot', 'GET', path + '/frames?region_code=220600', token=user)
        check('history retains archive snapshot', prior[0]['archive_snapshot']['name'] == '棚体1' and prior[0]['location']['city_name'] == '白山市')
        next_body = {**body, 'timestamp': (start + timedelta(minutes=65)).isoformat()}
        updated_frame = api('changed config resets history context', 'POST', '/api/user/weather', token=user, body=next_body)
        check('new config cold start', updated_frame['summary']['stage1_mode'] == 'current_only')
        invalid_size = api('store other dimensions', 'POST', '/api/admin/greenhouses', token=admin, body={'name': '尺寸不兼容', 'location': {'province_code': '220000', 'city_code': '220100'}, **dimensions, 'width_m': 3.})
        api('bind model for dimension check', 'PUT', f"/api/admin/greenhouses/{invalid_size['id']}/weather-model", token=admin, body={'weather_model_id': model_ids['two']})
        api('unsupported scaling rejected', 'POST', '/api/user/weather', 409, user, {**body, 'location': {'province_code': '220000', 'city_code': '220100'}})
        if args.interactive:
            # Disposable local test identities only. Never reuse a production password.
            (run / 'browser-accounts.json').write_text(json.dumps({'url': base,
                'admin': {'username': 'acceptadmin', 'password': admin_secret},
                'user': {'username': 'acceptuser1', 'password': user_secret}}, indent=2), 'utf-8')
            print(json.dumps({'browser_qa_ready': True, 'api': base, 'run_directory': str(run)}, ensure_ascii=False), flush=True)
            while not (run / 'continue').exists():
                if any(child.poll() is not None for child in children):
                    raise RuntimeError('A browser QA service exited')
                time.sleep(1)
        api('disable deployment', 'PATCH', '/api/admin/weather-models/' + model_ids['two'], token=admin, body={'status': 'DISABLED'})
        api('disabled deployment cannot construct', 'POST', '/api/user/weather', 409, user, {**body, 'timestamp': (start + timedelta(hours=2)).isoformat()})
        api('saved own result remains readable after model disabled', 'GET', path + f"/frames/{frames[-1]['id']}/field", token=user)
        api('admin resets password', 'POST', '/api/admin/users/' + users[0]['id'] + '/password', token=admin, body={'password': secrets.token_urlsafe(24)})
        api('password reset revokes token', 'GET', '/api/auth/me', 401, user)
        api('disable account', 'PATCH', '/api/admin/users/' + users[1]['id'], token=admin, body={'display_name': '用户2', 'role': 'USER', 'enabled': False})
        api('disabled account token revoked', 'GET', '/api/auth/me', 401, tokens[1])
        api('logout', 'POST', '/api/auth/logout', token=admin)
        api('logged out token revoked', 'GET', '/api/auth/me', 401, admin)
        check('Python legacy endpoint rejects direct callers', http.get(f'http://127.0.0.1:{python_port}/api/models').status_code == 403)
        report['passed'] = True
    except Exception as exc:
        report['passed'] = False
        report['error'] = str(exc)
        raise
    finally:
        for child in reversed(children):
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for stream in logs:
            stream.close()
        (run / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
        print(json.dumps({'passed': report.get('passed', False), 'checks': len(checks), 'report': str(run / 'report.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
