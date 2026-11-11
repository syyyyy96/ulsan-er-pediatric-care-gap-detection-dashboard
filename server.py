#!/usr/bin/env python3
"""Local Ulsan emergency bed availability collector and dashboard API."""
import datetime as dt
import json
import os
import sqlite3
import ssl
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs'
DB = ROOT / 'data' / 'processed' / 'live_beds.sqlite3'
API_URL = 'https://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire'
POLL_SECONDS = 900
FIELDS = {'hvec': '응급실 가용 병상', 'hvicc': '일반 중환자실 가용 병상', 'hvccc': '흉부 중환자실 가용 병상', 'hvncc': '신생아 중환자실 가용 병상'}

def load_env():
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))

def write_env(updates):
    """.env 의 해당 키 줄만 바꾸거나 추가합니다. 다른 줄과 주석은 그대로 둡니다."""
    env = ROOT / '.env'
    lines = env.read_text(encoding='utf-8').splitlines() if env.exists() else []
    names = {l.split('=', 1)[0].strip() for l in lines if '=' in l and not l.strip().startswith('#')}
    if 'DATA_GO_KR_SERVICE_KEY' in updates and 'DATA_GO_KR_KEY' in names:   # 예전 이름 줄이 있으면 함께 맞춤
        updates = {**updates, 'DATA_GO_KR_KEY': updates['DATA_GO_KR_SERVICE_KEY']}
    out, done = [], set()
    for line in lines:
        k = line.split('=', 1)[0].strip() if '=' in line and not line.strip().startswith('#') else None
        if k in updates:
            if k not in done:
                out.append(f'{k}={updates[k]}')
                done.add(k)
        else:
            out.append(line)
    out += [f'{k}={v}' for k, v in updates.items() if k not in done]
    env.write_text('\n'.join(out) + '\n', encoding='utf-8')
    os.chmod(env, 0o600)

def api_key():
    load_env()
    return os.environ.get('DATA_GO_KR_SERVICE_KEY', '').strip()

def set_collector_state(key, value):
    with db_conn() as c:
        c.execute('INSERT OR REPLACE INTO collector_state VALUES (?,?)', (key, str(value)))
        c.commit()

def get_collector_state():
    with db_conn() as c:
        return {r['key']: r['value'] for r in c.execute('SELECT key,value FROM collector_state')}

