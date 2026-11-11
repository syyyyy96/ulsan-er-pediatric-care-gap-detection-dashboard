"""STEP 6. 시간 순서 기반 가용 병상 1·3시간 저병상 진입 경보 후향 검증.

기록 부족/양성 사건 부족 시 경보 성능 주장을 허용하지 않는다.
기준은 실행 결과를 보기 전에 정한 프로젝트 검토 기준(3일, 사건 10건,
정밀도 0.50, 재현율 0.30)이며 임상 기준이 아니다.
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import PROC, ROOT, save_json

DB = ROOT / "data" / "processed" / "live_beds.sqlite3"
FIELDS = {"hvec": "응급실", "hvicc": "일반 중환자실", "hvccc": "흉부 중환자실", "hvncc": "신생아 중환자실"}
HORIZONS = (1, 3)
MIN_DAYS = 3
MIN_EVENTS = 10
MIN_PRECISION = .50
MIN_RECALL = .30


def read_observations():
    if not DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as con:
        rows = con.execute("SELECT observed_at,hpid,name,payload FROM observations ORDER BY observed_at,hpid").fetchall()
    out = []
    for stamp, hpid, name, payload in rows:
        try:
            item = json.loads(payload)
            when = pd.Timestamp(stamp)
        except Exception:
            continue
        record = {"observed_at": when, "hpid": str(hpid), "name": str(name)}
        for f in FIELDS:
            try:
                v = int(item.get(f))
                record[f] = v if v >= 0 else np.nan
            except (TypeError, ValueError):
                record[f] = np.nan
        out.append(record)
    return pd.DataFrame(out)


def predict_at(past, horizon):
    seq = past[-49:]
    slopes = []
    for i in range(len(seq)):
        for j in range(i+1, len(seq)):
            hours = (seq[j][0]-seq[i][0]).total_seconds()/3600
            if hours >= .25:
                slopes.append((seq[j][1]-seq[i][1])/hours)
    slope = float(np.median(slopes)) if slopes else 0.0
    return max(0.0, seq[-1][1] + slope*horizon)


def metric_row(horizon, cases, days):
    y = np.array([x["actual"] for x in cases], dtype=bool)
    pred = np.array([x["alert"] for x in cases], dtype=bool)
    tp, fp = int((y & pred).sum()), int((~y & pred).sum())
    fn = int((y & ~pred).sum())
    precision = tp/(tp+fp) if tp+fp else None
    recall = tp/(tp+fn) if tp+fn else None
    if days < MIN_DAYS or int(y.sum()) < MIN_EVENTS:
        status = "insufficient"
    elif precision is not None and recall is not None and precision >= MIN_PRECISION and recall >= MIN_RECALL:
        status = "supported"
    else:
        status = "not_supported"
    return {"horizonHours": horizon, "status": status, "days": round(days, 2), "cases": len(cases),
        "events": int(y.sum()), "alerts": int(pred.sum()), "trueAlerts": tp, "falseAlerts": fp,
        "missedEvents": fn, "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "minimumDays": MIN_DAYS, "minimumEvents": MIN_EVENTS, "precisionThreshold": MIN_PRECISION,
        "recallThreshold": MIN_RECALL}


def main():
    observations = read_observations()
    if observations.empty:
        summary = {"status": "insufficient", "reason": "실시간 병상 관측 이력이 없습니다.", "periodDays": 0, "horizons": []}
        save_json(summary, PROC / "alert_backtest_summary.json")
        pd.DataFrame().to_csv(PROC / "alert_backtest.csv", index=False, encoding="utf-8-sig")
        print(summary["reason"])
        return
    first, last = observations.observed_at.min(), observations.observed_at.max()
    days = max(0, (last-first).total_seconds()/86400)
    all_cases = {h: [] for h in HORIZONS}
    detail = []
    for (hpid, name), inst in observations.groupby(["hpid", "name"]):
        inst = inst.sort_values("observed_at")
        for field in FIELDS:
            valid = inst.dropna(subset=[field])[["observed_at", field]].drop_duplicates("observed_at").sort_values("observed_at")
            seq = list(zip(valid.observed_at.tolist(), valid[field].astype(float).tolist()))
            for horizon in HORIZONS:
                cases = []
                for i in range(2, len(seq)-1):
                    past = seq[:i+1]
                    span = (past[-1][0]-past[0][0]).total_seconds()/60
                    if span < 30:
                        continue
                    target = past[-1][0] + pd.Timedelta(hours=horizon)
                    future = next(((t, v) for t, v in seq[i+1:] if t >= target), None)
                    if future is None:
                        continue
                    lag = (future[0]-target).total_seconds()/60
                    if lag > 25:
                        continue
                    estimate = predict_at(past, horizon)
                    case = {"actual": future[1] <= 1, "alert": estimate <= 1}
                    cases.append(case)
                    all_cases[horizon].append(case)
                if cases:
                    ys = [x["actual"] for x in cases]
                    ps = [x["alert"] for x in cases]
                    tp = sum(a and p for a,p in zip(ys,ps)); fp=sum((not a) and p for a,p in zip(ys,ps)); fn=sum(a and (not p) for a,p in zip(ys,ps))
                    detail.append({"기관": name, "병상유형": FIELDS[field], "예측시간": f"{horizon}시간",
                        "평가건수": len(cases), "실제저병상사건": sum(ys), "경보": sum(ps), "적중": tp, "오경보": fp, "미탐": fn})
    metrics = [metric_row(h, all_cases[h], days) for h in HORIZONS]
    overall = "insufficient" if any(x["status"] == "insufficient" for x in metrics) else (
        "supported" if all(x["status"] == "supported" for x in metrics) else "not_supported")
    summary = {"status": overall, "periodDays": round(days, 2), "firstObservedAt": first.isoformat(),
        "lastObservedAt": last.isoformat(), "targetDefinition": "예측 시점+h시간 가용 병상이 1석 이하",
        "predictionRule": "각 예측 시점 이전 기록만 사용한 최근 최대 49개 관측쌍의 시간당 변화량 중앙값 외삽; estimate <= 1이면 경보",
        "horizons": metrics, "thresholdsWereSpecifiedBeforeRun": True,
        "thresholdNote": "프로젝트 검토용 임계값이며 임상·운영 표준이 아닙니다.",
        "claimBoundary": "후향 검증은 향후 사건을 보장하지 않습니다. 기준 미충족/자료 부족 시 조기경보 성능을 주장하지 않습니다."}
    save_json(summary, PROC / "alert_backtest_summary.json")
    pd.DataFrame(detail).to_csv(PROC / "alert_backtest.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("STEP 6 완료")


if __name__ == "__main__":
    main()
