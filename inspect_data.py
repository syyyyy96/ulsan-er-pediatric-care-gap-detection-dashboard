"""
데이터 구조 확인 도구

data/raw/ 폴더 안의 csv / xlsx / json 파일을 모두 열어서
'어떤 열이 있는지, 몇 행인지, 울산 행이 있는지'를 보여줍니다.
(결과는 화면에 나오고 data/inspect_report.txt 에도 저장됩니다. 서비스키 같은 비밀 정보는 읽지 않습니다.)

사용법:  python inspect_data.py
"""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
KEY = "울산"


def read_table(p):
    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        xl = pd.ExcelFile(p)
        if len(xl.sheet_names) > 1:
            print(f"  시트: {xl.sheet_names} (첫 번째 시트만 확인)")
        return xl.parse(xl.sheet_names[0])
    if ext == ".csv":
        for enc in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                return pd.read_csv(p, encoding=enc, low_memory=False)
            except UnicodeDecodeError:
                continue
        raise ValueError("글자 인코딩을 읽지 못했습니다")
    if ext == ".json":
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(obj, list):
            return pd.json_normalize(obj)
        print("  JSON 최상위 항목:", list(obj)[:15])

        def find(o, path="", depth=0):
            if isinstance(o, list) and o and isinstance(o[0], dict):
                return path, o
            if isinstance(o, dict) and depth < 6:
                for k, v in o.items():
                    r = find(v, f"{path}/{k}", depth + 1)
                    if r:
                        return r
            return None

        r = find(obj)
        if r:
            print(f"  '{r[0]}' 목록을 표로 읽습니다")
            return pd.json_normalize(r[1])
        return None
    return None


def show(p):
    print("=" * 70)
    print(f"파일: {p.name}  ({p.stat().st_size / 1024:,.0f} KB)")
    try:
        df = read_table(p)
    except Exception as e:
        print("  [읽기 실패]", e)
        return
    if df is None:
        print("  (표로 읽을 수 없는 형식)")
        return
    print(f"  크기: {len(df):,}행 x {df.shape[1]}열")
    print("  열 이름과 예시:")
    for c in df.columns:
        s = df[c].dropna()
        ex = str(s.iloc[0])[:30] if len(s) else "(비어 있음)"
        print(f"    - {c} [{df[c].dtype}] 예: {ex}")
    print("  처음 3행:")
    print("    " + df.head(3).to_string(max_colwidth=18).replace("\n", "\n    "))
    mask = df.astype(str).apply(lambda s: s.str.contains(KEY, na=False)).any(axis=1)
    print(f"  '{KEY}'가 들어간 행: {int(mask.sum()):,}행")
    if mask.any():
        print("    " + df[mask].head(3).to_string(max_colwidth=18).replace("\n", "\n    "))
    for c in df.columns:
        if any(w in str(c) for w in ("일자", "날짜", "일시", "시간", "date", "Date", "time")):
            s = df[c].dropna().astype(str)
            if len(s):
                print(f"  [{c}] 범위: {s.min()} ~ {s.max()}")
                break


if __name__ == "__main__":
    files = sorted(p for p in RAW.glob("*") if p.suffix.lower() in (".csv", ".xlsx", ".xls", ".json"))
    buf = io.StringIO()
    if not files:
        print(f"[안내] {RAW} 안에 csv/xlsx/json 파일이 없습니다. 공공데이터포털에서 받은 파일을 넣고 다시 실행하세요.")
    else:
        with redirect_stdout(buf):
            for f in files:
                show(f)
        text = buf.getvalue()
        print(text)
        (ROOT / "data" / "inspect_report.txt").write_text(text, encoding="utf-8")
        print("저장: data/inspect_report.txt")
