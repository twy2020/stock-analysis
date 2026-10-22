# 回测口径与规则结构

引擎：`<项目>/bt.py`。前端白板 `runBacktest` 与它同口径，算法回测页调 `/api/backtest/scan` 和 `/api/backtest/detail`。

## 规则 JSON

买卖两侧结构相同，`conditions` 至少一条；每条条件最终都编译成**一条表达式**（见 `expressions.md`）：

```json
{
  "buy": {"conditions": [
    {"expr": "CROSS(MA(CLOSE,5),MA(CLOSE,20))", "join": "and", "negate": false, "size": null}
  ]},
  "sell": {"conditions": [
    {"expr": "CROSSDOWN(MA(CLOSE,5),MA(CLOSE,20))", "join": "or", "negate": false, "size": null},
    {"expr": "ABS(RSI(CLOSE,14)-70)<=0.5", "join": "or", "negate": false, "size": 50}
  ]},
  "settings": {"cash": 100000, "fee": 0.0003, "buySize": 100, "sellSize": 100, "buyDelay": 0, "sellDelay": 0},
  "days": 242, "warmup": 250, "excludeST": true
}
```

条件字段：

| 字段 | 说明 |
| --- | --- |
| `expr` | 表达式字符串。**直接用它表达条件**，最清晰 |
| `join` | 与**上一条**的结合方式：`and`（默认）/ `or`。第一条的 `join` 被忽略 |
| `negate` | true 表示取反，等价于 `NOT(expr)` |
| `size` | 这条条件触发时用多少仓位（1~100 的百分数）；留空/null 表示用全局仓位。**取第一条命中且带 size 的条件** |
| `pnl` / `priceExpr` / `up` / `pct` | 浮盈浮亏条件：`pct` 为阈值，`up=true` 表示浮盈 ≥ pct 触发。依赖持仓成本，**不能用于离线筛查**，只能实时回测 |

结合顺序是**从左到右折叠**，不是按 and/or 优先级重新分组：

```
result = c1
result = result AND c2   (或 result OR c2)
result = result AND c3   ...
```

所以 `c1 且 c2 或 c3` 等于 `((c1 AND c2) OR c3)`。要别的优先级就拆成多条或自己写括号。

## 撮合口径

- **信号用收盘价判断**：第 i 根收盘后，用 `series[i]` 得到信号。
- **信号下一根的开盘价成交**（`buyDelay=0`），也就是常说的"收盘出信号、次日开盘成交"。`buyDelay=1` 表示再往后推一根；买卖各有独立延迟。
- **同一根 K 线先卖后买**（`sell` 分支先于 `buy` 分支），不会在同一根既买又卖。
- **买入按手取整并预留手续费**：`手数 = floor(可用资金 × 仓位% / (开盘价 × (1+手续费率) × 100))`，不足 1 手就买不进。
- **卖出**：仓位 ≥100% 时清仓；否则取整到 100 股的整数倍，至少卖 100 股。
- **只有回到空仓才算一笔完整交易**（`trades`）；部分买入/卖出都计入 `fills`。
- **手续费单边收取**（买入和卖出各收一次），默认 `fee=0.0003`（万三）。**没有滑点、没有冲击成本、不检查涨跌停能否成交**——信号出现在一字涨停板上时，回测会假设你能买到，实盘往往买不到。
- 权益 `equity[i] = 现金 + 持股数 × 收盘价`，每天按收盘价重估。

## 参数范围与默认

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `days` | 242 | 20 ~ 1210 | 回测区间（交易日根数），1210 ≈ 5 年。242 对应一年 |
| `warmup` | 250 | 0 ~ 600 | 预热根数，用来把均线等指标算热；不够长会让前段信号缺失 |
| `cash` | 100000 | ≥1 | 每只股票各自的初始资金 |
| `fee` | 0.0003 | ≥0 | 单边手续费率 |
| `buySize` / `sellSize` | 100 | 1~100 | 全局仓位 % |
| `buyDelay` / `sellDelay` | 0 | 0~30 | 信号后再延几根成交 |
| `excludeST` | 见说明 | — | 剔除名称含 ST 的股票。页面默认勾选，但**直接调 API 不传就是不剔除**（`bool(None)=False`） |
| `sample` | 0（全部） | — | 随机抽样只数，快速预览用；固定随机种子，同参数结果可复现 |

## 指标定义（单只股票）

