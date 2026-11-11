
"""
STEP 2. 울산 응급실 혼잡 패턴 분석 + 다음 관측값 예측 시험

[분석 원칙]
1. 응급실 자료만 응급실 분석에 사용합니다.
2. 중환자실 자료는 응급실 혼잡 예측에 사용하지 않습니다.
3. 날짜/시간/예측 대상 열을 임의로 추측하지 않습니다.
4. 최소 90일의 관측 기간이 확보되어야 AI 평가를 진행합니다.
5. 시험 데이터가 100개 미만이면 AI 학습 및 성능평가를 중단합니다.
6. 검증할 수 없는 데이터로 성능 그래프를 생성하지 않습니다.

사용법:
python step2_er_forecast.py data/raw/응급실자료.csv

주의:
TARGET_COL은 데이터 정의서를 확인한 후 직접 지정해야 합니다.
"""

import re
import sys

import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor

from common import (
    CHARTS,
    HOLIDAYS,
    PROC,
    RAW,
    REGION,
    read_table,
    save_json,
    setup_font,
)


# ============================================================
# 1. 사용자 설정
# ============================================================

# 정의서에서 의미를 확인한 예측 대상 열을 직접 지정합니다.
# 확인 전에는 None으로 유지합니다.
TARGET_COL = None

# 동일 시각에 여러 종류의 행이 있다면 지정합니다.
# 예: {"병상구분": "일반"}
SERIES_FILTER = {}

# 시험 구간 길이
TEST_DAYS = 30

# 최소 관측 기간
MIN_HISTORY_DAYS = 90

# 최소 시험 관측 수
MIN_TEST_OBS = 100

# 자동 선택에서 제외할 파일명
SKIP_NAMES = (
    "facilities",
    "population",
    "api_probe",
    "정의서",
)

# 병상 관련 파일 검색어
BED_HINTS = (
    "가용",
    "포화",
    "hvec",
    "병상",
    "bed",
    "sckbd",
    "satur",
    "icu",
    "avail",
)

MODEL = "AI 모델(그래디언트 부스팅)"

BASES = [
    "직전 관측값",
    "어제 같은 시간대",
    "최근 4주 같은 요일·시간대 평균",
]

NAVY = "#0B2545"
GRAY = "#8A97A5"
RED = "#B33A0B"

WD = ["월", "화", "수", "목", "금", "토", "일"]


# ============================================================
# 2. 자료 종류 판별
# ============================================================

def detect_subject(filename, columns):

    text = (
        str(filename)
        + " "
        + " ".join(map(str, columns))
    ).lower()

    # 중환자실 자료 판별
    icu_words = (
        "icu",
        "중환자",
        "sckbd",
    )

    if any(word in text for word in icu_words):
        return "중환자실"

    # 응급실 자료 판별
    er_words = (
        "응급실",
        "emergency",
        "emergencyroom",
        "er_bed",
        "erbed",
        "hvec",
    )

    if any(word in text for word in er_words):
        return "응급실"

    return "미확인"


# ============================================================
# 3. 자료 불러오기
# ============================================================

def load_source():

    # 사용자가 파일 경로를 직접 지정한 경우
    if len(sys.argv) > 1:

        path = sys.argv[1]

        df = read_table(path)

        return path, df

    candidates = []
    seen = []

    for path in sorted(RAW.glob("*")):

        if path.suffix.lower() not in (
            ".csv",
            ".xlsx",
            ".xls",
        ):
            continue

        if any(
            word in path.name.lower()
            for word in SKIP_NAMES
        ):
            continue

        try:

            df = read_table(path)

        except Exception as error:

            print(
                f"[읽기 실패] {path.name}: {error}"
            )

            continue

        columns = list(map(str, df.columns))

        text = (
            path.name
            + " "
            + " ".join(columns)
        ).lower()

        subject = detect_subject(
            path.name,
            columns,
        )

        seen.append(
            {
                "name": path.name,
                "rows": len(df),
                "subject": subject,
                "columns": columns[:12],
            }
        )

        if not any(
            word in text
            for word in BED_HINTS
        ):
            continue

        # 응급실 자료로 확인된 경우만 선택
        if subject != "응급실":
            continue

        candidates.append(
            (path, df)
        )

    if not candidates:

        print(
            "\n[자료 선택 중단]"
        )

        print(
            "응급실 자료로 확인된 병상 자료를 찾지 못했습니다."
        )

        print(
            "\n확인한 파일:"
        )

        for item in seen:

            print(
                f"- {item['name']}"
                f" | {item['rows']:,}행"
                f" | 자료 종류: {item['subject']}"
                f" | 열: {item['columns']}"
            )

        print(
            "\n중환자실 자료는 응급실 혼잡 예측에 "
            "자동으로 사용하지 않습니다."
        )

        print(
            "응급실 자료를 확보한 후 파일 경로를 직접 지정해 주세요."
        )

        sys.exit(2)

    best = max(
        candidates,
        key=lambda item: len(item[1]),
    )

    return str(best[0]), best[1]


