"""시험용(가짜) 자료 만들기 — 실제 제출물에 쓰면 안 됩니다. 사용법: python dev_make_demo_data.py  (run_all.py --demo 가 자동 실행)"""
import numpy as np
import pandas as pd

from common import ROOT

D = ROOT / "data" / "demo"
D.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)
days = pd.date_range("2023-12-01", "2024-11-30")
rows = []
for sido, base in (("울산광역시", 55), ("부산광역시", 60), ("서울특별시", 70)):
    for day in days:
        for h in (3, 9, 15, 21):
            v = base + 12 * (day.dayofweek >= 5) + {3: -8, 9: 6, 15: 10, 21: 2}[h] + 8 * np.sin(day.dayofyear / 20) + rng.normal(0, 4)
            rows.append({"기준일자": day.strftime("%Y%m%d"), "시간대": f"{h:02d}:00", "시도": sido, "응급의료기관수": 6, "포화도": round(float(np.clip(v, 5, 99)), 1)})
pd.DataFrame(rows).to_csv(D / "demo_er_saturation.csv", index=False, encoding="cp949")
gus = ["남구", "중구", "동구", "북구", "울주군"]
ped = [{"dutyName": f"데모소아과{i}", "dutyAddr": f"울산광역시 {gus[i % 5]} 데모동", "dutyTime1c": "2000" if i % 2 else "1800", "dutyTime7s": "0900" if i % 3 == 0 else ""} for i in range(26)]
def _pts(n, c=(35.54, 129.31), sd=(0.06, 0.07)):
    return rng.normal(c[0], sd[0], n), rng.normal(c[1], sd[1], n)


la, lo = _pts(26)
for i, r in enumerate(ped):
    r["wgs84Lat"], r["wgs84Lon"] = la[i], lo[i]
la, lo = _pts(700)
pd.DataFrame({"dutyName": [f"데모의원{i}" for i in range(700)], "dutyAddr": [f"울산광역시 {gus[i % 5]} 데모동" for i in range(700)], "wgs84Lat": la, "wgs84Lon": lo}).to_csv(D / "facilities_all.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(ped).to_csv(D / "facilities_pediatric.csv", index=False, encoding="utf-8-sig")
er = [{"dutyName": f"데모병원{i}", "dutyAddr": f"울산광역시 {gus[i]} 데모동", "dutyEmclsName": "지역응급의료기관", "wgs84Lat": 35.5 + 0.03 * i, "wgs84Lon": 129.2 + 0.05 * i} for i in range(5)]
pd.DataFrame(er[:4]).to_csv(D / "facilities_er.csv", index=False, encoding="utf-8-sig")
pd.DataFrame({"구군": gus, "총인구": [100000, 330000, 150000, 220000, 230000], "0~14세인구": [11000, 42000, 15000, 33000, 30000]}).to_csv(D / "population_manual.csv", index=False, encoding="utf-8-sig")
print("시험용 자료 생성:", D)
