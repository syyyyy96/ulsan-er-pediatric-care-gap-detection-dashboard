"""대시보드와 보고서 초안이 함께 쓰는 본문 조각 (결과 파일이 있는 부분만 만들어집니다)"""
import base64
import html

import pandas as pd

from common import CHARTS, DEMO, PROC, RAW, REGION, load_json, read_table

WD = ["월", "화", "수", "목", "금", "토", "일"]
e = html.escape


def img(name, alt):
    p = CHARTS / name
    if not p.exists():
        return ""
    return f'<figure class="chart narrow"><img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" alt="{e(alt)}"></figure>'


def table(head, rows):
    th = "".join(f"<th>{e(str(h))}</th>" for h in head)
    tb = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'


def verdict_text(v):
    c = v.get("code")
    if c == "small":
        return f"시험에 쓸 수 있는 관측이 {v.get('n_test', 0)}개로 적어 AI 모델이 낫다/아니다를 판단하기 어렵습니다."
    bk, rel = v.get("best_baseline", ""), v.get("rel_improvement_pct", 0)
    if c == "better":
        return (f"AI 모델의 평균 오차가 가장 좋은 단순 기준({bk})보다 {rel:.1f}% 작았고 모든 시험 구간에서 앞섰습니다. "
                "다만 시험 기간이 짧아 참고용입니다.")
    if c == "worse":
        return f"AI 모델의 평균 오차가 가장 좋은 단순 기준({bk})보다 {abs(rel):.1f}% 컸습니다. 이 자료에서는 AI 모델이 낫다고 말할 수 없습니다."
    return (f"AI 모델과 가장 좋은 단순 기준({bk})의 평균 오차 차이가 {rel:+.1f}%로 작거나 일관되지 않아, "
            "단순 기준보다 낫다고 말하기 어렵습니다.")


def er_html():
    ev = load_json(PROC / "er_eval.json")
    if not ev:
        return ""
    pv_path = PROC / "er_pattern.csv"
    worst = ""
    if pv_path.exists():
        pv = pd.read_csv(pv_path, index_col=0)
        s = pv.stack()
        k = s.idxmin() if ev["worse_is_low"] else s.idxmax()
        worst = (f"요일·시간대 평균으로는 <b>{WD[int(k[0])]}요일 {int(float(k[1]))}시</b>가 가장 혼잡했습니다"
                 f"({ev['target']} 평균 {s[k]:.1f}).")
    low = "낮을수록" if ev["worse_is_low"] else "높을수록"
    out = [f"<section><h2>{e(ev.get('subject', '응급실'))} 병상 혼잡 패턴과 예측 시험</h2>",
           f"<p>자료: <b>{e(str(ev['source']))}</b> — 울산 행만 골라 '{e(ev['target'])}'을(를) {ev['aggregate']}으로 합쳐 시계열을 만들었습니다"
           f"(관측 {ev['n_obs']:,}개, {ev['from'][:10]} ~ {ev['to'][:10]}). 값이 {low} 혼잡한 것으로 해석했습니다. {worst}</p>",
           img("er_pattern.png", "요일 시간대별 평균")]
    folds = ev.get("folds", [])
    if folds:
        methods = list(folds[0]["MAE"].keys())
        head = ["방법"] + [f"MAE {f['test_from']}~{f['test_to']}" for f in folds] + [f"혼잡 알림 F1 {f['test_from'][5:]}~" for f in folds]
        rows = [[m] + [f["MAE"][m] for f in folds] + [("-" if f["F1"][m] is None else f["F1"][m]) for f in folds] for m in methods]
        out += ["<h3 style='font-size:15px;margin:22px 0 6px'>과거 자료만 보고 다음 관측값을 맞히는 시험</h3>",
                f"<p>{e(verdict_text(ev['verdict']))}</p>", img("er_eval.png", "예측 시험 평균 오차"), table(head, rows),
                img("er_example.png", "실제와 예측"),
                "<p class='note'>MAE는 평균 오차(작을수록 좋음), F1은 훈련 구간 기준 상위 25% 혼잡 시간대를 얼마나 잘 알려주는지(클수록 좋음)입니다. "
                "예측은 '바로 다음 관측값 1단계'이고, 시험 구간이 짧아 참고용입니다.</p>"]
    else:
        out.append("<p class='note'>기간이 짧아 예측 시험은 하지 못했습니다.</p>")
    out.append("</section>")
    return "".join(out)