# ============================================================
# 4. 날짜 변환
# ============================================================

def parse_dt(column):

    values = column.astype(str).str.strip()

    digits = values.str.replace(
        r"\D",
        "",
        regex=True,
    )

    lengths = digits.str.len()

    # YYYYMMDD / YYYYMMDDHH / YYYYMMDDHHMM / YYYYMMDDHHMMSS
    if (
        lengths.isin([8, 10, 12, 14]).mean() > 0.9
        and not values.str.contains(
            r"[-/:. ]",
            regex=True,
        ).any()
    ):

        result = pd.Series(
            pd.NaT,
            index=values.index,
            dtype="datetime64[ns]",
        )

        formats = (
            (8, "%Y%m%d"),
            (10, "%Y%m%d%H"),
            (12, "%Y%m%d%H%M"),
            (14, "%Y%m%d%H%M%S"),
        )

        for length, date_format in formats:

            mask = lengths == length

            if mask.any():

                result.loc[mask] = pd.to_datetime(
                    digits.loc[mask],
                    format=date_format,
                    errors="coerce",
                )

        return result

    try:

        return pd.to_datetime(
            values,
            errors="coerce",
            format="mixed",
        )

    except (TypeError, ValueError):

        return pd.to_datetime(
            values,
            errors="coerce",
        )


# ============================================================
# 5. 시간 변환
# ============================================================

def parse_time_delta(column):

    """
    지원하는 시간 형식:
    22:00
    22:00:00
    22
    2200
    """

    values = column.astype(str).str.strip()

    result = pd.Series(
        pd.NaT,
        index=values.index,
        dtype="timedelta64[ns]",
    )

    # HH:MM 또는 HH:MM:SS
    colon_mask = values.str.fullmatch(
        r"\d{1,2}:\d{2}(:\d{2})?"
    )

    if colon_mask.any():

        result.loc[colon_mask] = pd.to_timedelta(
            values.loc[colon_mask],
            errors="coerce",
        )

    # HH
    hour_mask = values.str.fullmatch(
        r"\d{1,2}"
    )

    if hour_mask.any():

        hours = pd.to_numeric(
            values.loc[hour_mask],
            errors="coerce",
        )

        valid = hours.between(0, 23)

        valid_index = valid[valid].index

        result.loc[valid_index] = pd.to_timedelta(
            hours.loc[valid_index],
            unit="h",
        )

    # HHMM
    hhmm_mask = values.str.fullmatch(
        r"\d{4}"
    )

    if hhmm_mask.any():

        hhmm = values.loc[hhmm_mask]

        hours = pd.to_numeric(
            hhmm.str[:2],
            errors="coerce",
        )

        minutes = pd.to_numeric(
            hhmm.str[2:],
            errors="coerce",
        )

        valid = (
            hours.between(0, 23)
            & minutes.between(0, 59)
        )

        valid_index = valid[valid].index

        result.loc[valid_index] = (
            pd.to_timedelta(
                hours.loc[valid_index],
                unit="h",
            )
            + pd.to_timedelta(
                minutes.loc[valid_index],
                unit="m",
            )
        )

    return result


