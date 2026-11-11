"""STEP 3d. 야간·휴일 소아 진료소 추가를 가정한 거리 접근성 시나리오.

이 결과는 기존 의료기관 좌표를 가상 후보지로 쓴 거리 계산이다. 개설 타당성,
수용능력, 이용자 수, 실제 접근 개선이나 건강 성과를 추정하지 않는다.
"""
import sys

import numpy as np
import pandas as pd

from common import PROC, RAW, save_json
from step3_access import flags
from step3c_priority import distances, points

RADII = (2.0, 3.0, 4.0)
ADD_COUNTS = (1, 3, 5)


def main():
    demand = points("facilities_all.csv")
    pediatric = points("facilities_pediatric.csv")
    if demand.empty or pediatric.empty:
        print("[건너뜀] 좌표가 포함된 병·의원과 소아의원 자료가 필요합니다.")
        sys.exit(2)
    late, holiday = flags(pediatric)
    providers = pediatric[late | holiday].copy().reset_index(drop=True)
    if providers.empty:
        summary = {"status": "insufficient", "reason": "야간 또는 휴일 진료시간이 등록된 소아의원이 없습니다.",
                   "claimBoundary": "거리 시나리오이며 실제 개선·개설 가능성·환자 수·건강결과를 뜻하지 않습니다."}
        save_json(summary, PROC / "scenario_summary.json")
        pd.DataFrame().to_csv(PROC / "scenario_access.csv", index=False, encoding="utf-8-sig")
        print(summary["reason"])
        return
    current = distances(demand, providers)
    candidate = demand[["lat", "lon"]].drop_duplicates().reset_index(drop=True)
    # Do not propose a duplicate site within 250 m of an existing after-hours pediatric provider.
    candidate["nearest_existing_km"] = distances(candidate.rename(columns={"lat":"lat", "lon":"lon"}), providers)
    candidate = candidate[candidate.nearest_existing_km > .25].reset_index(drop=True)
    if candidate.empty:
        print("[건너뜀] 추가 시나리오 후보 위치가 없습니다.")
        sys.exit(2)
    cand_dist = np.column_stack([
        distances(demand, candidate.iloc[[i]]) for i in range(len(candidate))
    ])
    rows, chosen_by_radius = [], {}
    for radius in RADII:
        best = current.copy()
        selected = []
        eligible = int((best <= radius).sum())
        base_count = eligible
        for k in range(1, max(ADD_COUNTS)+1):
            gains = []
            for j in range(len(candidate)):
                if j in selected:
                    gains.append(-np.inf)
                else:
                    new_best = np.minimum(best, cand_dist[:, j])
                    gains.append(float(np.maximum(best-new_best, 0).sum()))
            pick = int(np.argmax(gains))
            selected.append(pick)
            best = np.minimum(best, cand_dist[:, pick])
            covered = int((best <= radius).sum())
            if k in ADD_COUNTS:
                rows.append({"기준거리km": radius, "가정추가기관수": k, "기준내지점수_기존": base_count,
                    "기준내지점수_시나리오": covered,
                    "기준내지점비율_기존%": round(base_count/len(demand)*100, 1),
                    "기준내지점비율_시나리오%": round(covered/len(demand)*100, 1),
                    "변화_퍼센트포인트": round((covered-base_count)/len(demand)*100, 1),
                    "가상후보지": "; ".join(f"{candidate.iloc[j].lat:.4f},{candidate.iloc[j].lon:.4f}" for j in selected)})
        chosen_by_radius[str(radius)] = selected
    table = pd.DataFrame(rows)
    table.to_csv(PROC / "scenario_access.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "ready", "demandProxyPointCount": int(len(demand)),
        "currentAfterHoursPediatricProviderCount": int(len(providers)), "hypotheticalAddCounts": list(ADD_COUNTS),
        "distanceRadiiKm": list(RADII), "candidateSiteCount": int(len(candidate)),
        "selectedSitesByRadius": chosen_by_radius,
        "assumption": "기존 병·의원 좌표 중에서 야간·휴일 소아 진료기관이 추가된다고 가정하고, 전체 직선거리 합을 탐욕적으로 줄이는 후보지를 선택했습니다.",
        "claimBoundary": "시나리오상 직선거리 변화입니다. 실제 개설 가능성, 서비스 용량, 인구·이용자 수, 이동시간, 진료·건강 결과를 나타내지 않습니다."}
    save_json(summary, PROC / "scenario_summary.json")
    print(table.to_string(index=False))
    print("STEP 3d 완료: 가정 시나리오이며 실현된 개선 효과가 아닙니다.")


if __name__ == "__main__":
    main()
