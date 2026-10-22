# Service Hub 接入验收

结论：**接入完成**。按统一准则的混合应用方案拆成主应用与原生依赖两条登记；两者均可在正式 Electron 页面启停，不代表管理器支持跨两条登记的自动依赖编排。

检查日期：2026-10-14，Asia/Shanghai。依据：`F:\my_projects\collabflow\service-hub\接入准则.md` v1.0。

## 登记和控制范围

| 项目 | 主应用 | 必要依赖 |
| --- | --- | --- |
| ID | `stock-analysis` | `stock-analysis-market-relay` |
| 名称 | 股票分析智能体 | 股票分析 · 市场中继 |
| 方式 | 已部署 Docker 容器 | 原生前台 Python 进程及其子进程 |
| Manifest | `F:\my_projects\stock_analizer\service-hub.app.json` | `F:\my_projects\stock_analizer\service-hub.market-relay.app.json` |
| 入口 | http://127.0.0.1:18110 | 无独立网页，`url` 留空，不用 API 冒充前端 |
| 健康检查 | http://127.0.0.1:18110/api/v1/health | http://127.0.0.1:18766/health |
| 控制对象 | Compose 项目标签精确值 `stock-analysis` | 项目虚拟环境 `stock-data-engine\.venv\Scripts\python.exe -u scripts\market-relay.py --port 18766` |

主应用的必要组件均已存在，已核实各容器的 `com.docker.compose.project=stock-analysis`：

- `stock-analysis-frontend-1`
- `stock-analysis-backend-1`
- `stock-analysis-core-1`
- `stock-analysis-data-engine-1`

三个持久卷分别为 `stock-analysis-chat-data`、`stock-analysis-core-data`、`stock-analysis-engine-data`，没有共享给其他 Compose 项目。Core 管理入口为 http://127.0.0.1:18210/admin。

原生依赖的可执行文件和工作目录均为存在的绝对路径；登记不含凭据，启动时从项目自己的 `engine.token` 文件读取。进程保持前台，不打开浏览器、不安装或构建、不要求输入、不派生后台服务后退出。监听端口被其他进程占用时绑定失败，不按端口杀进程或接管外部实例。

## 端口冲突修复

修复前，运行中的数据引擎确实使用 `http://host.docker.internal:18765/api/db`，而 18765 已被 Service Hub 占用。Windows 主机访问市场接口成功，容器直连 `192.168.3.5:8765` 超时，故保留必要的主机中继。

- 中继默认端口改为 18766；显式要求使用 18765 时拒绝启动。
- `.stock-private/stock.env` 的实际市场 URL 改为 `http://host.docker.internal:18766/api/db`，保留其余配置及凭据。
- `scripts/start-stock.ps1` 同步修改端口；检查中继身份和市场就绪状态，不再自行隐藏启动中继。该脚本仍是手动初始化/部署入口，不作为管理器每次启动命令。
- 中继新增 `/health`，真实检查远端市场接口，只返回服务身份与 UP/DOWN；市场数据路由继续要求认证及路径白名单。
- 使用已有镜像，仅重建所需容器配置；未构建镜像、删除容器数据卷或执行全局 Docker 清理。

## 正式 Electron 验收

正式程序：`F:\my_projects\collabflow\service-hub\release\win-unpacked\Service Hub.exe`。

`GET /api/identity` 返回 `service=service-hub`、`version=2`、`registryPath=C:\Users\22283\.service-hub\apps.json`。接入前后均检查身份，只通过 API 更新本应用及新增同组依赖。已有名称、收藏、颜色及标签保持不变。两条 ID 各只有一条登记，登记字段与各自 manifest 语义一致；原生参数逐项一致。

通过 `scripts/service-hub-desktop.ps1` 调用 Windows UI Automation，实际操作正式 Electron 窗口的按钮；启停操作不是直接调用管理 API 冒充桌面验收。API 只用于登记、读取状态和验证操作结果。

| 检查 | 实测结果和证据 |
| --- | --- |
| 依赖启动 | Electron 启动中继成功，`/health` 200，身份 `stock-market-relay`、状态 UP |
| 主应用停止 | Electron 停止成功，四个股票容器全部 exited，前端连接拒绝；中继仍 UP，说明控制范围独立 |
| 依赖停止 | Electron 停止成功，`nativeProcess.running=false`，18766 无监听，相关中继进程数量为 0 |
| 依赖再次启动及重启 | 均成功，重启前后 PID 从 32220 变为 23620，健康检查恢复 200 |
| 主应用从停止恢复 | Electron 启动成功，四个原有容器恢复，Core、后端、引擎 healthy；未假设管理器执行 compose 依赖编排 |
| 主应用重启 | Electron 重启成功，四个容器 StartedAt 均更新；最终分别为 2026-10-14T15:36:41Z 至 15:36:46Z，健康检查恢复 |
| 打开入口 | Electron 点击“打开应用”成功；浏览器验证到真实 `/login` 页面，HTTP 200，前端资产正常，页面异常 0 |
| 日志 | Electron 应用详情实际点击“日志”，核实渲染后端启动日志及中继的 `Stock market relay listening` 启动信息 |
| 托盘常驻和重开 | 关闭 Electron 窗口后管理 API、主应用及中继仍可用；重新运行正式 exe 恢复窗口，身份和固定配置目录不变，中继 PID 仍为 23620 |
| 真实依赖就绪 | 后端认证访问 Core `/health` 成功；通过引擎 HTTP 工具执行 `stock_health` 返回 succeeded，市场 ok=true、stocks=5227、last_date=2026-10-12 |
| 数据保留 | 前后均为 3 用户、35 对话、94 消息；Core 1 条 run、20 条事件；持久卷和凭据保留 |
| 其他应用 | 没有对其他项目发出生命周期或登记修改操作。125 个外部容器快照中仅 OCR 自身处于持续 restarting 的容器启动时间变化，其余一致 |

截图保存在 `F:\my_projects\stock_analizer\artifacts\verification\service-hub`。本次仅运行接入相关检查：中继 3 项测试通过、PowerShell 语法检查通过、正式桌面操作及真实依赖探测通过；没有进行付费模型调用或全仓测试。

## 操作边界和任务恢复

启动顺序：在 Service Hub 先启动“股票分析 · 市场中继”，再启动“股票分析智能体”。停止顺序相反。只操作主应用按钮不会启停中继；原生登记没有混填 `projects`。

验收启停时 Core 活动任务为 0；最终 SaaS `chat_runs` 与 `audit_records` 活动任务也为 0，消息及事件数量未变化。桌面验收脚本对后续主应用停止/重启增加了 Core 和 SaaS 活动任务检查。

市场中继为只读 HTTP 转发，无业务数据库写入或后台队列；Windows 强制终止后可以重新启动，已验证进程树全部退出。主应用数据库使用持久卷。代码中 Core 重启将中断的 RUNNING 任务标为 `WORKER_RESTARTED` 失败，避免自动重复付费调用；SaaS 有中断任务恢复记录逻辑。未创建或强杀真实付费任务来测试恢复。

管理器尚无跨原生/Docker 条目的自动编排，也不会自动排空分析任务。业务分析进行中应等待其完成后再停止；主应用普通 `/health` 是进程健康检查，不能单独证明市场数据可用，必须同时看中继就绪状态。本次额外通过真实 `stock_health` 工具验证了整条数据链路。

最终保留四个股票容器和受管理中继运行。没有修改 Service Hub 源码或打包文件，没有启动替代管理器后端。
