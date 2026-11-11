"""
STEP 3. 울산 구·군별 소아·응급 의료 접근성 비교 (규칙 기반 지표, AI 아님)

입력: data/raw/facilities_pediatric.csv, facilities_er.csv (STEP 1 결과 또는 직접 받은 목록)
      data/raw/population_manual.csv (구·군별 총인구, 0~14세 인구를 직접 적은 표 - 선택)
출력: data/processed/access_table.csv, access_summary.json, outputs/charts/access_score.png

지표: 소아전문의원 수 / 평일 20시 이후 진료 소아전문의원 수 / 일요일·공휴일 진료 소아전문의원 수 / 응급의료기관 수
      (인구가 있으면 아동 1만 명당, 응급은 10만 명당으로 환산)
점수: 각 지표를 구·군끼리 0~1로 맞춰 평균 x 100 (높을수록 접근 양호). 점수가 낮은 곳이 '취약 후보'입니다.
"""
import re
import sys

import numpy as np
import pandas as pd

from common import CHARTS, PROC, RAW, load_json, read_table, save_json, setup_font

GUS = ["중구", "남구", "동구", "북구", "울주군"]


def safe_read(p):
    try:
        return read_table(p)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def gu_of(addr):
    m = re.search(r"울산(?:광역시)?\s*([가-힣]+?[구군])", str(addr))
    return m.group(1) if m else "기타"


def hhmm(v):
    s = re.sub(r"\D", "", str(v))
    return int(s[:4]) if len(s) >= 3 else np.nan


def flags(df):
    close_cols = [c for c in df.columns if re.fullmatch(r"dutyTime[1-5]c", c)]
    late = (df[close_cols].map(hhmm).max(axis=1) >= 2000) if close_cols else pd.Series(False, index=df.index)
    hol_cols = [c for c in df.columns if c in ("dutyTime7s", "dutyTime8s")]
    hol = df[hol_cols].map(hhmm).notna().any(axis=1) if hol_cols else pd.Series(False, index=df.index)
    return late.fillna(False), hol


def main():
    fp, fe = RAW / "facilities_pediatric.csv", RAW / "facilities_er.csv"
    if not fp.exists() and not fe.exists():
        print("[건너뜀] data/raw 에 facilities_pediatric.csv / facilities_er.csv 가 없습니다. (STEP 1 실행 또는 직접 넣기)")
        sys.exit(2)
    rows = {g: {"구군": g, "소아전문의원": 0, "진료과목등록(참고)": 0, "지정응급의료기관": 0, "평일20시이후진료": 0, "일요일공휴일진료": 0, "응급의료기관": 0} for g in GUS}
    if fp.exists():
        ped = safe_read(fp)
        ped["gu"] = ped["dutyAddr"].map(gu_of) if "dutyAddr" in ped.columns else "기타"
        ped["late"], ped["hol"] = flags(ped) if len(ped) else (pd.Series(dtype=bool), pd.Series(dtype=bool))
        for g, sub in ped.groupby("gu"):
            if g in rows:
                rows[g].update({"소아전문의원": len(sub), "평일20시이후진료": int(sub.late.sum()), "일요일공휴일진료": int(sub.hol.sum())})
    if fe.exists():
        er = safe_read(fe)
        er["gu"] = er["dutyAddr"].map(gu_of) if "dutyAddr" in er.columns else "기타"
        for g, sub in er.groupby("gu"):
            if g in rows:
                rows[g]["응급의료기관"] = len(sub)
                if "dutyEmclsName" in sub.columns:
                    em = sub["dutyEmclsName"].astype(str)
                    rows[g]["지정응급의료기관"] = int((em.str.contains("응급의료") & ~em.str.contains("이외")).sum())
    fl = RAW / "facilities_pediatric_listed.csv"
    if fl.exists():
        lst = safe_read(fl)
        if "dutyAddr" in lst.columns:
            for g, sub in lst.groupby(lst["dutyAddr"].map(gu_of)):
                if g in rows:
                    rows[g]["진료과목등록(참고)"] = len(sub)
    t = pd.DataFrame(rows.values())
    pop_path = RAW / "population_manual.csv"
    per_pop, child = False, "아동"
    if pop_path.exists():
        pop = read_table(pop_path)
        child = re.sub(r"인구$", "", str(pop.columns[2])) if len(pop.columns) > 2 else "아동"
        pop.columns = ["구군", "총인구", "아동인구"][:len(pop.columns)]
        pop[["총인구", "아동인구"]] = pop[["총인구", "아동인구"]].apply(pd.to_numeric, errors="coerce")
        if pop["총인구"].notna().any() and pop["총인구"].median() < 10000:
            pop[["총인구", "아동인구"]] *= 1000
            print("[안내] 인구 값이 '천 명' 단위로 보여 1000배 해서 계산했습니다. (202.43 → 202,430명)")
        t = t.merge(pop, on="구군", how="left")
        per_pop = bool(t[["총인구", "아동인구"]].notna().all().all() and (t[["총인구", "아동인구"]] > 0).all().all())
    if per_pop:
        t[f"소아전문의원({child} 1만명당)"] = t["소아전문의원"] / t["아동인구"] * 1e4
        t[f"평일20시이후({child} 1만명당)"] = t["평일20시이후진료"] / t["아동인구"] * 1e4
        t[f"일요일공휴일({child} 1만명당)"] = t["일요일공휴일진료"] / t["아동인구"] * 1e4
        t["응급의료기관(10만명당)"] = t["응급의료기관"] / t["총인구"] * 1e5
        cols = [c for c in t.columns if "당)" in c]
    else:
        print("[안내] 인구 자료가 비어 있어 개수 그대로 비교합니다. population_manual.csv 를 채우면 인구 대비로 계산합니다.")
        cols = ["소아전문의원", "평일20시이후진료", "일요일공휴일진료", "응급의료기관"]
    z = t[cols].apply(lambda s: (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else pd.Series(0.5, index=s.index))
    t["접근성점수"] = (z.mean(axis=1) * 100).round(1)
    t["취약순위"] = t["접근성점수"].rank(method="min").astype(int)
    t = t.sort_values("취약순위")
    t.round(2).to_csv(PROC / "access_table.csv", index=False, encoding="utf-8-sig")
    meta = load_json(RAW / "facilities_meta.json") or {}
    save_json({"per_population": per_pop, "metrics": cols, "pediatric_method": meta.get("pediatric_method", "직접 받은 목록"),
               "lowest": t.iloc[0]["구군"], "n_ped": int(t["소아전문의원"].sum()), "n_er": int(t["응급의료기관"].sum())}, PROC / "access_summary.json")
    plt = setup_font()
    fig, ax = plt.subplots(figsize=(7, 3.4))
    s = t.sort_values("접근성점수", ascending=False)
    ax.barh(s["구군"], s["접근성점수"], color=["#B33A0B" if g == t.iloc[0]["구군"] else "#0B2545" for g in s["구군"]])
    ax.invert_yaxis(); ax.set_xlabel("접근성 점수 (낮을수록 취약 후보)"); ax.set_title("울산 구·군별 소아·응급 의료 접근성")
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(CHARTS / "access_score.png", dpi=150, bbox_inches="tight")
    print(t[["구군"] + cols[:2] + ["접근성점수", "취약순위"]].to_string(index=False))
    print("STEP 3 완료")


if __name__ == "__main__":
    main()
