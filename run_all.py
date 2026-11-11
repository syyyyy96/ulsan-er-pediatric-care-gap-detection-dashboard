"""
전체 실행. 사용법:  python run_all.py            (실제 자료)
                    python run_all.py --demo     (시험용 가짜 자료로 전체 흐름만 확인 — 제출 금지)
없는 자료 때문에 건너뛰는 단계는 '건너뜀'으로 표시되고, 나머지는 계속 실행됩니다.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
demo = "--demo" in sys.argv
offline = "--offline" in sys.argv
env = {**os.environ, "ULSAN_DEMO": "1"} if demo else os.environ
steps = [("step1_fetch_facilities.py", "병·의원/응급의료기관 목록 내려받기(API)", True),
         ("step2_er_forecast.py", "응급실 혼잡 패턴과 예측 시험", True),
         ("step3_access.py", "구·군별 접근성 분석", True),
         ("step3b_gap_cluster.py", "거리 기반 공백 생활권 탐지(군집)", True),
         ("step3c_priority.py", "현장 확인 우선순위·민감도 분석", True),
         ("step3d_scenario.py", "야간·휴일 소아 접근성 개선 시나리오", True),
         ("step6_alert_backtest.py", "병상 저가용 진입 경보 후향 검증", True),
         ("step4_build_dashboard.py", "대시보드 만들기", False),
         ("step5_make_report.py", "보고서 초안 만들기", False)]
if offline:
    steps = [s for s in steps if s[0] != "step1_fetch_facilities.py"]
if demo:
    subprocess.run([sys.executable, "dev_make_demo_data.py"], cwd=ROOT, check=True)
    steps = steps[1:]
t0 = time.time()
for i, (f, desc, optional) in enumerate(steps, 1):
    print(f"\n{'=' * 60}\n[{i}/{len(steps)}] {desc} ({f})\n{'=' * 60}")
    r = subprocess.run([sys.executable, "-W", "ignore", f], cwd=ROOT, env=env)
    if r.returncode != 0:
        if optional:
            print(f"→ 이 단계는 건너뜁니다(코드 {r.returncode}). 위 안내를 확인하세요. 나머지는 계속합니다.")
            continue
        print(f"\n✗ {f} 에서 멈췄습니다. 위의 오류 메시지를 확인하세요.")
        sys.exit(r.returncode)
out = "outputs_demo" if demo else "outputs"
dashboard_file = "index.html" if demo else "index_analysis.html"
print(f"\n✓ 완료 ({time.time() - t0:.0f}초). 분석 결과: {out}/{dashboard_file}, {out}/report_draft.html")
if not demo:
    print("실시간 서비스 화면은 outputs/index.html — run_dashboard.command로 실행하세요.")