def db_conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS observations (
      observed_at TEXT NOT NULL, hpid TEXT NOT NULL, name TEXT NOT NULL, address TEXT,
      category TEXT, payload TEXT NOT NULL, PRIMARY KEY(observed_at,hpid))''')
    c.execute('CREATE TABLE IF NOT EXISTS collector_state (key TEXT PRIMARY KEY, value TEXT)')
    c.commit()
    return c

def parse_response(raw):
    try:
        obj = json.loads(raw)
        body = obj.get('response', {}).get('body', {})
        items = body.get('items', {}).get('item', [])
        if isinstance(items, dict): items = [items]
        return items or []
    except (json.JSONDecodeError, AttributeError):
        root = ET.fromstring(raw)
        return [{child.tag: child.text for child in node} for node in root.findall('.//item')]

def hospital_lookup():
    import csv
    path = ROOT / 'data' / 'raw' / 'facilities_er.csv'
    if not path.exists(): return {}
    with path.open(encoding='utf-8-sig', newline='') as f:
        return {r.get('hpid',''): r for r in csv.DictReader(f) if r.get('hpid')}

def fetch_ulsan():
    key = api_key()
    if not key:
        raise RuntimeError('서비스 인증키가 없습니다. 프로젝트 폴더의 .env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.')
    set_collector_state('last_attempt_at', dt.datetime.now().astimezone().isoformat(timespec='seconds'))
    params = urllib.parse.urlencode({'serviceKey': key, 'STAGE1': '울산광역시', 'numOfRows': '100', 'pageNo': '1', '_type': 'json'})
    req = urllib.request.Request(API_URL + '?' + params, headers={'User-Agent': 'UlsanCareDashboard/1.0'})
    cafile = os.environ.get('SSL_CERT_FILE') or ('/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').exists() else None)
    context = ssl.create_default_context(cafile=cafile)
    with urllib.request.urlopen(req, timeout=20, context=context) as response:
        raw = response.read().decode('utf-8')
    items = parse_response(raw)
    lookup = hospital_lookup()
    # Use the approved real-time bed operation; join stable names/addresses by NMC hospital ID.
    if lookup:
        items = [x for x in items if str(x.get('hpid') or '') in lookup]
    else:
        items = [x for x in items if '울산' in str(x.get('dutyAddr', ''))]
    if not items:
        raise RuntimeError('API 응답에서 울산 의료기관을 찾지 못했습니다. 인증키와 API 신청 상태를 확인하세요.')
    observed = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    with db_conn() as c:
        for item in items:
            hpid = str(item.get('hpid') or item.get('dutyName') or 'unknown')
            facility = lookup.get(hpid, {})
            c.execute('INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?)',
                      (observed, hpid, str(facility.get('dutyName') or item.get('dutyName') or '기관명 미제공'), str(facility.get('dutyAddr') or item.get('dutyAddr') or ''), str(facility.get('dutyEmclsName') or item.get('dutyDivNam') or ''), json.dumps(item, ensure_ascii=False)))
        c.commit()
    set_collector_state('last_success_at', observed)
    set_collector_state('last_success_count', len(items))
    set_collector_state('last_error', '')
    return {'observedAt': observed, 'count': len(items)}

def latest_rows():
    with db_conn() as c:
        latest = c.execute('SELECT MAX(observed_at) FROM observations').fetchone()[0]
        if not latest: return None, []
        rows = c.execute('SELECT * FROM observations WHERE observed_at=? ORDER BY name', (latest,)).fetchall()
    result = []
    lookup = hospital_lookup()
    for r in rows:
        p = json.loads(r['payload'])
        meta = lookup.get(r['hpid'], {})
        vals = {}
        for key, label in FIELDS.items():
            raw = p.get(key)
            try:
                value = int(raw)
                if value < 0: value = None
            except (TypeError, ValueError): value = None
            vals[key] = {'label': label, 'available': value}
        result.append({'hpid': r['hpid'], 'name': r['name'], 'address': r['address'], 'category': r['category'], 'phone': meta.get('dutyTel3') or meta.get('dutyTel1') or p.get('dutyTel3') or p.get('dutyTel1'), 'lat': meta.get('wgs84Lat'), 'lon': meta.get('wgs84Lon'), 'beds': vals})
    return latest, result

def history_rows(hours=168):
    cutoff = (dt.datetime.now().astimezone() - dt.timedelta(hours=hours)).isoformat(timespec='seconds')
    with db_conn() as c:
        rows = c.execute('SELECT observed_at,hpid,name,payload FROM observations WHERE observed_at>=? ORDER BY observed_at', (cutoff,)).fetchall()
    out = []
    for r in rows:
        p = json.loads(r['payload'])
        rec = {'observedAt': r['observed_at'], 'hpid': r['hpid'], 'name': r['name']}
        for k in FIELDS:
            try: rec[k] = int(p.get(k))
            except (TypeError, ValueError): rec[k] = None
        out.append(rec)
    return out

def history_coverage():
    hist = history_rows(72)
    stamps = sorted({r['observedAt'] for r in hist if r.get('observedAt')})
    if not stamps:
        return {'snapshotCount': 0, 'rowCount': 0, 'firstObservedAt': None, 'lastObservedAt': None, 'spanMinutes': 0}
    first = dt.datetime.fromisoformat(stamps[0])
    last = dt.datetime.fromisoformat(stamps[-1])
    return {'snapshotCount': len(stamps), 'rowCount': len(hist), 'firstObservedAt': stamps[0],
            'lastObservedAt': stamps[-1], 'spanMinutes': max(0, round((last-first).total_seconds()/60))}

def forecast_rows():
    hist = history_rows(72)
    by = {}
    for r in hist:
        for field in FIELDS:
            v = r.get(field)
            if v is not None and v >= 0:
                by.setdefault((r['hpid'], r['name'], field), []).append((r['observedAt'], v))
    forecasts = []
    for (hpid, name, field), seq in by.items():
        seq = seq[-49:]
        first, last = dt.datetime.fromisoformat(seq[0][0]), dt.datetime.fromisoformat(seq[-1][0])
        span_minutes = max(0, round((last-first).total_seconds()/60))
        if len(seq) < 3 or span_minutes < 30:
            continue
        times = [dt.datetime.fromisoformat(t).timestamp() for t, _ in seq]
        vals = [v for _, v in seq]
        slopes = []
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                dh = (times[j]-times[i])/3600
                if dh >= 0.25:
                    slopes.append((vals[j]-vals[i])/dh)
        slopes.sort()
        slope = slopes[len(slopes)//2] if slopes else 0
        current = vals[-1]
        if len(seq) >= 12 and span_minutes >= 180: evidence = '3시간 이상 관측'
        elif len(seq) >= 8 and span_minutes >= 120: evidence = '2시간 이상 관측'
        else: evidence = '초기 관측 · 낮은 참고성'
        direction = '증가 추세' if slope >= 1 else ('감소 추세' if slope <= -1 else '큰 변화 없음')
        forecasts.append({'hpid': hpid, 'name': name, 'field': field, 'label': FIELDS[field], 'current': current,
                          'hours': [{'ahead': h, 'availableEstimate': max(0, round(current+slope*h, 1))} for h in (1, 3)],
                          'samples': len(seq), 'spanMinutes': span_minutes, 'evidence': evidence,
                          'direction': direction, 'method': '최근 관측 쌍별 시간당 변화량 중앙값', 'validated': False})
    field_order = {k: i for i, k in enumerate(FIELDS)}
    forecasts.sort(key=lambda x: (field_order[x['field']], x['current'], x['name']))
    return forecasts

def status_info():
    latest, rows = latest_rows()
    key_present = bool(api_key())
    state = get_collector_state()
    age_minutes = None
    if latest:
        try: age_minutes = max(0, round((dt.datetime.now().astimezone()-dt.datetime.fromisoformat(latest)).total_seconds()/60))
        except ValueError: pass
    expected = len(hospital_lookup())
    stale = age_minutes is not None and age_minutes > max(30, (POLL_SECONDS*2)//60)
    return {'configured': key_present, 'lastObservedAt': latest, 'institutionCount': len(rows),
            'expectedInstitutionCount': expected, 'pollMinutes': POLL_SECONDS//60, 'ageMinutes': age_minutes,
            'stale': stale, 'lastAttemptAt': state.get('last_attempt_at'), 'lastError': state.get('last_error') or '',
            'message': '수신 중' if latest and not stale else ('자료 지연' if latest else ('API 키가 설정되지 않았습니다.' if not key_present else '아직 수집된 관측이 없습니다.'))}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(OUT), **kwargs)
    def send_json(self, data, code=200):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(raw))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith('/api/health'): return self.send_json(status_info())
        if self.path.startswith('/api/current'):
            latest, rows = latest_rows(); return self.send_json({'observedAt': latest, 'institutions': rows, 'status': status_info()})
        if self.path.startswith('/api/history'):
            try: hours = min(720, max(1, int(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('hours', ['168'])[0])))
            except ValueError: hours = 168
            return self.send_json({'observations': history_rows(hours), 'status': status_info()})
        if self.path.startswith('/api/forecast'): return self.send_json({'forecasts': forecast_rows(), 'coverage': history_coverage(), 'status': status_info()})
        return super().do_GET()
    def do_POST(self):
        if self.path == '/api/configure':
            origin = self.headers.get('Origin', '')
            local_origin = f'http://127.0.0.1:{self.server.server_port}'
            if origin != local_origin: return self.send_json({'error': '허용되지 않은 요청'}, 403)
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.send_json({'error': 'JSON 요청만 허용됩니다.'}, 415)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                key = str(body.get('serviceKey', '')).strip()
                if len(key) < 32 or any(ch.isspace() for ch in key): return self.send_json({'error': '인증키 형식을 확인해 주세요.'}, 400)
                write_env({'DATA_GO_KR_SERVICE_KEY': key, 'ULSAN_DASHBOARD_PORT': str(self.server.server_port)})
                os.environ['DATA_GO_KR_SERVICE_KEY'] = key
                try:
                    result = fetch_ulsan()
                    return self.send_json({'ok': True, 'saved': True, **result})
                except Exception as e:
                    return self.send_json({'ok': False, 'saved': True, 'error': str(e)}, 502)
            except Exception:
                return self.send_json({'error': '인증키를 저장하지 못했습니다.'}, 400)
        if self.path != '/api/refresh': return self.send_json({'error': 'not found'}, 404)
        try: result = fetch_ulsan(); return self.send_json({'ok': True, **result})
        except Exception as e:
            set_collector_state('last_error', str(e))
            return self.send_json({'ok': False, 'error': str(e)}, 502)
    def log_message(self, fmt, *args): print('%s - %s' % (self.log_date_time_string(), fmt % args))

def poll_loop():
    while True:
        try:
            if api_key():
                print('자동 수집:', fetch_ulsan())
        except Exception as e:
            set_collector_state('last_error', str(e))
            print('자동 수집 실패:', e)
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    load_env(); db_conn().close()
    threading.Thread(target=poll_loop, daemon=True).start()
    host, port = '127.0.0.1', int(os.environ.get('ULSAN_DASHBOARD_PORT', '8000'))
    print(f'울산 의료 접근성 대시보드: http://{host}:{port}/index.html')
    ThreadingHTTPServer((host, port), Handler).serve_forever()
