# 数据审计发现

## 当前状态

`datasets/data_test` 只有 `stock_daily.csv`：1000 行、12 列，单只股票 `002322.SZ`。

原始字段：

```text
trade_date, ts_code, open, high, low, close, pre_close,
change, pct_chg, vol, amount, industry
```

初步观察：

- `trade_date` 是字符串，样例格式为 `19/8/2026`，数据当前按新到旧倒序。
- OHLC、`pre_close`、`change`、`pct_chg`、`vol`、`amount` 为数值列，当前没有缺失值。
- `ts_code` 和 `industry` 各只有一个取值；`industry` 按默认 UTF-8 读取时显示乱码，需在脚本中处理编码/保留原始值。
- 当前数据没有大盘、行业指数、技术指标或 Kalman 字段，需要从 OHLCV 派生技术和状态特征。
- 当前数据只有单只股票，适合验证预处理流程，不足以验证跨股票泛化。

## 字段与输出决策

- 已实现 31 个标准化模型输入字段，包含价格行为、成交活动、滚动波动/动量、均线距离、MACD、布林带、RSI、ATR 和 4 个 Kalman 状态特征。
- 已实现 3 个 5 日多任务目标：收益率、上涨方向、未来波动率。
- 预处理后有效行数为 975；默认最早 80% 有效日期为 train（780 行），其余 195 行为 future。
- 输出无缺失值，时间升序，输入字段和 scaler 统计写入 `feature_schema.json`。

## 设计约束

- 模型方向：多因子输入 + 多尺度 CNN + Transformer。
- Kalman 作为额外状态/趋势/残差特征，不替代原始序列。
- 训练主体优先使用收益率、相对价格、标准化和滚动特征。
- scaler 只能使用训练窗口拟合；不能对全量数据先拟合。
- Kalman 必须是因果滤波，不能使用未来观测。
