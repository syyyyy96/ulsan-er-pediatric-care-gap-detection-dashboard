"""
STEP 1. 울산 소아청소년과 의원·병원 목록과 응급의료기관 목록을 공공데이터포털 API(무료)로 내려받기

필요: .env 의 인증키 + 아래 두 서비스의 활용신청(승인)
  - 국립중앙의료원_전국 병·의원 찾기 서비스
  - 국립중앙의료원_전국 응급의료기관 정보 조회 서비스
결과: data/raw/facilities_pediatric.csv, facilities_er.csv, facilities_meta.json

※ 서비스 주소와 요청 변수는 제가 알고 있는 형식이라 포털 화면과 다를 수 있습니다.
   오류가 나면 화면의 오류 문구를 그대로 알려주세요(인증키는 알리지 마세요).
"""
import os
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from common import RAW, env_key, save_json

BASE = os.environ.get("NMC_API_BASE", "http://apis.data.go.kr/B552657")
SIDO = "울산광역시"
PEDIATRIC_CODE = "D002"          # 진료과목 코드: 소아청소년과 (확인 필요)
HOSPITAL_LIST = f"{BASE}/HsptlAsembySearchService/getHsptlMdcncListInfoInqire"
ER_LIST = f"{BASE}/ErmctInfoInqireService/getEgytListInfoInqire"


def call(url, key, params):
    q = urlencode({"serviceKey": key, **params}, quote_via=quote)
    last = None
    for _ in range(3):
        try:
            with urlopen(Request(f"{url}?{q}", headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as r:
                return ET.fromstring(r.read())
        except Exception as e:
            last = e
            time.sleep(1.5)
    sys.exit(f"[요청 실패] {type(last).__name__}: {last}\n  → 인증키 승인 전이거나 서비스 주소가 다를 수 있습니다.")


def fetch_all(url, key, params, rows=500):
    out, page, total = [], 1, None
    while True:
        root = call(url, key, {**params, "pageNo": page, "numOfRows": rows})
        code = root.findtext(".//resultCode")
        if code not in (None, "00"):
            sys.exit(f"[API 오류] 코드 {code}: {root.findtext('.//resultMsg')}")
        items = root.findall(".//item")
        out += [{c.tag: (c.text or "").strip() for c in it} for it in items]
        total = int(root.findtext(".//totalCount") or len(out))
        if not items or len(out) >= total:
            return out
        page += 1


if __name__ == "__main__":
    key = env_key()
    if not key:
        print("[건너뜀] .env 에 인증키가 없습니다. (인증키 신청 후 .env 에 DATA_GO_KR_SERVICE_KEY=키 를 적고 다시 실행)")
        sys.exit(3)
    meta = {}
    allh = fetch_all(HOSPITAL_LIST, key, {"Q0": SIDO})                              # 울산 전체 병·의원
    listed = fetch_all(HOSPITAL_LIST, key, {"Q0": SIDO, "QD": PEDIATRIC_CODE})     # 진료과목 코드 조회(참고용)
    ped = [h for h in allh if "소아" in h.get("dutyName", "")]                      # 기관명에 '소아' 포함 = 소아 전문 의원 추정
    meta["pediatric_method"] = "기관명에 '소아'가 들어간 곳(소아 전문 의원 추정). 진료과목만 등록한 일반 의원은 제외"
    er = fetch_all(ER_LIST, key, {"Q0": SIDO})
    pd.DataFrame(allh).to_csv(RAW / "facilities_all.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(ped).to_csv(RAW / "facilities_pediatric.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(listed).to_csv(RAW / "facilities_pediatric_listed.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(er).to_csv(RAW / "facilities_er.csv", index=False, encoding="utf-8-sig")
    meta.update({"all_count": len(allh), "pediatric_count": len(ped), "listed_count": len(listed), "er_count": len(er)})
    save_json(meta, RAW / "facilities_meta.json")
    print(f"울산 전체 병·의원 {len(allh)}곳 중 소아 전문 의원(이름 기준) {len(ped)}곳, 진료과목 코드 조회 {len(listed)}곳(참고), 응급의료기관 {len(er)}곳 저장")
    print("STEP 1 완료")
