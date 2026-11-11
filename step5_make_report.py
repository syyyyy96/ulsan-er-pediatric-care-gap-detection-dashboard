"""STEP 5. 보고서 초안(report_draft.html) 만들기: 브라우저로 열고 인쇄(Cmd+P) → 'PDF로 저장'하면 PDF 초안이 됩니다. 문장은 직접 고쳐 쓰세요."""
from common import DEMO, OUT, PROC, load_json
import content as C

CSS = """@page{size:A4;margin:18mm}body{font:11pt/1.75 "Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:#16202B;max-width:820px;margin:0 auto;padding:16px}
h1{font-size:22pt;color:#0B2545}h2{font-size:15pt;color:#0B2545;border-bottom:1px solid #DDE2E8;padding-bottom:4px;margin-top:28px}h3{font-size:12pt}
table{border-collapse:collapse;width:100%;font-size:9.5pt;margin:8px 0}th,td{border:1px solid #DDE2E8;padding:5px 7px;text-align:left}th{background:#F3F5F7}
figure{margin:8px 0;text-align:center}img{max-width:100%}.note{font-size:9.5pt;color:#5E6B78}.todo{background:#FFF6ED;border:1px dashed #E0A060;padding:8px 12px;font-size:10pt}
.noprint{background:#EAF2FF;padding:8px 12px;font-size:10pt}@media print{.noprint{display:none}h2{page-break-after:avoid}figure,table{page-break-inside:avoid}}"""
demo = '<p class="todo"><b>시험용(DEMO) 가짜 자료로 만든 초안입니다. 제출 금지.</b></p>' if DEMO else ""
todo = lambda t: f'<p class="todo">[직접 작성] {t}</p>'
er_ok = load_json(PROC / "er_eval.json") is not None
title = "울산 응급·소아 필수의료 접근성" + ("과 병상 혼잡" if er_ok else "")
intro = ("울산의 응급·소아 필수의료 접근성이 구·군별로 어떻게 다른지 공공데이터로 비교하고, 병·의원 위치 기반 거리 분석과 군집화로 소아 의료 공백 생활권 후보를 찾았다."
         + (" 또한 응급의료기관 병상 혼잡이 요일·시간대에 따라 어떤 패턴을 보이는지 분석해 다음 시간대 예측 가능성을 시험했다." if er_ok else " 실시간 응급의료 API 수집과 초기 병상 추세 참고 기능은 별도 로컬 서비스로 구현했지만, 관측 기간이 짧아 예측 성능은 검증하지 못했다."))
rows = ([["병상 혼잡 예측(그래디언트 부스팅)", "요일·시간대·직전 값 등으로 다음 관측값 예측", "공공데이터 응급의료기관 가용 병상 시계열", "시험 결과는 5장에 있는 그대로 보고"]] if er_ok else [["실시간 병상 조회·초기 추세", "응급 API를 수집하고 최근 변화량 중앙값으로 1·3시간 참고값 계산", "국립중앙의료원 API·SQLite 관측 이력", "로컬 프로토타입; 짧은 기록으로 정확도 검증 전"]]) + [
        ["공백 생활권 군집(DBSCAN, 비지도 학습)", "병·의원 위치와 거리로 소아 의료 공백 후보 지점을 묶어 탐지", "병·의원/응급의료기관 목록(위치 포함)", "탐색적 분석이며 예측 모델이 아님"],
        ["접근성 지표(규칙 기반)", "구·군별 소아·응급 의료기관 수를 점수화", "병·의원/응급의료기관 목록, 인구", "AI가 아닌 기술 통계"]]
use = [["15분 간격", "응급실 가용 병상 현황 확인", "국립중앙의료원 실시간 API와 SQLite 관측 이력", "구현(로컬 프로토타입)"], ["관측 누적 시", "1·3시간 가용 병상 변화 참고", "최소 3회·30분부터 잠정 추세 외삽", "참고용; 검증 필요"], ["수시", "취약 후보 구·군 점검", "기관 목록·인구 자료 갱신", "정기 검증 필요"]]
html_ = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>보고서 초안</title><style>{CSS}</style></head><body>
<p class="noprint">초안입니다. 브라우저에서 인쇄(Cmd+P) → 'PDF로 저장'하면 PDF가 됩니다. [직접 작성] 칸을 채우고, 모든 문장과 숫자를 본인이 확인해 고쳐 쓰세요.</p>{demo}
<h1>[프로젝트 제목] {title}</h1><p>[이름] · NEXT:AI DEVELOPER 부트캠프 우수자 포상 프로젝트</p>
<h2>1. 개요</h2><p>{intro}</p>{todo('한 줄 요약, 기간, 참여자, 핵심 숫자 3개')}
<h2>2. 동기</h2>{C.issues_html()}{todo('지역 문제를 본인의 말로 정리. 공식 통계 확인 후 출처 표시')}
<h2>3. 내용</h2><p>AI 구성과 자료는 아래와 같다.</p>{C.table(['구성','하는 일','자료','비고'], rows)}{C.sources_html()}{todo('사용한 기술과 처리 순서 그림')}
<h2>4. 일정</h2>{todo('실제 작업 기록 그대로 (기간별 한 일)')}
<h2>5. 결과</h2>{C.er_html()}{C.access_html()}{C.gap_html()}{C.priority_html()}{C.scenario_html()}{C.alert_backtest_html()}{todo('그래프마다 3문장: 무엇을 보여주는지 / 핵심 숫자 / 그래서 무슨 뜻인지')}
<h2>6. 기대효과와 이용 방식</h2><p>사용자는 지역 보건의료 정책 담당자와 시민이다. 현재 버전은 127.0.0.1에서만 실행되는 로컬 프로토타입이며, 다중 이용자 공개 서비스로 배포되지는 않았다. 응급 상황에는 119에 신고하고, 병상 값은 방문 전 기관에 전화해 확인해야 한다.</p>{C.table(['주기','사용 장면','필요한 것','현재 상태'], use)}{C.scenario_html()}{todo('실제 이용자 수·현장 의사결정·건강 결과가 측정되지 않았으므로 시나리오를 실현 성과로 표현하지 않기')}
<h2>7. 요약, 한계, 느낀점</h2>{C.limits_html()}{todo('다음 단계(더 긴 기간 자료, 병상·의사 수·이동 시간 반영, 실시간 연동)와 느낀 점')}
</body></html>"""
(OUT / "report_draft.html").write_text(html_, encoding="utf-8")
print(f"보고서 초안 저장: {OUT / 'report_draft.html'}")
print("STEP 5 완료")
