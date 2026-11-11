"""시작 전 점검: 설치, 인증키, 자료 파일이 준비됐는지 한 번에 확인합니다. 사용법: python check_setup.py"""
import sys

from common import RAW, ROOT, env_key, read_table

print(f"파이썬 {sys.version.split()[0]}")
ok = True
for m in ("pandas", "numpy", "sklearn", "matplotlib", "openpyxl"):
    try:
        __import__(m)
        print(f"  [OK] {m}")
    except ImportError:
        ok = False
        print(f"  [필요] {m} 설치 안 됨 → pip install -r requirements.txt")
print("인증키(.env):", "[OK] 있음" if env_key() else "[필요] 없음 (API 신청 후 .env 에 DATA_GO_KR_SERVICE_KEY=키 한 줄)")
files = [p for p in sorted(RAW.glob("*")) if p.suffix.lower() in (".csv", ".xlsx", ".xls")]
print(f"자료 폴더 {RAW.relative_to(ROOT)}: 파일 {len(files)}개")
for p in files:
    print("  -", p.name)
er = any(any(k in p.name for k in ("응급", "가용", "포화", "er_", "bed")) for p in files)
print("응급실 가용 병상 자료:", "[확인 필요] 파일이 있으면 inspect_data.py 로 구조 확인" if files else "[필요] 아직 없음 (내려받아 data/raw 에 넣기)")
pop = RAW / "population_manual.csv"
if pop.exists():
    df = read_table(pop)
    filled = df.iloc[:, 1:].notna().all(axis=1).sum()
    print(f"인구 입력(population_manual.csv): {filled}/{len(df)}개 구·군 입력됨", "[OK]" if filled == len(df) else "[필요] 빈칸 채우기")
print("\n모두 [OK]가 아니어도 됩니다. [필요]로 표시된 것만 START_HERE.md 순서대로 채우세요.")
sys.exit(0 if ok else 1)