# ============================================================
# 6. 시계열 데이터 구성
# ============================================================

def prepare_series(df, source_name):

    df = df.copy()

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    # 자료 종류 확인
    subject = detect_subject(
        source_name,
        df.columns,
    )

    if subject != "응급실":

        print(
            f"\n[분석 중단] 이 자료는 '{subject}' 자료입니다."
        )

        print(
            "STEP 2는 응급실 혼잡 분석 단계입니다."
        )

        print(
            "중환자실 자료를 응급실 자료처럼 분석하지 않습니다."
        )

        sys.exit(2)

    # 울산 지역 열 탐색
    nonnum = [
        column
        for column in df.columns
        if not pd.api.types.is_numeric_dtype(
            df[column]
        )
    ]

    region_col = None
    best_count = 0

    for column in nonnum:

        count = int(
            df[column]
            .astype(str)
            .str.contains(
                REGION,
                na=False,
            )
            .sum()
        )

        if count > best_count:

            region_col = column
            best_count = count

    # 실시간 수집 자료 예외 처리
    if (
        region_col is None
        and "collected_at" in df.columns
    ):

        sub = df.copy()

        region_col = "(실시간 수집 자료)"

    elif region_col is None:

        print(
            f"[오류] '{REGION}'이 포함된 지역 열을 찾지 못했습니다."
        )

        print(
            "현재 열:",
            list(df.columns),
        )

        sys.exit(1)

    else:

        sub = df[
            df[region_col]
            .astype(str)
            .str.contains(
                REGION,
                na=False,
            )
        ].copy()

    if sub.empty:

        print(
            f"[오류] '{REGION}' 데이터가 없습니다."
        )

        sys.exit(1)

    # 사용자 필터 적용
    for column, value in SERIES_FILTER.items():

        if column not in sub.columns:

            print(
                f"[오류] SERIES_FILTER 열 '{column}'이 없습니다."
            )

            sys.exit(1)

        sub = sub[
            sub[column].astype(str)
            == str(value)
        ]

    if sub.empty:

        print(
            "[오류] 필터 적용 후 데이터가 없습니다."
        )

        sys.exit(1)

    low = {
        column: column.lower()
        for column in sub.columns
    }

    # 날짜 열 탐색
    date_cols = [
        column
        for column in sub.columns
        if low[column] in (
            "stndt",
            "기준일자",
            "기준일",
        )
        or any(
            word in low[column]
            for word in (
                "일시",
                "일자",
                "날짜",
                "date",
                "collected",
                "_dt",
                "ymd",
                "dttm",
            )
        )
    ]

    # 시간 열 탐색
    time_cols = [
        column
        for column in sub.columns
        if column not in date_cols
        and (
            low[column] in (
                "tm_info",
                "시간정보",
            )
            or any(
                word in low[column]
                for word in (
                    "시간",
                    "시각",
                    "hour",
                    "time",
                    "시점",
                    "_hh",
                    "_hr",
                    "_tm",
                )
            )
        )
    ]

    if not date_cols:

        print(
            "[오류] 날짜 열을 찾지 못했습니다."
        )

        print(
            "현재 열:",
            list(sub.columns),
        )

        sys.exit(1)

    date_col = date_cols[0]

    date_values = parse_dt(
        sub[date_col]
    )

    # 날짜 자체에 시간이 포함되었는지 확인
    has_time = bool(
        (
            (date_values.dt.hour != 0)
            | (date_values.dt.minute != 0)
            | (date_values.dt.second != 0)
        ).any()
    )

    if has_time:

        timestamps = date_values

        used_time_col = None

    elif time_cols:

        time_col = time_cols[0]

        time_delta = parse_time_delta(
            sub[time_col]
        )

        timestamps = (
            date_values.dt.normalize()
            + time_delta
        )

        used_time_col = time_col

    else:

        timestamps = date_values

        used_time_col = None

    invalid_datetime_rows = int(
        timestamps.isna().sum()
    )

    if invalid_datetime_rows:

        print(
            f"[확인] 날짜·시간 변환 실패: "
            f"{invalid_datetime_rows}행"
        )

    # 숫자형 열에서 날짜·시간 열 제외
    excluded_cols = (
        date_cols
        + time_cols
    )

    numeric_cols = [
        column
        for column in sub.columns
        if pd.api.types.is_numeric_dtype(
            sub[column]
        )
        and column not in excluded_cols
    ]

    if not numeric_cols:

        print(
            "[오류] 숫자형 분석 열이 없습니다."
        )

        sys.exit(1)

    # 예측 대상 자동 선택 금지
    target = TARGET_COL

    if target is None:

        print(
            "\n[예측 대상 지정 필요]"
        )

        print(
            "예측 대상 열을 자동으로 선택하지 않습니다."
        )

        print(
            "\n선택 가능한 숫자형 열:"
        )

        for column in numeric_cols:

            print(
                f"- {column}"
            )

        print(
            "\n정의서에서 의미를 확인한 후 "
            "TARGET_COL에 열 이름을 지정해 주세요."
        )

        sys.exit(2)

    if target not in sub.columns:

        print(
            f"[오류] TARGET_COL '{target}'이 없습니다."
        )

        print(
            "사용 가능한 숫자형 열:",
            numeric_cols,
        )

        sys.exit(1)

    if target not in numeric_cols:

        print(
            f"[오류] TARGET_COL '{target}'은 "
            "숫자형 분석 열이 아닙니다."
        )

        sys.exit(1)

    # 예측 대상 값 숫자 변환
    values = pd.to_numeric(
        sub[target],
        errors="coerce",
    )

    series_df = pd.DataFrame(
        {
            "_ts": timestamps,
            "_y": values,
        }
    )

    series_df = series_df.dropna(
        subset=["_ts", "_y"]
    )

    if series_df.empty:

        print(
            "[오류] 유효한 날짜·시간 및 예측 대상 값이 없습니다."
        )

        sys.exit(1)

    # 비율형은 평균, 일반 수치형은 합계
    target_name = str(target).lower()

    rate_like = any(
        word in target_name
        for word in (
            "포화",
            "율",
            "비율",
            "%",
            "rate",
            "satur",
            "_rt",
            "ratio",
        )
    )

    worse_is_low = (
        any(
            word in target_name
            for word in (
                "가용",
                "avail",
                "avl",
                "hvec",
            )
        )
        and not rate_like
    )

    grouped = series_df.groupby(
        "_ts"
    )["_y"]

    if rate_like:

        series = grouped.mean()

        aggregation = "평균"

    else:

        series = grouped.sum()

        aggregation = "합계"

    series = series.sort_index()

    # 55분 미만 간격의 자료만 시간 단위로 재표본화
    if len(series) > 2:

        median_gap = (
            series.index.to_series()
            .diff()
            .median()
        )

        if (
            pd.notna(median_gap)
            and median_gap < pd.Timedelta(minutes=55)
        ):

            series = (
                series.resample("1h")
                .mean()
                .dropna()
            )

    meta = {
        "subject": subject,
        "region_col": region_col,
        "target": str(target),
        "worse_is_low": worse_is_low,
        "aggregate": aggregation,
        "date_col": date_col,
        "time_col": used_time_col,
        "other_text_cols": [
            column
            for column in nonnum
            if column not in (
                [region_col]
                + date_cols
                + time_cols
            )
            and 1 < sub[column].nunique() <= 12
        ][:4],
        "invalid_datetime_rows": invalid_datetime_rows,
    }

    return series, meta


