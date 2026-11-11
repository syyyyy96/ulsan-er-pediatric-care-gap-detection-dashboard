"""
STEP 3b. 거리 기반 '소아 의료 공백 생활권' 탐지 (비지도 군집 DBSCAN)

방법
  1) 울산 전체 병·의원 위치를 '생활권이 모여 있는 곳'의 대리 지표(수요 지점)로 씁니다. (인구 자료가 아님)
  2) 각 지점에서 가장 가까운 '소아 전문 의원(기관명에 소아 포함)'과 '지정 응급의료기관'까지 직선거리(km)를 계산합니다.
  3) 소아 전문 의원이 PED_FAR_KM 보다 먼 지점만 모아 DBSCAN(밀도 기반 군집)으로 묶어 '공백 생활권 후보'를 찾습니다.
입력: data/raw/facilities_all.csv, facilities_pediatric.csv, facilities_er.csv (STEP 1 결과, 위도·경도 열 필요)
출력: data/processed/gap_by_gu.csv, gap_clusters.csv, gap_summary.json, outputs/charts/gap_map.png, gap_distance.png
기준값(3km 등)은 임의로 정한 값이니 바꿔서 다시 실행해 볼 수 있습니다.
"""
import re
import sys

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from common import CHARTS, PROC, RAW, read_table, save_json, setup_font

PED_FAR_KM = 3.0
ER_FAR_KM = 8.0
EPS_KM, MIN_PTS = 1.5, 5
BBOX = (35.3, 35.8, 128.9, 129.6)     # 울산 대략 범위(좌표 오류 제거)


def gu_of(a):
    m = re.search(r"울산(?:광역시)?\s*([가-힣]+?[구군])", str(a))
    return m.group(1) if m else "기타"


def coords(df):
    la = next((c for c in df.columns if c.lower() in ("wgs84lat", "lat", "latitude", "위도")), None)
    lo = next((c for c in df.columns if c.lower() in ("wgs84lon", "lon", "longitude", "경도")), None)
    if la is None or lo is None:
        return None
    out = df.copy()
    out["lat"], out["lon"] = pd.to_numeric(out[la], errors="coerce"), pd.to_numeric(out[lo], errors="coerce")
    return out[out.lat.between(BBOX[0], BBOX[1]) & out.lon.between(BBOX[2], BBOX[3])].reset_index(drop=True)


def nearest_km(P, Q):
    la1, lo1 = np.radians(P.lat.values)[:, None], np.radians(P.lon.values)[:, None]
    la2, lo2 = np.radians(Q.lat.values)[None, :], np.radians(Q.lon.values)[None, :]
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return (2 * 6371 * np.arcsin(np.sqrt(a))).min(axis=1)


def load(name):
    p = RAW / name
    if not p.exists():
        return None
    try:
        d = read_table(p)
    except pd.errors.EmptyDataError:
        return None
    return coords(d) if len(d) else None


