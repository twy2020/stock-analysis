from __future__ import annotations

import numpy as np


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray, prefix: str) -> dict[str, float]:
    error = y_pred - y_true
    return {
        f"{prefix}_mae": float(np.mean(np.abs(error))),
        f"{prefix}_rmse": float(np.sqrt(np.mean(error ** 2))),
        f"{prefix}_direction_accuracy": float(np.mean(np.sign(y_true) == np.sign(y_pred))),
    }


def classification_metrics(y_true: np.ndarray, probability: np.ndarray, prefix: str) -> dict[str, float]:
    pred = (probability >= 0.5).astype(int)
    accuracy = float(np.mean(pred == y_true))
    eps = 1e-7
    logloss = float(-np.mean(y_true * np.log(probability.clip(eps, 1 - eps)) + (1 - y_true) * np.log((1 - probability).clip(eps, 1 - eps))))
    return {f"{prefix}_accuracy": accuracy, f"{prefix}_logloss": logloss, f"{prefix}_positive_rate": float(np.mean(pred))}


def strategy_metrics(y_true: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    position = (probability >= 0.5).astype(float)
    strategy_returns = position * y_true
    benchmark = y_true
    def sharpe(x: np.ndarray) -> float:
        return float(np.sqrt(252) * x.mean() / (x.std(ddof=0) + 1e-8))
    def max_drawdown(x: np.ndarray) -> float:
        curve = np.cumprod(1 + x)
        return float(np.min(curve / np.maximum.accumulate(curve) - 1))
    return {
        "strategy_total_return": float(np.prod(1 + strategy_returns) - 1),
        "strategy_sharpe": sharpe(strategy_returns),
        "strategy_max_drawdown": max_drawdown(strategy_returns),
        "buy_hold_total_return": float(np.prod(1 + benchmark) - 1),
    }