def access_html():
    t = PROC / "access_table.csv"
    sm = load_json(PROC / "access_summary.json")
    if not t.exists() or not sm:
        return ""
    df = pd.read_csv(t)
    basis = "인구 대비" if sm["per_population"] else "개수 그대로(인구 자료 없음)"
    body = table(list(df.columns), df.round(1).values.tolist())
    return ("<section><h2>소아·응급 필수의료 접근성 (구·군별)</h2>"
            f"<p>울산의 소아 전문 의원(기관명에 '소아' 포함) {sm['n_ped']}곳, 응급의료기관 {sm['n_er']}곳을 구·군별로 세어 {basis} 비교했습니다. "
            f"접근성 점수가 가장 낮은 구·군은 <b>{e(sm['lowest'])}</b>입니다(취약 <b>후보</b>).</p>"
            + img("access_score.png", "구군별 접근성 점수") + body +
            f"<p class='note'>소아 전문 의원 기준: {e(sm['pediatric_method'])}. 점수는 지표를 구·군끼리 0~1로 맞춰 평균 낸 규칙 기반 값이며 AI가 아닙니다. "
            "기관 수만 보며 병상, 의사 수, 이동 시간, 실제 진료량은 반영하지 않았으므로 '취약 확정'이 아니라 '추가 확인이 필요한 후보'입니다.</p></section>")


def gap_html():
    sm = load_json(PROC / "gap_summary.json")
    tg = PROC / "gap_by_gu.csv"
    if not sm or not tg.exists():
        return ""
    g = pd.read_csv(tg)
    cl = pd.read_csv(PROC / "gap_clusters.csv") if (PROC / "gap_clusters.csv").exists() and (PROC / "gap_clusters.csv").stat().st_size > 5 else pd.DataFrame()
    if len(cl):
        big, far = cl.iloc[0], cl.sort_values("소아의원까지_평균km").iloc[-1]
        top = (f"지점 수가 가장 많은 군집은 <b>{e(str(big['구군']))}</b> 쪽({big['군집']}, {int(big['지점수'])}개 지점, 소아 의원까지 평균 {big['소아의원까지_평균km']}km)이고, "
               f"소아 의원까지 가장 먼 군집은 <b>{e(str(far['구군']))}</b> 쪽({far['군집']}, {int(far['지점수'])}개 지점, 평균 {far['소아의원까지_평균km']}km)입니다. 군집의 크기와 공백의 심각도는 다릅니다.")
    else:
        top = "기준 거리를 넘는 지점이 많지 않아 뚜렷한 군집은 없었습니다."
    return ("<section><h2>거리 기반 공백 생활권 탐지 (군집)</h2>"
            f"<p>울산 병·의원 위치 {sm['n_points']:,}곳을 생활권이 모여 있는 곳의 <b>대리 지표</b>로 삼아, 각 지점에서 가장 가까운 소아 전문 의원({sm['n_ped']}곳)과 지정 응급의료기관({sm['n_er']}곳)까지 직선거리를 계산했습니다. "
            f"소아 전문 의원이 {sm['ped_far_km']:g}km보다 먼 지점 {sm['n_far']}곳을 밀도 기반 군집(DBSCAN, 반경 {sm['eps_km']:g}km)으로 묶어 <b>공백 생활권 후보</b> {sm['n_clusters']}개를 찾았습니다. {top}</p>"
            + img("gap_map.png", "공백 생활권 지도") + img("gap_distance.png", "구군별 거리")
            + table(list(g.columns), g.values.tolist())
            + ("<h3 style='font-size:15px;margin:18px 0 6px'>공백 생활권 후보 군집</h3>" + table(list(cl.columns), cl.head(8).values.tolist()) if len(cl) else "")
            + "<p class='note'>한계: 인구가 아니라 병·의원 위치를 수요의 대리 지표로 썼고, 도로·대중교통이 아닌 직선거리이며, 3km·8km 기준과 군집 반경은 임의로 정한 값입니다. "
            "소아 전문 의원은 기관명에 '소아'가 들어간 곳만 포함합니다. '공백 확정'이 아니라 현장 확인이 필요한 후보입니다. 군집화(DBSCAN)는 비지도 기계학습이지만 예측 모델은 아닙니다.</p></section>")


