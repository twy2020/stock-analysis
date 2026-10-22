# 股票分析智能体

通过自然语言设计股票查询规则、指标、筛选条件与研究方案，由数据引擎执行查询和统计，再由 AI 解读有来源的结果。包含 Vue 对话界面、SaaS 后端、独立 Agent Core 和股票数据引擎。

本系统用于研究辅助。行情为未复权日线，回测采用简化成交约束，历史表现不代表未来收益。

## 两个私有仓库

| 仓库 | 职责 |
| --- | --- |
| [stock-analysis](https://github.com/twy2020/stock-analysis) | 对话 SaaS、图表与表格、数据引擎、部署脚本和研究资料 |
| [stock-agent-core](https://github.com/twy2020/stock-agent-core) | 模型调用、Agent 执行、Tools/MCP/Skills、供应商及应用授权管理 |

主仓库将 Core 固定为 `agent-core/` 子模块，需要同时具有两个仓库的读取权限。

```powershell
git clone --recurse-submodules https://github.com/twy2020/stock-analysis.git
cd stock-analysis
# 已克隆但没有 Core 时：
git submodule update --init --recursive
```

## 能力与架构

- AI 编写声明式查询 schema，按股票池、时间窗、条件和字段投影取数，不把行情整库送进模型。
- 数据引擎负责指标、筛选、描述统计、事件研究、比较和探索性回测。布林带可以使用 `MA(CLOSE,20) +/- 2*STD(CLOSE,20)`。
- 工具只返回受限摘要、少量预览及不可变 `datasetRef`；大表、图表通过经过权限检查的独立接口加载。
- 前端支持 K 线、成交量、指标曲线、表格、分组图表目录、全屏分析、数据引用、标注、PNG/CSV 导出及日夜主题。
- 联网研究由管理员开放、用户每轮选择。搜索聚合、网页浏览及引用效果依赖已配置服务的真实能力、额度和网络。
- RAG 默认关闭；后续联动时应使用股票系统独立的知识空间，并分别配置 SaaS 和 Core 权限。

```text
浏览器 :18110 -> Vue / Nginx -> SaaS 后端 -> Agent Core :18210 -> 模型供应商
                                              -> 数据引擎 :18310 -> 市场数据库 API
                                              -> SaaS 联网适配器（按权限启用）
```

Compose 项目名为 `stock-analysis`，包含 `frontend`、`backend`、`core`、`data-engine` 四个容器。数据库和研究产物使用独立命名卷。

`quantlab-stock-analysis/` 是参考方法和踩坑资料，`stock_predict/` 是独立预测模型研究代码，不是在线 Agent 的必需服务；数据集和训练权重不随仓库发布。

## 首次部署

需要 Git、Docker Compose v2 和 Python 3.12。以下为 Windows PowerShell 示例，先启动 Docker Desktop。

```powershell
py -3.12 -m venv agent-core/.venv
./agent-core/.venv/Scripts/python.exe -m pip install -r agent-core/requirements.txt -r stock-data-engine/requirements.txt
./agent-core/.venv/Scripts/python.exe scripts/bootstrap_stock.py
./agent-core/.venv/Scripts/python.exe scripts/configure_stock_web.py
```

脚本在 `.stock-private/` 生成本机配置和凭据，不覆盖已有股票配置。新机器没有模型配置时会生成占位模型，稍后需要在 Core 控制台设置真实供应商和 API Key。

编辑 `.stock-private/stock.env`，设置真实 `MARKET_API_URL` 和端口。默认 `http://192.168.3.5:8765/api/db` 是原开发环境地址，其他机器必须修改；使用市场接口 `/health` 验证可用性。接口契约见 [数据库查询接口](数据库查询接口(1).md)。

```powershell
docker compose --env-file .stock-private/stock.env up -d --build
docker compose --env-file .stock-private/stock.env ps
```

也可运行 `./scripts/start-stock.ps1` 完成配置检查和构建部署；它是初始化入口，不是 Service Hub 日常启动命令。

## 登录与模型配置

| 页面 | 默认入口 | 首次登录 |
| --- | --- | --- |
| 股票对话 | http://127.0.0.1:18110/ | 查看本机 `.stock-private/initial-login.txt`，登录后改密 |
| Core 管理 | http://127.0.0.1:18210/admin | `admin / admin123`，首次登录强制改密 |

Core 管理使用账密和会话，旧管理员令牌不能代替登录；修改后的管理员密码保存在 Core 数据库中。

在 Core 控制台维护供应商 → 账号 → API Key，再创建模型。Base URL 必须为供应商实际的 OpenAI-compatible API 前缀，不能填网站首页。保存后分别测试文本和工具调用，为股票应用选择允许模型及默认模型。

供应商可配置 HTTP(S) 代理。Docker 访问本机代理使用 `host.docker.internal`，不能填容器自己的 `127.0.0.1`。联网服务还需在 SaaS 管理页开放并配置，Core 中也须存在相应工具授权。

## 可选市场中继与 Service Hub

如果主机能访问市场服务而容器因路由重叠不能访问，可启用认证主机中继。

```powershell
py -3.12 -m venv stock-data-engine/.venv
./stock-data-engine/.venv/Scripts/python.exe -m pip install -r stock-data-engine/requirements.txt
./stock-data-engine/.venv/Scripts/python.exe -u scripts/market-relay.py --port 18766
```

中继保持前台运行，默认上游 `http://192.168.3.5:8765`，可通过 `--upstream` 修改；就绪检查为 `http://127.0.0.1:18766/health`。启用时在 `.stock-private/stock.env` 设置：

```dotenv
MARKET_API_URL=http://host.docker.internal:18766/api/db
MARKET_API_TOKEN_FILE=/run/stock/engine.token
```

创建 `.stock-private/market-relay.enabled` 可让部署脚本检查中继。**18765 专供 Service Hub**，中继拒绝占用。

登记模板是 `service-hub.app.json` 和 `service-hub.market-relay.app.json`，绝对路径须按新机器实际目录修改。主应用控制四个容器，中继是独立原生依赖；启动先中继后主应用，停止顺序相反。管理器不负责首次构建或两条登记的自动编排。详见 [接入验收](service-hub.acceptance.md)。

## 查询契约与研究口径

工具包括 `stock_schema`、`stock_health`、`stock_query`、`stock_events`、`stock_backtest`、`stock_dataset`、`stock_annotate`、`stock_sql`，经认证 HTTP 或 MCP 暴露。先读取 `stock_schema`，再用当前真实字段构造规则，例如：

```json
{
  "task": "screen",
  "universe": {"codes": ["000001", "600519"]},
  "window": {"bars": 300, "warmup": 260},
  "condition": "CROSS(MA(CLOSE,5),MA(CLOSE,20))",
  "output": {"fields": ["code", "date", "close"], "previewRows": 5}
}
```

全部计算交给数据引擎，AI 只解读分析结果。价格单位为元、成交量为手，普通收益为小数，`PCTCHANGE` 为百分数。结论须保留样本量、日期、未复权、缺失值、停牌及查询上限等限制。多股票独立账户回测不等于组合回测。

详细信息见 [能力审计](docs/stock-capability-audit.md)、[研究契约参考](docs/stock-research-reference.md) 和 `stock-data-engine/tests/`。历史参考中的启动路径和端口以本 README 为准。

## 开发检查

```powershell
./stock-data-engine/.venv/Scripts/python.exe -m unittest discover -s stock-data-engine/tests -v
./agent-core/.venv/Scripts/python.exe -m unittest discover -s agent-core/tests -v
# 在 SaaS 后端的虚拟环境中：
cd rag-chat-saas/backend
python -m pip install -e ".[test]"
python -m pytest
# Vue 前端：
cd ../frontend
npm ci
npm test
npm run build
```

常规测试使用模拟模型和固定数据。真实对话验证可能产生模型费用，需显式开启。升级 Core 时应在主仓库提交新的子模块版本，不要让线上服务自动跟踪未验收分支。

## 密钥与数据管理

仓库包含当前源代码、依赖清单、配置模板和文档，不包含生产 API Key、`.env`、`.stock-private/`、Core `.local/`、数据库、会话、日志、行情数据、训练权重、验证截图及旧 Git 历史。

在自己的环境生成凭据，不在代码、Compose 明文、README 或 Issue 中填写密钥。备份须单独保护 `.stock-private/` 和三个数据卷；只备份 Git 不包含用户数据。丢失加密主密钥可能使已有加密配置无法恢复。
