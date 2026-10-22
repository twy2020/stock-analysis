"""Prepare daily stock data for a CNN + Transformer training pipeline.

The script deliberately computes every feature in chronological order. Rolling
features and the Kalman state are causal; only the target columns use future
observations. The scaler is fitted on the chronological training part only.

Example:
    python scripts/preprocess_stock_data.py \
        --input datasets/data_test/stock_daily.csv \
        --output-dir datasets/processed

For a real time split, prefer an explicit date:
    python scripts/preprocess_stock_data.py --train-end 2025-12-31
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "trade_date", "ts_code", "open", "high", "low", "close",
    "pre_close", "change", "pct_chg", "vol", "amount",
}
META_COLUMNS = ["trade_date", "ts_code", "industry"]
TARGET_COLUMNS = ["target_return_5d", "target_up_5d", "target_volatility_5d"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("datasets/data_test/stock_daily.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("datasets/processed"))
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--train-end", type=str, default=None, help="Inclusive YYYY-MM-DD training cutoff")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--kalman-q", type=float, default=0.0001)
    parser.add_argument("--kalman-r", type=float, default=0.01)
    return parser.parse_args()


def read_input(path: Path) -> pd.DataFrame:
    # UTF-8 is the source encoding; utf-8-sig also handles files exported with a BOM.
    df = pd.read_csv(path, encoding="utf-8-sig")
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["trade_date"] = pd.to_datetime(df["trade_date"], dayfirst=True, errors="coerce")
    if df["trade_date"].isna().any():
        raise ValueError("trade_date contains values that cannot be parsed")

    numeric_columns = sorted(REQUIRED_COLUMNS - {"trade_date", "ts_code"})
    for column in numeric_columns:
        if column == "industry":
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df.duplicated(["ts_code", "trade_date"]).any():
        duplicate_count = int(df.duplicated(["ts_code", "trade_date"]).sum())
        raise ValueError(f"Found {duplicate_count} duplicate stock/date rows")

    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    return df


def rolling_zscore(series: pd.Series, window: int = 20, min_periods: int = 10) -> pd.Series:
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def causal_kalman_log_price(log_price: Iterable[float], q: float, r: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Two-state local-linear-trend Kalman filter: [level, velocity]."""
    values = np.asarray(list(log_price), dtype=float)
    levels = np.full(len(values), np.nan)
    velocities = np.full(len(values), np.nan)
    residuals = np.full(len(values), np.nan)
    state = np.array([values[0], 0.0], dtype=float)
    covariance = np.eye(2, dtype=float)
    transition = np.array([[1.0, 1.0], [0.0, 1.0]])
    observation = np.array([1.0, 0.0])
    process_noise = q * np.array([[0.25, 0.5], [0.5, 1.0]])

    for i, observation_value in enumerate(values):
        if i:
            state = transition @ state
            covariance = transition @ covariance @ transition.T + process_noise
        innovation = observation_value - observation @ state
        innovation_variance = observation @ covariance @ observation.T + r
        gain = (covariance @ observation) / innovation_variance
        state = state + gain * innovation
        covariance = (np.eye(2) - np.outer(gain, observation)) @ covariance
        levels[i], velocities[i], residuals[i] = state[0], state[1], innovation
    return levels, velocities, residuals


