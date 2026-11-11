"""공통 설정: 폴더 경로, 인증키 읽기, 한글 폰트, 파일 읽기 (모든 step 파일이 불러옵니다)"""
import json
import os
from pathlib import Path
from urllib.parse import unquote

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEMO = os.environ.get("ULSAN_DEMO") == "1"          # 시험용(가짜) 데이터 모드
RAW = ROOT / "data" / ("demo" if DEMO else "raw")           # 내려받은 원본 자료
PROC = ROOT / "data" / ("processed_demo" if DEMO else "processed")   # 계산 결과
OUT = ROOT / ("outputs_demo" if DEMO else "outputs")        # 대시보드, 보고서, 그래프
CHARTS = OUT / "charts"
for _d in (RAW, PROC, OUT, CHARTS):
    _d.mkdir(parents=True, exist_ok=True)

REGION = "울산"

# 공휴일(2023-12 ~ 2024-12). 이 범위 밖 날짜는 평일/주말만 구분합니다.
HOLIDAYS = {
    "2023-12-25", "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12", "2024-03-01",
    "2024-04-10", "2024-05-05", "2024-05-06", "2024-05-15", "2024-06-06", "2024-08-15", "2024-09-16",
    "2024-09-17", "2024-09-18", "2024-10-01", "2024-10-03", "2024-10-09", "2024-12-25",
}


ENV_KEY_NAMES = ("DATA_GO_KR_SERVICE_KEY", "DATA_GO_KR_KEY")   # 앞의 이름이 표준(server.py와 동일), 뒤는 예전 이름


def env_key():
    """.env 의 DATA_GO_KR_SERVICE_KEY(또는 예전 이름 DATA_GO_KR_KEY)를 읽습니다(없으면 None). 화면에는 출력하지 않습니다."""
    f = ROOT / ".env"
    if f.exists():
        found = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                found[k.strip()] = v.strip().strip('"').strip("'")
        for name in ENV_KEY_NAMES:
            if found.get(name):
                return unquote(found[name])
    return None


def save_json(obj, path):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def read_table(path):
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p)
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(p, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{p.name}: 글자 인코딩을 읽지 못했습니다")


def setup_font():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in ["AppleGothic", "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]:
        if name in installed:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트를 찾지 못했습니다. 그래프의 한글이 네모로 보일 수 있습니다.")
    plt.rcParams["axes.unicode_minus"] = False
    return plt
