"""
공공데이터 API 확인 도구 (인증키는 .env 파일에서 읽고, 화면에는 출력하지 않습니다)

준비:  프로젝트 폴더에 '.env' 파일을 만들고 한 줄을 적습니다.
        DATA_GO_KR_SERVICE_KEY=공공데이터포털에서 받은 인증키   (예전 이름 DATA_GO_KR_KEY 도 읽습니다)
사용:  python probe_api.py "요청주소"
        요청주소 안의 인증키 자리를 {KEY} 로 바꿔서 넣으세요. 예)
        python probe_api.py "http://apis.data.go.kr/.../서비스이름?serviceKey={KEY}&pageNo=1&numOfRows=5"

결과: 응답 구조를 화면에 보여주고, 표로 읽히면 data/raw/api_probe_<시각>.csv 로 저장합니다.
"""
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

import json
import pandas as pd

ROOT = Path(__file__).resolve().parent


def read_key():
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("[오류] .env 파일이 없습니다. 파일 안에 DATA_GO_KR_SERVICE_KEY=인증키 한 줄을 적어주세요.")
    found = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            found[k.strip()] = v.strip().strip('"').strip("'")
    for name in ("DATA_GO_KR_SERVICE_KEY", "DATA_GO_KR_KEY"):
        if found.get(name):
            return quote(unquote(found[name]), safe="")        # 인코딩/디코딩 키 어느 쪽을 넣어도 동작
    sys.exit("[오류] .env 에 DATA_GO_KR_SERVICE_KEY=... 줄이 없거나 비어 있습니다.")


def xml_to_df(text):
    root = ET.fromstring(text)
    for tag in ("resultCode", "resultMsg", "totalCount"):
        el = root.find(f".//{tag}")
        if el is not None:
            print(f"  {tag}: {el.text}")
    items = root.findall(".//item")
    if not items:
        return None
    return pd.DataFrame([{c.tag: (c.text or "") for c in it} for it in items])


def json_to_df(text):
    obj = json.loads(text)

    def find(o, d=0):
        if isinstance(o, list) and o and isinstance(o[0], dict):
            return o
        if isinstance(o, dict) and d < 6:
            for v in o.values():
                r = find(v, d + 1)
                if r:
                    return r
        return None

    r = find(obj)
    return pd.json_normalize(r) if r else None


if __name__ == "__main__":
    if len(sys.argv) < 2 or "{KEY}" not in sys.argv[1]:
        sys.exit('사용법: python probe_api.py "요청주소(인증키 자리는 {KEY})"')
    url = sys.argv[1].replace("{KEY}", read_key())
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            text = r.read().decode("utf-8", errors="replace")
            print(f"응답 코드: {r.status}")
    except Exception as e:
        sys.exit(f"[요청 실패] {type(e).__name__}: {e}   (인증키 승인 전이거나 주소가 틀렸을 수 있습니다)")
    head = text.lstrip()[:1]
    try:
        df = xml_to_df(text) if head == "<" else json_to_df(text)
    except Exception as e:
        print("[해석 실패]", e)
        print(text[:600])
        sys.exit(1)
    if df is None or df.empty:
        print("표로 읽을 수 있는 목록이 없습니다. 응답 앞부분:")
        print(text[:600])
        sys.exit(0)
    print(f"행 {len(df)}개, 열 {df.shape[1]}개")
    print("열 이름과 예시:")
    for c in df.columns:
        print(f"  - {c}: {str(df[c].iloc[0])[:30]}")
    out = ROOT / "data" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"api_probe_{datetime.now():%Y%m%d_%H%M%S}.csv"
    df.to_csv(f, index=False, encoding="utf-8-sig")
    print(f"저장: {f.relative_to(ROOT)}")
