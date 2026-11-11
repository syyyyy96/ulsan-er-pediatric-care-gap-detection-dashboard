"""STEP 4. 대시보드(index.html) 만들기: 결과가 있는 메뉴만 나타납니다. 한 파일에 그림이 모두 들어 있어 어디서든 열립니다."""
from common import DEMO, OUT, PROC, ROOT, load_json
import content as C

CSS = (ROOT / "assets" / "dashboard.css").read_text(encoding="utf-8")
PANELS = [("issue", "울산 보건 현안", C.issues_html()), ("er", "병상 혼잡 예측", C.er_html()), ("access", "필수의료 접근성", C.access_html()), ("gap", "공백 생활권(군집)", C.gap_html()),
          ("priority", "현장 확인 우선순위", C.priority_html()), ("scenario", "개선 시나리오", C.scenario_html()),
          ("alert", "경보 후향 검증", C.alert_backtest_html()),
          ("limits", "한계와 검증", C.limits_html()), ("src", "데이터와 출처", C.sources_html())]
menu = "".join(f'<li><button type="button" data-p="{k}">{n}</button></li>' for k, n, _ in PANELS)
panels = "".join(f'<div class="panel" id="p-{k}">{h}</div>' for k, _, h in PANELS)
er_ok = load_json(PROC / "er_eval.json") is not None
purpose = "울산 구·군별 소아·응급 의료 접근성 후보를 찾는 분석 결과를 보여줍니다." + (" 병상 혼잡 패턴과 예측 가능성을 시험한 결과도 포함합니다." if er_ok else " (병상 혼잡 예측은 과거 자료를 확보하지 못해 포함하지 않았습니다.)")
banner = '<p class="note" style="color:#B33A0B"><b>시험용(DEMO) 가짜 자료 화면입니다. 제출 금지.</b></p>' if DEMO else ""
page = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>울산 응급·소아 필수의료 접근성 대시보드</title><style>{CSS}</style></head><body>
<aside class="side"><div class="brand"><h1>울산 응급·소아<br>필수의료 접근성</h1><p>공공데이터 기반 분석 프로토타입<br>자료의 한계는 '한계와 검증' 메뉴에 있습니다</p></div><ul class="menu">{menu}</ul></aside>
<main>{banner}<p class="purpose">{purpose}</p>{panels}</main>
<script>(function(){{var b=[].slice.call(document.querySelectorAll('.menu button'));
function show(k){{b.forEach(function(x){{x.classList.toggle('on',x.dataset.p===k)}});document.querySelectorAll('.panel').forEach(function(p){{p.classList.toggle('on',p.id==='p-'+k)}});window.scrollTo(0,0);try{{history.replaceState(null,'','#'+k)}}catch(e){{}}}}
b.forEach(function(x){{var p=document.getElementById('p-'+x.dataset.p);if(!p||!p.innerHTML.trim()){{x.parentNode.style.display='none';return}}x.addEventListener('click',function(){{show(x.dataset.p)}})}});
var v=b.filter(function(x){{return x.parentNode.style.display!=='none'}});var h=location.hash.slice(1);
show(v.some(function(x){{return x.dataset.p===h}})?h:v[0].dataset.p)}})();</script></body></html>"""
filename = "index.html" if DEMO else "index_analysis.html"
(OUT / filename).write_text(page, encoding="utf-8")
print(f"분석 대시보드 저장: {OUT / filename} ({len(page) / 1024:,.0f} KB)")
print("STEP 4 완료")