def main():
    allh, ped, er = load("facilities_all.csv"), load("facilities_pediatric.csv"), load("facilities_er.csv")
    if allh is None or ped is None or ped.empty or er is None or er.empty:
        print("[건너뜀] facilities_all / facilities_pediatric / facilities_er (위도·경도 포함)가 필요합니다. STEP 1 을 실행하세요.")
        sys.exit(2)
    if "dutyEmclsName" in er.columns:
        em = er["dutyEmclsName"].astype(str)
        des = er[em.str.contains("응급의료") & ~em.str.contains("이외")]
        er_use = des if len(des) else er
    else:
        er_use = er
    d = allh.copy()
    d["gu"] = d["dutyAddr"].map(gu_of) if "dutyAddr" in d.columns else "기타"
    d["ped_km"], d["er_km"] = nearest_km(d, ped), nearest_km(d, er_use)
    g = d[d.gu != "기타"].groupby("gu").agg(지점수=("lat", "size"), 소아의원_중앙거리km=("ped_km", "median"), 소아의원_90퍼센타일km=("ped_km", lambda x: x.quantile(.9)),
                                          응급기관_중앙거리km=("er_km", "median"), 응급기관_90퍼센타일km=("er_km", lambda x: x.quantile(.9))).round(2)
    g["소아의원_먼지점비율%"] = d[d.gu != "기타"].groupby("gu")["ped_km"].apply(lambda x: (x > PED_FAR_KM).mean() * 100).round(1)
    g["응급기관_먼지점비율%"] = d[d.gu != "기타"].groupby("gu")["er_km"].apply(lambda x: (x > ER_FAR_KM).mean() * 100).round(1)
    g = g.reset_index().rename(columns={"gu": "구군"}).sort_values("소아의원_먼지점비율%", ascending=False)
    g.to_csv(PROC / "gap_by_gu.csv", index=False, encoding="utf-8-sig")
    far = d[d.ped_km > PED_FAR_KM].copy()
    clusters = pd.DataFrame()
    if len(far) >= MIN_PTS:
        far["cl"] = DBSCAN(eps=EPS_KM / 6371, min_samples=MIN_PTS, metric="haversine", algorithm="ball_tree").fit_predict(np.radians(far[["lat", "lon"]]))
        rows = []
        for k, s in far[far.cl >= 0].groupby("cl"):
            rows.append({"군집": f"C{k + 1}", "지점수": len(s), "구군": s.gu.mode().iat[0], "위도": round(s.lat.mean(), 4), "경도": round(s.lon.mean(), 4),
                         "소아의원까지_평균km": round(s.ped_km.mean(), 2), "응급기관까지_평균km": round(s.er_km.mean(), 2)})
        clusters = pd.DataFrame(rows).sort_values("지점수", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
    clusters.to_csv(PROC / "gap_clusters.csv", index=False, encoding="utf-8-sig")
    save_json({"n_points": int(len(d)), "n_ped": int(len(ped)), "n_er": int(len(er_use)), "ped_far_km": PED_FAR_KM, "er_far_km": ER_FAR_KM, "eps_km": EPS_KM,
               "min_pts": MIN_PTS, "n_far": int(len(far)), "n_clusters": int(len(clusters)),
               "worst_gu": g.iloc[0]["구군"] if len(g) else None}, PROC / "gap_summary.json")
    plt = setup_font()
    fig, ax = plt.subplots(figsize=(7, 6.4))
    ax.scatter(d.lon, d.lat, s=3, c="#C9D1DA", label="병·의원 위치(생활권 대리 지표)")
    if len(far):
        ax.scatter(far.lon, far.lat, s=7, c="#E0A060", label=f"소아 의원 {PED_FAR_KM:g}km 초과 지점")
    ax.scatter(ped.lon, ped.lat, s=26, marker="^", c="#0B2545", label="소아 전문 의원")
    ax.scatter(er_use.lon, er_use.lat, s=34, marker="s", c="#B33A0B", label="지정 응급의료기관")
    for _, r in clusters.head(6).iterrows():
        ax.annotate(f"{r['군집']}({int(r['지점수'])})", (r["경도"], r["위도"]), fontsize=9, weight="bold", xytext=(4, 4), textcoords="offset points")
    ax.set_aspect(1 / np.cos(np.radians(35.54)))
    ax.set_title("울산 소아 의료 공백 생활권 후보 (군집)"); ax.legend(fontsize=7, loc="lower left", frameon=False); ax.axis("off")
    fig.savefig(CHARTS / "gap_map.png", dpi=150, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = np.arange(len(g)); w = 0.38
    ax.bar(x - w / 2, g["소아의원_중앙거리km"], w, color="#0B2545", label="가장 가까운 소아 전문 의원(중앙값)")
    ax.bar(x + w / 2, g["응급기관_중앙거리km"], w, color="#B33A0B", label="가장 가까운 지정 응급의료기관(중앙값)")
    ax.set_xticks(x); ax.set_xticklabels(g["구군"]); ax.set_ylabel("직선거리(km)"); ax.legend(fontsize=7, frameon=False)
    ax.set_title("구·군별 가장 가까운 기관까지의 거리"); ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(CHARTS / "gap_distance.png", dpi=150, bbox_inches="tight"); plt.close(fig)
    print(g.to_string(index=False))
    print(f"먼 지점 {len(far)}개 → 군집 {len(clusters)}개")
    print("STEP 3b 완료")


if __name__ == "__main__":
    main()
