"""STEP 3c. 거리 공백 후보의 민감도 점검과 현장 확인 순서 산출.

시설 좌표를 생활권의 대리 지점으로 사용한다. 정책 우선순위를 자동 확정하지 않고,
거리·군집 기준을 바꿔도 반복해서 나타나는 후보만 추가 확인 대상으로 표시한다.
"""
import json
import sys

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from common import PROC, RAW, read_table, save_json
from step3_access import flags, gu_of

MIN_PTS = 3
DISTANCE_THRESHOLDS = (2.0, 3.0, 4.0)
EPS_VALUES = (1.0, 1.5, 2.0)
BASE_DISTANCE = 3.0
BASE_EPS = 1.5


def points(name):
    p = RAW / name
    if not p.exists():
        return pd.DataFrame()
    d = read_table(p)
    for c in ("wgs84Lat", "wgs84Lon"):
        if c not in d:
            return pd.DataFrame()
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["wgs84Lat", "wgs84Lon"]).copy()
    d = d.rename(columns={"wgs84Lat": "lat", "wgs84Lon": "lon"})
    return d[d.lat.between(35.30, 35.75) & d.lon.between(128.95, 129.55)].reset_index(drop=True)


def distances(a, b):
    if not len(b):
        return np.full(len(a), np.nan)
    la1, lo1 = np.radians(a.lat.to_numpy())[:, None], np.radians(a.lon.to_numpy())[:, None]
    la2, lo2 = np.radians(b.lat.to_numpy())[None, :], np.radians(b.lon.to_numpy())[None, :]
    hav = np.sin((la2-la1)/2)**2 + np.cos(la1)*np.cos(la2)*np.sin((lo2-lo1)/2)**2
    return (2*6371*np.arcsin(np.sqrt(np.clip(hav, 0, 1)))).min(axis=1)


def clusters_for(d, threshold, eps_km):
    mask = d.ped_km > threshold
    labels = np.full(len(d), -1, dtype=int)
    if mask.sum() >= MIN_PTS:
        labels[mask.to_numpy()] = DBSCAN(eps=eps_km/6371, min_samples=MIN_PTS,
            metric="haversine", algorithm="ball_tree").fit_predict(
                np.radians(d.loc[mask, ["lat", "lon"]].to_numpy()))
    return labels


def normalized(s):
    s = pd.to_numeric(s, errors="coerce").fillna(0)
    if s.max() == s.min():
        return pd.Series(0.5, index=s.index)
    return (s-s.min())/(s.max()-s.min())


def main():
    d, ped, er = points("facilities_all.csv"), points("facilities_pediatric.csv"), points("facilities_er.csv")
    if d.empty or ped.empty or er.empty:
        print("[건너뜀] 좌표가 포함된 시설·소아·응급기관 목록이 필요합니다.")
        sys.exit(2)
    late, holiday = flags(ped)
    after = ped[late | holiday].copy()
    d["gu"] = d["dutyAddr"].map(gu_of) if "dutyAddr" in d else "기타"
    d["ped_km"] = distances(d, ped)
    d["after_hours_km"] = distances(d, after)
    d["er_km"] = distances(d, er)

    point_presence = np.zeros(len(d), dtype=float)
    combo_count = 0
    for threshold in DISTANCE_THRESHOLDS:
        for eps in EPS_VALUES:
            labels = clusters_for(d, threshold, eps)
            point_presence += (labels >= 0)
            combo_count += 1
    d["stability_pct"] = (100*point_presence/combo_count).round(1)
    labels = clusters_for(d, BASE_DISTANCE, BASE_EPS)
    base = d.assign(cluster=labels)
    rows = []
    for cid, g in base[base.cluster >= 0].groupby("cluster"):
        night = g.after_hours_km.dropna()
        er_dist = g.er_km.dropna()
        p90 = float(g.ped_km.quantile(.9))
        if len(night) and float(night.mean()) > float(g.ped_km.mean()) + .5:
            reason = "야간·휴일 소아 진료 접근 추가 점검"
        elif len(er_dist) and float(er_dist.mean()) > 8:
            reason = "응급기관 직선거리 추가 점검"
        else:
            reason = "소아기관 접근 후보 현장 확인"
        rows.append({"군집": f"C{int(cid)+1}", "구군": str(g.gu.mode().iat[0]), "지점수": int(len(g)),
            "소아기관_평균직선거리km": round(float(g.ped_km.mean()), 2), "소아기관_90퍼센타일km": round(p90, 2),
            "야간휴일소아기관_평균직선거리km": round(float(night.mean()), 2) if len(night) else None,
            "응급기관_평균직선거리km": round(float(er_dist.mean()), 2) if len(er_dist) else None,
            "민감도안정성%": round(float(g.stability_pct.mean()), 1), "점검유형": reason})
    clusters = pd.DataFrame(rows)
    if len(clusters):
        # Explicitly illustrative score weights; ranking is for field-check order only.
        clusters["severity_n"] = normalized(clusters["소아기관_평균직선거리km"])
        clusters["size_n"] = normalized(clusters["지점수"])
        clusters["stability_n"] = clusters["민감도안정성%"] / 100
        scenarios = {"거리중심": (.5, .3, .2), "규모중심": (.3, .5, .2), "안정성중심": (.3, .2, .5)}
        ranks = []
        for name, (wd, ws, wr) in scenarios.items():
            score = wd*clusters.severity_n + ws*clusters.size_n + wr*clusters.stability_n
            clusters[f"{name}점수"] = (score*100).round(1)
            clusters[f"{name}순위"] = score.rank(method="min", ascending=False).astype(int)
            ranks.append(clusters[f"{name}순위"] <= 3)
        clusters["일관된상위후보"] = (clusters["민감도안정성%"] >= (100*6/9)) & pd.concat(ranks, axis=1).all(axis=1)
        clusters = clusters.sort_values(["일관된상위후보", "안정성중심순위", "소아기관_평균직선거리km"], ascending=[False, True, False])
        clusters = clusters.drop(columns=["severity_n", "size_n", "stability_n"])
    out = PROC / "priority_clusters.csv"
    clusters.to_csv(out, index=False, encoding="utf-8-sig")
    top = clusters[clusters.get("일관된상위후보", pd.Series(dtype=bool)) == True].to_dict("records") if len(clusters) else []
    summary = {"status": "ready", "demandProxyPointCount": int(len(d)), "pediatricProviderCount": int(len(ped),),
        "afterHoursHolidayProviderCount": int(len(after)), "emergencyProviderCount": int(len(er)),
        "distanceThresholdsKm": list(DISTANCE_THRESHOLDS), "clusterRadiusKm": list(EPS_VALUES),
        "baselineDistanceKm": BASE_DISTANCE, "baselineClusterRadiusKm": BASE_EPS,
        "minClusterPoints": MIN_PTS, "combinationCount": combo_count,
        "clusterCount": int(len(clusters)), "consistentTopCandidates": top,
        "claimBoundary": "후보 점검 순서이며 취약지역 확정, 실제 수요, 개설 가능성 또는 건강결과를 뜻하지 않습니다.",
        "scoreWeights": {k: {"거리": v[0], "규모": v[1], "안정성": v[2]} for k, v in scenarios.items()}}
    save_json(summary, PROC / "priority_summary.json")
    print(f"수요 대리지점 {len(d)}곳 · 야간/휴일 소아기관 {len(after)}곳 · 기준 군집 {len(clusters)}개")
    if len(clusters): print(clusters.to_string(index=False))
    print("STEP 3c 완료: 추가 현장 확인 순서를 산출했습니다.")


if __name__ == "__main__":
    main()
