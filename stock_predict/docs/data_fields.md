# 股票模型训练字段方案

## 原始数据审计

文件：`datasets/data_test/stock_daily.csv`

- 记录数：1000
- 股票数：1（`002322.SZ`）
- 日期范围：2022-07-07 至 2026-08-19
- 时间顺序：原始文件倒序；预处理输出升序
- 原始字段无空值、无重复的 `ts_code + trade_date` 记录
- `pct_chg` 与 `close / pre_close - 1` 一致（仅有四舍五入误差）

## 原始字段处理

| 字段 | 类型 | 用途 |
|---|---|---|
| `trade_date` | 日期 | 元数据和时间切分，不直接输入模型 |
| `ts_code` | 类别 | 股票标识；多股票训练时用于 embedding 或分组，不直接当连续值 |
| `industry` | 类别 | 行业元数据；多行业训练时可做 embedding |
| `open`, `high`, `low`, `close` | 数值 | 派生价格行为、收益率、相对位置和波动特征 |
| `pre_close` | 数值 | 派生隔夜缺口和日收益率 |
| `change`, `pct_chg` | 数值 | 原始变化记录；模型以派生的 `feat_return_1d` 为主，避免重复输入 |
| `vol` | 数值 | `log1p`、变化率和滚动活动特征 |
| `amount` | 数值 | `log1p` 和变化率特征 |

## 模型输入字段

预处理脚本生成 `feat_*` 原始派生特征，并生成对应的 `x_*` 标准化模型字段。训练时使用 `feature_schema.json` 中的 `model_feature_columns`，当前共有 31 个：

```text
x_return_1d
x_log_return_1d
x_open_gap
x_open_to_close
x_high_to_close
x_low_to_close
x_intraday_range
x_body
x_upper_shadow
x_lower_shadow
x_log_volume
x_log_amount
x_volume_change
x_amount_change
x_volatility_5d
x_volatility_20d
x_momentum_5d
x_momentum_20d
x_sma5_distance
x_sma20_distance
x_ema12_distance
x_ema26_distance
x_macd_relative
x_macd_signal_relative
x_bollinger_position
x_rsi14
x_atr14_relative
x_kalman_level_distance
x_kalman_trend
x_kalman_residual
x_kalman_residual_z20
```

这些字段可以直接组成 CNN/Transformer 输入张量：

```text
[batch_size, sequence_length, 31]
```

## 训练目标

```text
target_return_5d       # 从当前收盘到未来第 5 个交易日的收益率，回归
target_up_5d           # target_return_5d > 0，二分类
target_volatility_5d   # 未来 5 个交易日收益率的波动率，回归
```

目标列使用未来数据，只作为 label，不能放进输入特征。

## 防止数据泄漏

- 所有滚动统计按时间升序、只使用当前及过去数据。
- Kalman 使用因果 local-linear-trend filter，不使用未来观测。
- scaler 只在训练时间段拟合，再应用于后续数据。
- 默认训练切分为最早 80% 的有效日期；实际实验建议通过 `--train-end YYYY-MM-DD` 指定固定切分日期。
- 生成标签后，因技术指标预热期和未来标签不足而删除边界行。

## 输出文件

运行脚本后生成：

- `datasets/processed/stock_daily_processed.csv`：排序后的元数据、原始列、派生列、标准化模型输入、标签和 `split`。
- `datasets/processed/feature_schema.json`：字段列表、训练截止日期、Kalman 参数和 scaler 统计量。

## 运行方式

```powershell
python scripts/preprocess_stock_data.py `
  --input datasets/data_test/stock_daily.csv `
  --output-dir datasets/processed `
  --train-end 2025-12-31
```