def add_features(group: pd.DataFrame, horizon: int, kalman_q: float, kalman_r: float) -> pd.DataFrame:
    group = group.copy()
    close = group["close"].clip(lower=1e-12)
    prev_close = group["pre_close"].replace(0, np.nan)
    log_close = np.log(close)
    ret = close.pct_change()

    # Price action and relative representations. These are scale-independent
    # and are the main inputs for the convolutional branch.
    group["feat_return_1d"] = close / prev_close - 1.0
    group["feat_log_return_1d"] = log_close.diff()
    group["feat_open_gap"] = group["open"] / prev_close - 1.0
    group["feat_open_to_close"] = group["open"] / close - 1.0
    group["feat_high_to_close"] = group["high"] / close - 1.0
    group["feat_low_to_close"] = group["low"] / close - 1.0
    group["feat_intraday_range"] = (group["high"] - group["low"]) / close
    group["feat_body"] = (group["close"] - group["open"]) / close
    group["feat_upper_shadow"] = (group["high"] - group[["open", "close"]].max(axis=1)) / close
    group["feat_lower_shadow"] = (group[["open", "close"]].min(axis=1) - group["low"]) / close

    # Activity and rolling statistics.
    group["feat_log_volume"] = np.log1p(group["vol"].clip(lower=0))
    group["feat_log_amount"] = np.log1p(group["amount"].clip(lower=0))
    group["feat_volume_change"] = group["vol"].pct_change().replace([np.inf, -np.inf], np.nan)
    group["feat_amount_change"] = group["amount"].pct_change().replace([np.inf, -np.inf], np.nan)
    group["feat_volatility_5d"] = ret.rolling(5, min_periods=5).std(ddof=0)
    group["feat_volatility_20d"] = ret.rolling(20, min_periods=10).std(ddof=0)
    group["feat_momentum_5d"] = close / close.shift(5) - 1.0
    group["feat_momentum_20d"] = close / close.shift(20) - 1.0

    sma5 = close.rolling(5, min_periods=5).mean()
    sma20 = close.rolling(20, min_periods=10).mean()
    ema12 = close.ewm(span=12, adjust=False, min_periods=5).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=10).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=5).mean()
    rolling_std20 = close.rolling(20, min_periods=10).std(ddof=0)
    group["feat_sma5_distance"] = close / sma5 - 1.0
    group["feat_sma20_distance"] = close / sma20 - 1.0
    group["feat_ema12_distance"] = close / ema12 - 1.0
    group["feat_ema26_distance"] = close / ema26 - 1.0
    group["feat_macd_relative"] = macd / close
    group["feat_macd_signal_relative"] = macd_signal / close
    group["feat_bollinger_position"] = (close - sma20) / (2.0 * rolling_std20.replace(0, np.nan))

    delta = close.diff()
    up = delta.clip(lower=0).rolling(14, min_periods=10).mean()
    down = (-delta.clip(upper=0)).rolling(14, min_periods=10).mean()
    group["feat_rsi14"] = (100.0 - 100.0 / (1.0 + up / down.replace(0, np.nan))) / 100.0
    true_range = pd.concat([
        group["high"] - group["low"],
        (group["high"] - prev_close).abs(),
        (group["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    group["feat_atr14_relative"] = true_range.rolling(14, min_periods=10).mean() / close

    # Causal state features; no future observations are used here.
    level, velocity, innovation = causal_kalman_log_price(log_close, kalman_q, kalman_r)
    group["feat_kalman_level_distance"] = log_close.to_numpy() - level
    group["feat_kalman_trend"] = velocity
    group["feat_kalman_residual"] = innovation
    group["feat_kalman_residual_z20"] = rolling_zscore(pd.Series(innovation, index=group.index), 20, 10)

    # Future-only targets. These rows are removed after all features are made.
    group["target_return_5d"] = close.shift(-horizon) / close - 1.0
    group["target_up_5d"] = (group["target_return_5d"] > 0).astype("float64")
    group["target_volatility_5d"] = ret.shift(-1).rolling(horizon, min_periods=horizon).std(ddof=0).shift(-(horizon - 1))
    return group


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("feat_")]


def fit_scale(df: pd.DataFrame, columns: list[str], train_mask: pd.Series) -> tuple[pd.DataFrame, dict]:
    output = df.copy()
    stats: dict[str, dict[str, float]] = {}
    for column in columns:
        values = pd.to_numeric(output.loc[train_mask, column], errors="coerce")
        mean = float(values.mean()) if values.notna().any() else 0.0
        std = float(values.std(ddof=0)) if values.notna().any() else 1.0
        if not np.isfinite(std) or std < 1e-12:
            std = 1.0
        scaled_name = f"x_{column[5:]}"
        output[scaled_name] = (output[column] - mean) / std
        stats[scaled_name] = {"source": column, "mean": mean, "std": std}
    return output, stats


def main() -> None:
    args = parse_args()
    if not 0.5 <= args.train_ratio < 1.0:
        raise ValueError("--train-ratio must be in [0.5, 1.0)")
    if args.horizon < 1:
        raise ValueError("--horizon must be positive")

    raw = read_input(args.input)
    pieces = [add_features(g, args.horizon, args.kalman_q, args.kalman_r) for _, g in raw.groupby("ts_code", sort=False)]
    processed = pd.concat(pieces, ignore_index=True).sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    processed = processed.replace([np.inf, -np.inf], np.nan)
    processed = processed.dropna(subset=feature_columns(processed) + TARGET_COLUMNS).reset_index(drop=True)

    unique_dates = processed["trade_date"].drop_duplicates().sort_values().reset_index(drop=True)
    if args.train_end:
        train_end = pd.Timestamp(args.train_end)
    else:
        split_index = max(0, min(len(unique_dates) - 1, int(len(unique_dates) * args.train_ratio) - 1))
        train_end = unique_dates.iloc[split_index]
    train_mask = processed["trade_date"] <= train_end
    if train_mask.sum() == 0 or train_mask.sum() == len(processed):
        raise ValueError(f"Training cutoff {train_end.date()} does not leave both train and future rows")

    raw_feature_cols = feature_columns(processed)
    processed, scaler = fit_scale(processed, raw_feature_cols, train_mask)
    scaled_feature_cols = [f"x_{c[5:]}" for c in raw_feature_cols]
    processed["split"] = np.where(processed["trade_date"] <= train_end, "train", "future")
    processed = processed.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = args.output_dir / "stock_daily_processed.csv"
    processed.to_csv(output_csv, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    schema = {
        "source": str(args.input),
        "rows_raw": int(len(raw)),
        "rows_output": int(len(processed)),
        "date_min": str(processed["trade_date"].min().date()),
        "date_max": str(processed["trade_date"].max().date()),
        "train_end": str(train_end.date()),
        "metadata_columns": META_COLUMNS + ["split"],
        "raw_columns_kept": [c for c in ["open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"] if c in processed],
        "raw_feature_columns": raw_feature_cols,
        "model_feature_columns": scaled_feature_cols,
        "target_columns": TARGET_COLUMNS,
        "excluded_from_model": ["ts_code", "industry", "trade_date"] + raw_feature_cols,
        "kalman": {"type": "causal_local_linear_trend", "q": args.kalman_q, "r": args.kalman_r},
        "scaler": scaler,
    }
    (args.output_dir / "feature_schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_csv} ({len(processed)} rows)")
    print(f"Model features: {len(scaled_feature_cols)}; targets: {', '.join(TARGET_COLUMNS)}")
    print(f"Train cutoff: {train_end.date()} ({int(train_mask.sum())} rows); future rows: {int((~train_mask).sum())}")


if __name__ == "__main__":
    main()
