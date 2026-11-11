"""
(선택) 응급실 실시간 가용 병상을 일정 간격으로 모아 data/raw/er_snapshots.csv 에 쌓기

과거 자료를 못 받았을 때의 대안입니다. 켜 둔 시간만큼만 쌓이므로 양이 적습니다(결과 해석에 한계가 큽니다).
사용법(맥에서 잠자기를 막으려면 앞에 caffeinate -i 를 붙입니다):
    caffeinate -i python collect_er_snapshots.py            # 10분 간격, 72시간
    caffeinate -i python collect_er_snapshots.py 10 48      # 10분 간격, 48시간
멈추려면 Ctrl + C
※ 서비스 주소는 제가 알고 있는 형식이라 다를 수 있습니다.
"""
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from common import RAW, env_key

BASE = os.environ.get("NMC_API_BASE", "http://apis.data.go.kr/B552657")
URL = f"{BASE}/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire"
OUT = RAW / "er_snapshots.csv"


def once(key):
    q = urlencode({"serviceKey": key, "STAGE1": "울산광역시", "pageNo": 1, "numOfRows": 100}, quote_via=quote)
    with urlopen(Request(f"{URL}?{q}", headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as r:
        root = ET.fromstring(r.read())
    code = root.findtext(".//resultCode")
    if code not in (None, "00"):
        raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [{"collected_at": now, "시도": "울산광역시", **{c.tag: (c.text or "").strip() for c in it}} for it in root.findall(".//item")]


if __name__ == "__main__":
    key = env_key()
    if not key:
        sys.exit("[오류] .env 에 DATA_GO_KR_SERVICE_KEY=인증키 가 없습니다.")
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    hours = float(sys.argv[2]) if len(sys.argv) > 2 else 72
    end, n = time.time() + hours * 3600, 0
    print(f"{minutes:g}분 간격으로 {hours:g}시간 동안 수집합니다. 멈추려면 Ctrl + C")
    while time.time() < end:
        try:
            rows = once(key)
            pd.DataFrame(rows).to_csv(OUT, mode="a", header=not OUT.exists(), index=False, encoding="utf-8-sig")
            n += 1
            print(f"[{datetime.now():%m-%d %H:%M}] {len(rows)}개 기관 저장 (누적 {n}회)")
        except Exception as e:
            print(f"[{datetime.now():%m-%d %H:%M}] 실패: {e}  (다음 간격에 다시 시도)")
        time.sleep(minutes * 60)