| 字段 | 含义 |
| --- | --- |
| `total_return` | 期末权益 / 初始资金 − 1 |
| `annual` | 年化收益，按 242 交易日/年折算 |
| `max_drawdown` | 权益曲线最大回撤（1 − 当前/峰值 的最大值） |
| `benchmark` | 同期**等额买入持有**收益率，是策略的对照基准 |
| `trades` / `wins` | 完整交易笔数 / 其中盈利笔数 |
| `fills` | 成交笔数（含部分买卖） |
| `avg_position` | 平均仓位 = `(持股数×收盘价)/权益` 的时间均值 |
| `hold_days` / `flat_days` | 持仓 / 空仓的交易日数 |
| `hold_daily` / `flat_daily` | 持仓日 / 空仓日的**权益日收益均值**（即"持仓时日均收益率"） |
| `fees_paid` | 累计手续费 |
| `signals.buy` / `signals.sell` | 逐根的买卖信号序列，用来在 K 线图上画判断线 |
| `trades[]` | 每笔完整交易的 `entry` / `exit` 下标、`bars` 持有根数、进出价、盈亏 |

## 全市场扫描的汇总口径

- `scanned`：数据够长、真正参与回测的股票数；`skipped`：数据不足或计算出错的
- `traded`：**至少成交过一次**的股票数；`participation = traded/scanned`
- `success_rate = success/traded`：`success` 是收益率 > 0 的股票数，**分母只算有成交的**，不是全部股票
- `total_return`：**等权累加**——每只股票投同样的钱（各 `cash`），把各自的收益率直接相加。这是"策略平均表现"的度量，**不等于**一个真实组合的资金曲线，也不能当组合收益率用
- `profit`：各股盈亏金额之和；`invested`：有成交股票投入的资金合计
- `avg_return` / `avg_benchmark` / `avg_drawdown`：都只对有成交的股票求平均
- `stocks[]`：逐只结果 `{c:代码, n:名称, r:收益率, t:完整交易数, d:最大回撤, b:同期买入持有, f:成交笔数}`，前端按盈利/亏损分类浏览

对比策略优劣时，至少同时看：`avg_return` vs `avg_benchmark`（有没有跑赢躺平）、`success_rate`（多少只赚钱）、`avg_drawdown`、`trade_win_rate`、`trades`（样本够不够）。

## HTTP 调用

```bash
# 全市场扫描（sample=0 表示全部；excludeST 是 camelCase）
curl -X POST http://127.0.0.1:8765/api/backtest/scan \
  -H "Content-Type: application/json" \
  -d '{"buy":{"conditions":[{"expr":"CROSS(MA(CLOSE,5),MA(CLOSE,20))"}]},
       "sell":{"conditions":[{"expr":"CROSSDOWN(MA(CLOSE,5),MA(CLOSE,20))"}]},
       "settings":{"cash":100000,"fee":0.0003},
       "days":242,"warmup":250,"excludeST":true}'

# 单只股票明细：多返回权益曲线、买卖点、指标线（overlays）与信号处的指标值（events）
curl -X POST http://127.0.0.1:8765/api/backtest/detail \
  -H "Content-Type: application/json" \
  -d '{"code":"000001","buy":{"conditions":[...]},"sell":{"conditions":[...]},
       "settings":{},"days":242,"overlays":[{"expr":"RSI(CLOSE,14)","title":"RSI14"}]}'
```

扫描走多进程，先用 `sample=200` 快速试参数，确认口径没问题再放全量。

实测耗时（本机 12 进程，近 1 年区间、单买点单卖点）：`sample=300` 约 1.8 秒；**全市场 4924 只约 9.6 秒**，响应体约 485 KB。

## 一份基准样例（用来校准"数字正常长什么样"）

策略：`CROSS(MA(CLOSE,5),MA(CLOSE,20))` 买、`CROSSDOWN(...)` 卖，满仓、万三手续费、剔除 ST、近 1 年：

```text
scanned 4924 · traded 4922 · excluded_st 201 · success_rate 35.9%
avg_return +1.75%   avg_benchmark -1.36%   avg_drawdown 30.2%
trades 34051 · trade_win_rate 30.0%
```

读法：均线金叉死叉这种"人人都会"的信号，一年里跑赢躺平只有约 3 个百分点，平均回撤却有 30%，交易胜率 30%——靠盈亏比活着。**看到 avg_return 明显低于 avg_benchmark 的策略，先怀疑是不是反向指标**；看到 success_rate 高但 avg_return 低，说明赚小亏大。
