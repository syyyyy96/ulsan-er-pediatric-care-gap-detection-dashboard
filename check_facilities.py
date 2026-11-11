"""울산 병·의원 목록(API로 받은 파일)이 제대로인지 확인합니다. 사용법: python check_facilities.py"""
import re

import pandas as pd

from common import RAW, read_table


def gu(a):
    m = re.search(r"울산(?:광역시)?\s*([가-힣]+?[구군])", str(a))
    return m.group(1) if m else "기타"


for fn, label in (("facilities_pediatric.csv", "소아청소년과(진료과목 조회)"), ("facilities_er.csv", "응급의료기관")):
    p = RAW / fn
    if not p.exists():
        print(f"[없음] {fn}")
        continue
    d = read_table(p)
    print("=" * 60)
    print(f"{label}: {len(d)}곳 | 열 {len(d.columns)}개")
    if "dutyAddr" in d.columns:
        print("구·군별:", d["dutyAddr"].map(gu).value_counts().to_dict())
    for c in ("dutyDivName", "dutyEmclsName"):
        if c in d.columns:
            print(f"{c}:", d[c].value_counts().head(8).to_dict())
    if "dutyName" in d.columns:
        n = d["dutyName"].astype(str).str.contains("소아").sum()
        print(f"이름에 '소아'가 들어간 곳: {n}곳 ({n / max(len(d), 1):.0%})")
        print("이름 예시(앞 15개):", list(d["dutyName"].astype(str).head(15)))
print("\n→ '이름에 소아가 들어간 곳' 비율이 낮고 내과·가정의학과 이름이 많이 보이면, 진료과목에 소아청소년과를 함께 적은 기관까지 포함된 것입니다.")
