# 取数与调用

默认路径 `C:\Users\35788\Desktop\量化工具`（环境变量 `QUANTLAB_HOME` 可覆盖）。服务默认 `http://127.0.0.1:8765`，局域网地址（形如 `http://192.168.3.5:8765`）在启动窗口里打印。完整接口说明见项目内 `数据库查询接口.md`。

服务没起来就先启动：双击项目里的 `启动量化工具.bat`（会绑到 `0.0.0.0`、自动放行防火墙、打印局域网地址），或手工 `python server.py`。确认活着用 `GET /api/health`。

## 库里有什么

`market.db`（SQLite，GB 级）两张表：

**stocks** — 股票元信息（每只在市股票一行）

| 字段 | 说明 |
| --- | --- |
| `code` | 6 位代码，主键 |
| `name` | 名称；**ST 判定就看是否含 `ST`** |
| `symbol` | 带市场后缀，如 `000001.SZ` |
| `bars` | 已入库 K 线根数（`sum(bars)` = `bars` 表真实行数，用它代替 `COUNT(*)` 会快很多） |
| `synced_at` | 最后同步时间 |
| `error` | 同步失败原因，成功为 null |

**bars** — 日线（千万行级，主键 `(code, date)`，另有索引 `idx_bars_date(date)`）

| 字段 | 单位 |
| --- | --- |
| `code` / `date` | 6 位代码 / `YYYY-MM-DD` |
| `open` `high` `low` `close` | 元，**未复权** |
| `volume` | **手**（1 手 = 100 股） |
| `amount` | 元 |

股票池来自数据源的**当前上市列表**；具体数据区间看 `/api/db/meta` 的 `coverage`。

## 查询接口 `/api/db/*`

只读，无鉴权，返回 JSON（可 `format=csv` 下载）：

| 接口 | 用途 |
| --- | --- |
| `GET /api/db` | 接口清单、库规模 |
| `GET /api/db/health`、`/api/db/meta` | 健康检查、表结构、索引、最后同步时间 |
| `GET /api/db/dates` | 交易日列表 |
| `GET /api/db/stocks` | 列表 / 搜索 / 板块 / 剔除 ST / 排序 / 分页（`q, board, exclude_st, synced, sort, order, limit, offset`） |
| `GET /api/db/stocks/{code}` | 单只详情（`000001`、`000001.SZ` 都行） |
| `GET /api/db/bars/{code}` | K 线（`start, end, limit, anchor=last\|first, order, fields, format`） |
| `GET /api/db/bars?codes=a,b` | 多只一次取（≤20） |
| `GET /api/db/snapshot` | 某交易日全市场截面，含 `pct_change`、`amplitude` |
| `GET /api/db/rank` | 单日榜 / 区间榜（成交额、涨跌幅、振幅、波动率…） |
| `GET /api/db/stats/{code}` | 区间统计：涨跌幅、振幅、波动率、累计成交、均线及斜率 |
| `GET\|POST /api/db/sql` | 只读 SQL 直查（仅 SELECT/WITH，默认上限 5000 行、20 秒超时） |

常用参数速记：`board=sh|sz|bj|kcb|cyb|main`（可逗号多选）、`exclude_st=1`、`limit`、`offset`；`format=csv` 会带 BOM 下载。

```bash
BASE=http://127.0.0.1:8765/api/db
curl "$BASE/stocks?q=平安&exclude_st=1&limit=5"
curl "$BASE/bars/000001?start=2025-09-11&limit=12000&fields=date,close&format=csv"
curl "$BASE/rank?date=2026-09-11&by=pct_change&exclude_st=1&limit=20"
curl -G "$BASE/sql" --data-urlencode "sql=select date, count(*) from bars group by date order by date desc limit 5"
```

## 任务接口（POST，计算类）

```jsonc
// 选股：按买入表达式在全市场找最近的买点
POST /api/screen
{"expr":"CROSS(MA(CLOSE,5),MA(CLOSE,20))","window":60,"minHits":1,"limit":80,"warmup":260}

// 全市场回测扫描（口径见 backtest.md）
POST /api/backtest/scan
{"buy":{"conditions":[{"expr":"..."}]},"sell":{"conditions":[...]},"settings":{...},
 "days":242,"warmup":250,"excludeST":true,"sample":0,"codes":["000001"]}

// 单只回测明细：权益曲线、买卖点、指标线、信号处指标值
POST /api/backtest/detail
{"code":"000001","buy":{...},"sell":{...},"settings":{...},"days":242,
 "overlays":[{"expr":"RSI(CLOSE,14)","title":"RSI14"}],
 "events":["RSI(CLOSE,14)","MA(VOLUME,5)"]}

// 事件窗口统计（口径见 statistics.md）
POST /api/feature/extract
{"condition":"...","before":5,"after":10,"sample":300,"periods":[1,3,5,10]}
```

注意：`/api/screen` 用的字段名是 `expr`（直接收表达式）；`/api/backtest/scan` 用的剔除 ST 开关是 **`excludeST`**（camelCase），跟 `/api/db` 的 `exclude_st` 不一样。浮盈/浮亏类条件依赖持仓成本，`/api/screen` 会直接拒绝，只能用于回测。

## 脚本

```bash
SKILL="C:\Users\35788\.codex\skills\quantlab-stock-analysis"   # 本技能目录

# 在真实行情上验证一条表达式（最常用的自检手段）
python "$SKILL/scripts/qlab.py" expr "MA(HIGH,3)" --code 000001 --tail 5

# 事件后收益分布
python "$SKILL/scripts/qlab.py" events "CROSSDOWN(EMA(CLOSE,3),MA(CLOSE,30)-2*STD(CLOSE,30))" --periods 1,3,5,10

# 数据源自检（项目自带）
python "C:\Users\35788\Desktop\量化工具\market_api.py" --check
```

本 skill 自带 `scripts/qlab.py`（下面 `expressions.md`、`statistics.md` 里出现的命令都用它），它复用项目里的 `expr.py` / `feature.py`，不会另起一套语义。参数 `--project` 指定项目目录，`--db` 可直接指定 `market.db`。

## 更新数据

行情靠主站「买点筛查」页的同步按钮从数据源逐只拉取（受平台限速约束），写进 `market.db`。`/api/db/*` 是只读的，不会也不应该用来写数据。