# ============================================================
# 7. 예측용 특성 생성
# ============================================================

def make_frame(series):

    data = pd.DataFrame(
        {
            "y": series.values,
            "ts": series.index,
        }
    )

    data["date"] = data["ts"].dt.normalize()

    data["slot"] = data["ts"].dt.hour

    data["wd"] = data["ts"].dt.dayofweek

    data["wk"] = (
        data["wd"] >= 5
    ).astype(int)

    data["month"] = data["ts"].dt.month

    data["hol"] = (
        data["date"]
        .dt.strftime("%Y-%m-%d")
        .isin(HOLIDAYS)
        .astype(int)
    )

    data["lag1"] = data["y"].shift(1)

    data["lag2"] = data["y"].shift(2)

    history = data.set_index("ts")["y"]

    data["lag_day"] = (
        data["ts"] - pd.Timedelta(days=1)
    ).map(history)

    data["lag_week"] = (
        data["ts"] - pd.Timedelta(days=7)
    ).map(history)

    data["slot_mean"] = (
        data.groupby("slot")["y"]
        .transform(
            lambda values:
                values.shift(1)
                .rolling(14, min_periods=3)
                .mean()
        )
    )

    data["wd_slot_mean"] = (
        data.groupby(
            ["wd", "slot"]
        )["y"]
        .transform(
            lambda values:
                values.shift(1)
                .rolling(4, min_periods=1)
                .mean()
        )
    )

    return data