def issues_html():
    rows = [
        ["공공의료기관 비중", "울산 1.0%, 전국 평균 5.2%", "시민단체 기고문", "공식 통계로 확인 필요"],
        ["응급의학 전문의", "인구 10만 명당 울산 2.8명, 서울 11.7명(2024 기준이라는 주장)", "같은 기고문", "공식 통계로 확인 필요"],
        ["소아 중환자 병상", "울산 0개라는 주장", "같은 기고문", "공식 통계로 확인 필요"],
        ["산재전문공공병원", "300병상 규모, 올해 개원 예정이라는 보도(보도마다 시점이 다름)", "언론 보도", "개원 시점 확인 필요"],
        ["울산시 보건 예산", "2026년 762억 원, 필수·공공의료와 지역완결형 응급의료체계 구축 추진", "언론 보도", "시 공식 자료로 확인 필요"],
    ]
    return ("<section><h2>울산 보건 현안 (조사 기록)</h2>"
            "<p>아래는 검색으로 확인한 현안이며, 서로 다른 출처의 주장·보도를 정리한 것입니다. <b>제출 전에 공식 통계나 원문으로 확인한 뒤 출처와 함께 인용하세요.</b></p>"
            + table(["항목", "내용", "출처 유형", "확인 상태"], rows) + "</section>")


def priority_html():
    sm = load_json(PROC / "priority_summary.json")
    path = PROC / "priority_clusters.csv"
    if not sm or not path.exists():
        return ""
    df = pd.read_csv(path)
    preferred = df[df["일관된상위후보"] == True] if len(df) and "일관된상위후보" in df else pd.DataFrame()
    lead = ("기준 거리·군집 반경·가중치를 바꿔도 상위 후보로 남은 군집입니다. 현장 확인 순서 후보이지 취약지역 확정은 아닙니다."
            if len(preferred) else "현재 자료에서 일관된 상위 후보 기준을 통과한 군집이 없습니다. 이것은 취약지역이 없다는 뜻이 아닙니다.")
    rows = [[r.get("군집"), r.get("구군"), int(r.get("지점수", 0)), r.get("소아기관_평균직선거리km"),
        r.get("야간휴일소아기관_평균직선거리km", "자료 미등록"), r.get("민감도안정성%"),
        "일관 후보" if bool(r.get("일관된상위후보")) else "추가 확인", r.get("점검유형")] for _, r in df.iterrows()]
    return ("<section><h2>현장 확인 우선순위 후보</h2>"
        f"<p>{e(lead)} 수요 대리지점 {sm.get('demandProxyPointCount', 0):,}곳, 기준 조합 {sm.get('combinationCount', 0)}개를 비교했습니다.</p>"
        + table(["군집", "구·군", "지점 수", "소아기관 평균 km", "야간·휴일기관 평균 km", "안정성 %", "판정", "점검 유형"], rows)
        + "<p class='note'>점수 가중치는 탐색용으로 사전 정의한 임의 기준입니다. 시설 좌표는 생활권 수요의 대리값이며, 실제 환자 수·도로 이동시간·시설 개설 가능성을 반영하지 않았습니다.</p></section>")