FEATS = [
    "slot",
    "wd",
    "wk",
    "hol",
    "month",
    "lag1",
    "lag2",
    "lag_day",
    "lag_week",
    "slot_mean",
    "wd_slot_mean",
]


# ============================================================
# 8. AI 모델 학습 및 예측
# ============================================================

def fit_predict(train, test):

    feature_cols = [
        column
        for column in FEATS
        if train[column].nunique() >= 2
    ]

    if not feature_cols:

        raise ValueError(
            "AI 학습에 사용할 수 있는 특성이 없습니다."
        )

    model = HistGradientBoostingRegressor(
        max_depth=4,
        learning_rate=0.05,
        max_iter=200,
        l2_regularization=1.0,
        min_samples_leaf=max(
            5,
            min(20, len(train) // 20),
        ),
        random_state=0,
    )

    model.fit(
        train[feature_cols],
        train["y"],
    )

    return model.predict(
        test[feature_cols]
    )


# ============================================================
# 9. 혼잡 알림 F1
# ============================================================

def congestion_f1(
    y_true,
    y_pred,
    threshold,
    low,
):

    if low:

        true_alert = y_true <= threshold

        pred_alert = y_pred <= threshold

    else:

        true_alert = y_true >= threshold

        pred_alert = y_pred >= threshold

    tp = int(
        (true_alert & pred_alert).sum()
    )

    precision = (
        tp / pred_alert.sum()
        if pred_alert.sum()
        else np.nan
    )

    recall = (
        tp / true_alert.sum()
        if true_alert.sum()
        else np.nan
    )

    if (
        pd.notna(precision)
        and pd.notna(recall)
        and precision + recall > 0
    ):

        return (
            2 * precision * recall
            / (precision + recall)
        )

    return np.nan


# ============================================================
# 10. 검증 구간 생성
# ============================================================

def make_folds(data):

    max_date = data["date"].max()

    min_date = data["date"].min()

    total_days = (
        max_date - min_date
    ).days + 1

    if total_days < MIN_HISTORY_DAYS:

        return []

    first_boundary = (
        max_date
        - pd.Timedelta(days=TEST_DAYS)
    )

    first_start = (
        first_boundary
        - pd.Timedelta(days=TEST_DAYS)
    )

    return [
        (first_start, first_boundary),
        (first_boundary, max_date),
    ]


# ============================================================
# 11. 예측 성능 평가
# ============================================================

def evaluate(data, low):

    # 먼저 검증 구간을 구성합니다.
    valid_splits = []

    for lower_date, upper_date in make_folds(data):

        train = data[
            data["date"] <= lower_date
        ].dropna(
            subset=["y", "lag1"]
        )

        test = data[
            (data["date"] > lower_date)
            & (data["date"] <= upper_date)
        ].dropna(
            subset=["lag1"]
        ).copy()

        if len(train) >= 30 and len(test) >= 5:

            valid_splits.append(
                (lower_date, upper_date, train, test)
            )

    # AI 학습 전에 시험 관측 수 확인
    total_test_count = sum(
        len(test)
        for _, _, _, test in valid_splits
    )

    if total_test_count < MIN_TEST_OBS:

        print(
            f"[검증 보류] 시험 관측 {total_test_count}개 "
            f"(최소 필요 {MIN_TEST_OBS}개)"
        )

        return []

    folds = []

    for lower_date, upper_date, train, test in valid_splits:

        predictions = {
            BASES[0]: test["lag1"].values,

            BASES[1]: (
                test["lag_day"]
                .fillna(test["lag1"])
                .values
            ),

            BASES[2]: (
                test["wd_slot_mean"]
                .fillna(test["slot_mean"])
                .fillna(test["lag1"])
                .values
            ),

            MODEL: fit_predict(
                train,
                test,
            ),
        }

        threshold = float(
            train["y"].quantile(
                0.25 if low else 0.75
            )
        )

        actual = test["y"].values

        mae = {
            name: round(
                float(
                    np.abs(
                        actual - prediction
                    ).mean()
                ),
                3,
            )
            for name, prediction in predictions.items()
        }

        f1 = {}

        for name, prediction in predictions.items():

            score = congestion_f1(
                actual,
                prediction,
                threshold,
                low,
            )

            f1[name] = (
                None
                if pd.isna(score)
                else round(float(score), 3)
            )

        folds.append(
            {
                "test_from": str(
                    (lower_date + pd.Timedelta(days=1)).date()
                ),

                "test_to": str(
                    upper_date.date()
                ),

                "n": int(len(test)),

                "threshold": round(
                    threshold,
                    2,
                ),

                "MAE": mae,

                "F1": f1,

                "_te": test.assign(
                    **predictions
                ),
            }
        )

    return folds


# ============================================================
# 12. 성능 판정
# ============================================================

def verdict(folds):

    test_count = sum(
        fold["n"]
        for fold in folds
    )

    if (
        not folds
        or test_count < MIN_TEST_OBS
    ):

        return {
            "code": "small",
            "n_test": test_count,
            "text": (
                "시험에 사용할 관측이 부족하여 "
                "모델 성능을 판단할 수 없습니다."
            ),
        }

    model_mae = np.mean(
        [
            fold["MAE"][MODEL]
            for fold in folds
        ]
    )

    baseline_mae = {
        name: np.mean(
            [
                fold["MAE"][name]
                for fold in folds
            ]
        )
        for name in BASES
    }

    best_baseline = min(
        baseline_mae,
        key=baseline_mae.get,
    )

    best_baseline_mae = baseline_mae[
        best_baseline
    ]

    relative_improvement = (
        (best_baseline_mae - model_mae)
        / best_baseline_mae
        if best_baseline_mae
        else 0.0
    )

    wins = sum(
        fold["MAE"][MODEL]
        < min(
            fold["MAE"][name]
            for name in BASES
        )
        for fold in folds
    )

    if (
        relative_improvement > 0.05
        and wins == len(folds)
    ):

        code = "better"

    elif relative_improvement < -0.02:

        code = "worse"

    else:

        code = "same"

    return {
        "code": code,
        "n_test": test_count,
        "best_baseline": best_baseline,
        "rel_improvement_pct": round(
            relative_improvement * 100,
            1,
        ),
        "wins": wins,
        "folds": len(folds),
    }


# ============================================================
# 13. 그래프 생성
# ============================================================

def charts(data, folds, low, target):

    import matplotlib.pyplot as plt

    setup_font()

    # 요일·시간대 평균
    pivot = (
        data.pivot_table(
            index="wd",
            columns="slot",
            values="y",
            aggfunc="mean",
        )
        .reindex(range(7))
    )

    figure, axis = plt.subplots(
        figsize=(8, 3.8)
    )

    image = axis.imshow(
        pivot.values,
        aspect="auto",
        cmap="Blues_r" if low else "Blues",
    )

    axis.set_xticks(
        range(len(pivot.columns))
    )

    axis.set_xticklabels(
        [
            f"{int(hour)}시"
            for hour in pivot.columns
        ]
    )

    axis.set_yticks(range(7))

    axis.set_yticklabels(WD)

    axis.set_title(
        f"울산 요일·시간대별 평균 ({target})"
    )

    figure.colorbar(
        image,
        ax=axis,
    )

    figure.savefig(
        CHARTS / "er_pattern.png",
        dpi=150,
        bbox_inches="tight",
    )

    plt.close(figure)

    pivot.round(2).to_csv(
        PROC / "er_pattern.csv",
        encoding="utf-8-sig",
    )

    methods = BASES + [MODEL]

    # MAE 비교 그래프
    figure, axis = plt.subplots(
        figsize=(8, 4)
    )

    width = 0.8 / len(methods)

    for index, method in enumerate(methods):

        axis.bar(
            np.arange(len(folds))
            + index * width,

            [
                fold["MAE"][method]
                for fold in folds
            ],

            width,

            label=method,

            color=(
                NAVY
                if method == MODEL
                else [
                    GRAY,
                    "#B9C2CC",
                    "#5B6B7E",
                ][index]
            ),
        )

    axis.set_xticks(
        np.arange(len(folds))
        + 0.4
        - width / 2
    )

    axis.set_xticklabels(
        [
            f"{fold['test_from']}~{fold['test_to']}"
            for fold in folds
        ],
        fontsize=8,
    )

    axis.set_ylabel(
        "평균 오차(MAE)"
    )

    axis.set_title(
        "예측 시험: 평균 오차 비교 (낮을수록 좋음)"
    )

    axis.legend(
        fontsize=7,
        frameon=False,
    )

    axis.spines[
        ["top", "right"]
    ].set_visible(False)

    figure.savefig(
        CHARTS / "er_eval.png",
        dpi=150,
        bbox_inches="tight",
    )

    plt.close(figure)

    # 실제값과 예측값 비교
    test_data = folds[-1]["_te"].tail(
        24 * 7
    )

    best_baseline = min(
        BASES,
        key=lambda name: np.mean(
            [
                fold["MAE"][name]
                for fold in folds
            ]
        ),
    )

    figure, axis = plt.subplots(
        figsize=(9, 3.6)
    )

    axis.plot(
        test_data["ts"],
        test_data["y"],
        color=NAVY,
        linewidth=1.5,
        label="실제",
    )

    axis.plot(
        test_data["ts"],
        test_data[MODEL],
        color=RED,
        linewidth=1.2,
        label="AI 모델",
    )

    axis.plot(
        test_data["ts"],
        test_data[best_baseline],
        color=GRAY,
        linewidth=1,
        linestyle="--",
        label=best_baseline,
    )

    axis.set_title(
        "시험 구간 마지막 부분: 실제와 예측"
    )

    axis.legend(
        fontsize=8,
        frameon=False,
    )

    axis.spines[
        ["top", "right"]
    ].set_visible(False)

    figure.autofmt_xdate()

    figure.savefig(
        CHARTS / "er_example.png",
        dpi=150,
        bbox_inches="tight",
    )

    plt.close(figure)


# ============================================================
# 14. 실행
# ============================================================

if __name__ == "__main__":

    source_name, raw = load_source()

    series, meta = prepare_series(
        raw,
        source_name,
    )

    print("\n===== STEP 2 자료 확인 =====")

    print(
        f"자료: {source_name}"
    )

    print(
        f"분석 대상: {meta['subject']}"
    )

    print(
        f"지역 열: {meta['region_col']}"
    )

    print(
        f"예측 대상: {meta['target']}"
    )

    print(
        f"집계 방식: {meta['aggregate']}"
    )

    print(
        f"날짜 열: {meta['date_col']}"
    )

    print(
        f"시간 열: {meta['time_col']}"
    )

    print(
        f"관측 개수: {len(series)}"
    )

    print(
        f"관측 시작: {series.index.min()}"
    )

    print(
        f"관측 종료: {series.index.max()}"
    )

    unique_days = (
        series.index.normalize().nunique()
    )

    print(
        f"관측 날짜 수: {unique_days}일"
    )

    # 데이터가 부족하면 모델 학습 및 그래프 생성을 하지 않음
    if (
        len(series) < 30
        or unique_days < MIN_HISTORY_DAYS
    ):

        result = {
            "status": "insufficient_data",
            "source": source_name,
            **meta,
            "n_obs": int(len(series)),
            "n_days": int(unique_days),
            "from": str(series.index.min()),
            "to": str(series.index.max()),
            "model_trained": False,
            "evaluation_performed": False,
            "charts_generated": False,
            "reason": (
                f"모델 검증에는 최소 {MIN_HISTORY_DAYS}일의 "
                "관측 기간이 필요합니다."
            ),
            "verdict": {
                "code": "small",
                "text": (
                    "자료가 부족하여 AI 예측 성능을 "
                    "검증하지 않았습니다."
                ),
            },
        }

        PROC.mkdir(
            parents=True,
            exist_ok=True,
        )

        save_json(
            result,
            PROC / "er_eval.json",
        )

        print("\n[검증 보류]")

        print(
            f"필요한 관측 기간: {MIN_HISTORY_DAYS}일 이상"
        )

        print(
            f"현재 관측 기간: {unique_days}일"
        )

        print(
            "AI 모델 학습 및 MAE·F1 평가를 수행하지 않았습니다."
        )

        print(
            "요일·시간대 패턴 그래프도 생성하지 않았습니다."
        )

        print(
            "검증 보류 사유를 er_eval.json에 기록했습니다."
        )

        sys.exit(0)

    # 충분한 데이터가 있을 때만 예측용 데이터 구성
    data = make_frame(series)

    folds = evaluate(
        data,
        meta["worse_is_low"],
    )

    result_verdict = verdict(folds)

    print("\n===== 예측 시험 결과 =====")

    # 시험 데이터가 부족하면 모델 평가 결과를 만들지 않음
    if (
        not folds
        or sum(
            fold["n"]
            for fold in folds
        ) < MIN_TEST_OBS
    ):

        print(
            "[검증 보류] 시험 관측 수가 부족합니다."
        )

        print(
            "AI 모델 학습 및 성능 비교를 수행하지 않았습니다."
        )

        print(
            "성능 비교 그래프와 예측 사례 그래프를 생성하지 않습니다."
        )

        PROC.mkdir(
            parents=True,
            exist_ok=True,
        )

        save_json(
            {
                "status": "insufficient_test_data",
                "source": source_name,
                **meta,
                "n_obs": int(len(series)),
                "from": str(series.index.min()),
                "to": str(series.index.max()),
                "folds": [],
                "verdict": result_verdict,
                "model_trained": False,
                "evaluation_performed": False,
                "charts_generated": False,
            },
            PROC / "er_eval.json",
        )

        sys.exit(0)

    for fold in folds:

        print(
            f"[시험 {fold['test_from']}~{fold['test_to']}, "
            f"{fold['n']}개]"
        )

        print(
            "MAE: "
            + " / ".join(
                f"{name}: {score}"
                for name, score in fold["MAE"].items()
            )
        )

        print(
            "F1: "
            + " / ".join(
                f"{name}: {score}"
                for name, score in fold["F1"].items()
            )
        )

    print(
        "\n최종 판정:",
        result_verdict,
    )

    # 충분한 검증 결과가 있을 때만 그래프 생성
    CHARTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    PROC.mkdir(
        parents=True,
        exist_ok=True,
    )

    charts(
        data,
        folds,
        meta["worse_is_low"],
        meta["target"],
    )

    # 시계열 저장
    pd.DataFrame(
        {
            "ts": series.index,
            "y": series.values,
        }
    ).to_csv(
        PROC / "er_series.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # 최종 평가 결과 저장
    save_json(
        {
            "status": "evaluated",
            "source": source_name,
            **meta,
            "n_obs": int(len(series)),
            "from": str(series.index.min()),
            "to": str(series.index.max()),
            "folds": [
                {
                    key: value
                    for key, value in fold.items()
                    if key != "_te"
                }
                for fold in folds
            ],
            "verdict": result_verdict,
            "model_trained": True,
            "evaluation_performed": True,
            "charts_generated": True,
        },
        PROC / "er_eval.json",
    )

    print("\nSTEP 2 완료")