def scenario_html():
    sm = load_json(PROC / "scenario_summary.json")
    path = PROC / "scenario_access.csv"
    if not sm:
        return ""
    if sm.get("status") != "ready" or not path.exists() or path.stat().st_size < 5:
        return ("<section><h2>야간·휴일 접근성 개선 시나리오</h2>"
                f"<p>{e(sm.get('reason', '시나리오 계산에 필요한 자료가 부족합니다.'))}</p>"
                "<p class='note'>실제 개설이나 이용 효과가 아니라 가정 시나리오입니다.</p></section>")
    df = pd.read_csv(path)
    rows = [[f"{r['기준거리km']:g} km", int(r["가정추가기관수"]), int(r["기준내지점수_기존"]),
        int(r["기준내지점수_시나리오"]), f"{r['기준내지점비율_기존%']:.1f}%",
        f"{r['기준내지점비율_시나리오%']:.1f}%", f"+{r['변화_퍼센트포인트']:.1f}%p"] for _, r in df.iterrows()]
    return ("<section><h2>야간·휴일 접근성 개선 시나리오</h2>"
        f"<p>기존 의료기관 좌표 중 후보지를 골라 야간·휴일 소아 진료기관이 추가된다고 가정했습니다. {e(sm.get('assumption', ''))}</p>"
        + table(["거리 기준", "가정 추가 수", "현재 기준 내 지점", "시나리오 기준 내 지점", "현재 비율", "시나리오 비율", "차이"], rows)
        + f"<p class='note'>{e(sm.get('claimBoundary', ''))}</p></section>")


def alert_backtest_html():
    sm = load_json(PROC / "alert_backtest_summary.json")
    if not sm:
        return ""
    metrics = sm.get("horizons", [])
    rows = [[f"{r['horizonHours']}시간", r.get("status"), r.get("days"), r.get("cases"), r.get("events"),
        r.get("alerts"), "—" if r.get("precision") is None else f"{r['precision']:.3f}",
        "—" if r.get("recall") is None else f"{r['recall']:.3f}"] for r in metrics]
    if sm.get("status") == "supported":
        verdict = "사전 정의한 기간·사건 수와 성능 문턱을 통과했습니다. 아래 검증 범위 안에서만 성능을 설명할 수 있습니다."
    elif sm.get("status") == "not_supported":
        verdict = "자료량은 최소 기준을 넘었지만 성능 문턱을 통과하지 못했습니다. 조기 경보 성능을 주장할 수 없습니다."
    else:
        verdict = f"관측 기간 {sm.get('periodDays', 0):.2f}일 또는 저병상 사건 수가 부족해 성능을 판정하지 못했습니다."
    return ("<section><h2>병상 저가용 진입 경보 후향 검증</h2>"
        f"<p>{e(verdict)} 예측 시점에 이미 확인된 기록만 사용해 1·3시간 뒤 가용 병상 1석 이하 진입을 평가했습니다.</p>"
        + (table(["시점", "판정", "기록 일수", "평가 건수", "실제 사건", "경보", "정밀도", "재현율"], rows) if rows else "")
        + f"<p class='note'>{e(sm.get('predictionRule', ''))} 사전 기준: 최소 3일·사건 10건, 정밀도 0.50·재현율 0.30. 프로젝트 검토 기준이며 임상 표준은 아닙니다. {e(sm.get('claimBoundary', ''))}</p></section>")


def limits_html():
    ev = load_json(PROC / "er_eval.json") or {}
    items = [
        "실시간 API는 15분 간격으로 수집하지만 기관 미응답·전송 지연이 있을 수 있습니다. 응답하지 않은 기관은 0병상으로 보지 않습니다.",
        "1·3시간 추정은 기관별 관측 쌍의 변화량을 단순 외삽한 참고치입니다. 3회·30분부터 잠정값을 표시하며, 관측이 짧을수록 참고성이 낮고 검증된 예측 모델이 아닙니다.",
        "응급상황이면 119에 신고하세요. 병상 표시는 실제 수용·배정 여부를 보장하지 않으므로 방문 전 기관에 전화해 확인해야 합니다.",
        "실시간 화면은 로컬 주소 127.0.0.1에서 실행됩니다. 여러 기관이 함께 쓰는 공개 서비스로 운영하려면 별도 배포·접근통제·모니터링·모델 검증이 필요합니다.",
        "접근성 점수는 기관 수만 반영한 규칙 기반 값이며 AI가 아닙니다. 병상, 의사 수, 이동 시간은 반영하지 않았습니다.",
        "소아 전문 의원은 기관명에 '소아'가 들어간 곳만 포함해 실제 소아 진료 가능 기관보다 적게 잡힐 수 있습니다.",
        "공백 생활권은 병·의원 위치를 수요의 대리 지표로 쓴 직선거리 분석이며, 인구·도로·대중교통은 반영하지 않았습니다.",
        "현안 수치는 시민단체 기고와 언론 보도에서 가져온 것으로 공식 통계 확인이 필요합니다.",
        "응급 병상 화면은 로컬 서버가 공공 API를 15분마다 수집해 갱신합니다. 서버는 127.0.0.1 전용이며 여러 사용자가 함께 쓰는 공개 서비스가 아닙니다. 짧은 관측 기반 추세는 검증되지 않았습니다.",
    ]
    if str(ev.get("source", "")).startswith("er_snapshots"):
        items.insert(0, "병상 자료는 직접 수집한 짧은 기간의 실시간 스냅샷이라 표본이 적고 일반화하기 어렵습니다.")
    if DEMO:
        items.insert(0, "<b>이 화면은 시험용(DEMO) 가짜 자료로 만든 것입니다. 제출하면 안 됩니다.</b>")
    return "<section><h2>한계와 검증</h2><ul class='limits'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul></section>"


def sources_html():
    ev = load_json(PROC / "er_eval.json") or {}
    historical = RAW / "TB_NC_ICU_SCKBD_INFO.csv"
    historical_label = ("TB_NC_ICU_SCKBD_INFO.csv (울산 21행·3개 시점)" if historical.exists()
                        else str(ev.get("source", "(아직 없음)")))
    rows = [["응급의료기관 가용 병상·포화도(과거 시계열)", "한국과학기술연구원(KIST) / 공공데이터포털", "출처 표시 필요; 총병상·가용병상으로 포화도 계산", historical_label],
            ["전국 병·의원 찾기 서비스", "국립중앙의료원 / 공공데이터포털", "이용허락범위 제한 없음", "facilities_pediatric.csv" if (RAW / "facilities_pediatric.csv").exists() else "(아직 없음)"],
            ["전국 응급의료기관 정보 조회 서비스", "국립중앙의료원 / 공공데이터포털", "포털 이용 정책(출처 표시)", "facilities_er.csv" if (RAW / "facilities_er.csv").exists() else "(아직 없음)"],
            ["울산 구·군별 인구", "행정안전부 주민등록 인구통계 또는 KOSIS", "직접 확인해 입력", "population_manual.csv"]]
    return ("<section><h2>데이터와 출처</h2>" + table(["자료", "제공기관", "이용 조건(확인 필요)", "사용한 파일"], rows) +
            "<p class='note'>병상 CSV의 울산 자료는 2023-12-12~13의 3개 관측 시점(21행)뿐입니다. 포화도는 총병상 수가 0보다 큰 항목에 대해 (총병상−가용병상)÷총병상으로 계산하며, 장기 추세나 예측을 입증하지 않습니다. 내려받은 날짜와 정확한 자료 이름은 PDF 출처 목록에 적으세요.</p></section>")
