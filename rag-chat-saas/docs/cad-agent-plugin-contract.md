# CAD Agent 插件集成契约 v1

更新时间：2026-10-03。仓库：`F:/my_projects/rag-chat-saas`。

## 实施状态

恢复联调中：SaaS 前后端 healthy，入口 `http://127.0.0.1:18100`。插件已部署，使用服务令牌 GET `/api/service/v1/capabilities` 实际返回 200 和四个 CAD 工具。
CAD adapter 的 base_url 为 `http://127.0.0.1:18100/api/service/v1`；已生成本地服务令牌文件 `F:/my_projects/rag-chat-saas/.local/integrations/cad-service.token`（不展示值）。
当前项目 allowlist：`04b16a9b-f69a-4ab2-b026-de4108ee1617`、`0ffc48b7-4de6-4fe4-b723-dbc98abfa8c7`。CAD 回调令牌只读挂载 `F:/tmp/cad-agent-tool.token`。
配置文件：`F:/my_projects/rag-chat-saas/.local/integrations/service-plugins.local.json`；Compose override：同目录 `compose.local.json`。修改 allowlist 后仅重载 SaaS 后端。令牌由文件直接读取（tokenFile），没有写入命令行或消息。
数据库迁移到 `a1e345c67894`，备份 `/data/rag-chat.before-cad-20261003.db`。SaaS 容器已到达 `host.docker.internal:5011`，匿名 401；OCR 鉴权及实际任务还在联调。未重启 Docker Desktop，没有创建网络。
最新配置：四个 CAD 工具回调已统一改为 `http://host.docker.internal:8765/api/cad/analysis/tools`。SaaS 容器携带原只读挂载令牌已实际取得主端四个工具；最后一轮后端重载完成且 healthy，鉴权、即时知识装载/更新/检索/卸载/快照无收费复验通过。主CAD现在可以进行13号定向提案验证。
CAD 带图提交 `/runs` 的 503 已修复并部署：带图请求自动挂载服务已授权的 ocr_analyze，复用 5011 视觉服务；不需要向 SaaS 复制 OCR 供应商凭据。
**真实 AI + OCR + 即时知识联调已通过**：run `23f48108-ce11-4ef1-91ed-58b76654ba37` 为 COMPLETED，446 条持久事件；模型调用 session_recall 和 ocr_analyze，实际识别合成卡片文字 THICKNESS 12 mm，含两个模型建议区域；SSE 回放和 Last-Event-ID 续读通过。未将合成测试结果提交 CAD 工程提案。临时测试空间及快照已删除，运行审计保留24小时。
主项目 `0ffc48b7-4de6-4fe4-b723-dbc98abfa8c7` 已加入 allowlist。真实图纸提案往返待主端8765定向重试验收；测试端8767不再是最终回调目标。
既有：供应商 OpenAI-compatible 流、LangGraph、RAG consumer、后台聊天任务、审计。
本轮：独立 `backend/app/plugins/`，核心仅应用挂载、Agent 可选执行环境与图片消息接缝。CAD 不出现在普通用户工具列表。

## 身份与配置

服务入口 `/api/service/v1`，只接受 `Authorization: Bearer <service-token>`，不接受浏览器 Cookie 身份。
使用环境变量 `SERVICE_PLUGINS_CONFIG` 指向服务端 JSON 配置文件；空配置默认关闭入口。文件不入 Git。

```json
{
  "services": [{
    "id": "cad-workbench", "tokenSha256": "<SHA256-of-service-token>",
    "tenantId": "company", "projectIds": ["project-a"],
    "tools": ["cad_get_evidence", "cad_propose_parts", "cad_calculate_weight"],
    "accountIds": [], "maxActiveRuns": 2
  }],
  "httpTools": [{
    "name": "cad_get_evidence", "version": "1", "description": "读取当前图纸的证据包",
    "url": "http://host.docker.internal:19000/api/tools/execute",
    "tokenEnv": "CAD_TOOL_TOKEN", "effect": "read",
    "inputSchema": {"type":"object","properties":{},"additionalProperties":false},
    "outputSchema": {"type":"object"}
  }],
  "visionAccountIds": []
}
```

空 `accountIds` 使用现有活跃账号池；视觉输入必须使用显式 `visionAccountIds`，不按模型名字猜测视觉能力。
`tenantId/serviceId` 来自凭据配置；`project_id` 必须在 allowlist 中。CAD 服务代表已鉴权用户提交 `drawing_id/revision`，宿主绑定空间与运行，不允许模型改写。CAD 服务也必须在其工具入口验证该上下文对应真实图纸版本；宿主不替 CAD 判定图纸归属。
不得互相 import 对方项目内部模块。HTTP 地址只来自服务器配置，不接受模型提供任意 URL。

## 工具注册与执行

`GET /api/service/v1/capabilities` 返回该身份获准能力与版本。
`POST /api/service/v1/tools/execute`：

```json
{"contractVersion":"1","context":{"project_id":"project-a","drawing_id":"d1","revision":"r1"},"tool":"cad_get_evidence","arguments":{}}
```

宿主向已配置 HTTP 工具 POST：

```json
{"contractVersion":"1","requestId":"UUID","context":{"service_id":"cad-workbench","tenant_id":"company","project_id":"project-a","drawing_id":"d1","revision":"r1"},"tool":"cad_get_evidence","arguments":{}}
```

工具返回 `{"contractVersion":"1","status":"succeeded","data":{},"sources":[],"artifacts":[],"warnings":[]}`；失败返回 `status:"failed",error:{code,message,retryable}`。宿主校验 schema、响应大小、超时与权限，审计仅记录标识、状态、耗时，不记录图片或凭据。
Agent 允许 `read/propose/compute`；`write` 只能显式服务调用，不由模型自动执行。重试非幂等工具前需 CAD 端处理 `requestId`。

## 即时知识空间

`POST /api/service/v1/spaces`：`{"context":{...},"ttlSeconds":3600}` → `{id,context,expiresAt,kind:"temporary"}`。
空间同时隔离 service、tenant、project、drawing、revision。默认 1 小时、最长 24 小时，后台清理；没有自动转长期库。

`PUT /spaces/{id}/documents/{documentId}` 幂等替换：

```json
{"title":"图纸说明","revision":"r1","chunks":[{"id":"c1","text":"钢板厚度 12 mm","source":{"documentId":"d1","revision":"r1","page":1,"coordinateSpace":"image-pixels","bbox":[10,20,100,40],"imageWidth":1600,"imageHeight":1200}}]}
```

每文档最多 1000 块，每块最多 12000 字；保留调用方分块与 source 原样，不自行 OCR。`DELETE /spaces/{id}/documents/{documentId}` 卸载，`DELETE /spaces/{id}` 销毁。
`POST /spaces/{id}/search`：`{"question":"厚度","topK":8,"documentIds":[]}`。
v1 临时检索为明确标识的本地 lexical 召回（中文字符二元组/英文词，非向量、不虚报重排），返回完整命中片段和 source；长期 RAG 可由独立工具适配器接入。

Agent 空间工具：`session_list_documents/session_load_document/session_unload_document/session_recall`，固定当前 space；装载只能取当前服务获准的 CAD 证据工具结果，不接收任意 URL。
`POST /spaces/{id}/promote`：`{"name":"审核后资料","requestId":"UUID"}`，显式快照到插件持久集合并返回新空间 ID；原临时空间不变。`GET /spaces/{id}/package` 导出版本化 JSON 包（含来源、版本、坐标）。该包不是既有 RAG ZIP 格式，不能冒充已发布进 RAG 控制台；转既有 RAG 库由发布适配器完成，本轮文档会如实列出联调结果。

## CAD 分析运行与 SSE

`POST /api/service/v1/runs`：

```json
{"contractVersion":"1","requestId":"UUID","context":{"project_id":"project-a","drawing_id":"d1","revision":"r1"},"spaceId":"UUID","question":"检查材料、尺寸并生成待审提案","tools":["cad_get_evidence","cad_propose_parts","cad_calculate_weight"],"images":[],"reasoningEnabled":false}
```

`images` 支持 `{mediaType:"image/png",data:"<base64>"}`，最多 4 张，每张 5MB；不支持任意外链下载。
返回 HTTP 202，`{id,status,eventsUrl}`。相同 requestId+相同请求幂等返回；参数不同返回 409。
`GET /runs/{id}` 查看快照；`POST /runs/{id}/cancel` 取消；`GET /runs/{id}/events?after=0` 订阅。
SSE 支持 `Last-Event-ID`/after 重放，事件包含 id；事件类型 `progress/model/delta/reasoning/tool_result/complete/error`；progress 含 stage、operationId、status、elapsedMs。断开连接不取消任务。取消为协作式，等待中的外部请求可能直到超时才结束。重启后中断任务标失败，不静默重跑已执行工具。
结果为提案，CAD 审核表接受后再确定性计算；服务不直接覆盖审核数据。

## 图片消息（独立普通用户能力）

管理员开关 `/api/v1/admin/settings/images`；默认关闭。图片消息通过独立用户上传接口绑定 owner，聊天只能引用自己的图片；普通用户不获得上述服务接口或 CAD 工具。
OCR 视觉插件由 OCR 线程负责，这里只实现 HTTP 适配器，不修改 OCR 源码或读取其凭据。

### 已实现的 OCR 接入

`visionPlugin: {url, tokenFile}` 指向独立 OCR HTTP 服务。当前容器 URL 是 `http://host.docker.internal:5011/api/plugins/vision/v1`，令牌从 `/run/ocr/service.token` 只读挂载读取，宿主原文件为 `F:/my_projects/2026-8-3_mingli/tools/ocr/data/vision_plugin/service.token`。不读取 OCR 模型供应商密钥。
CAD 服务允许的 `ocr_analyze` 为 `transport: "ocr-vision-v1"`，参数 `imageIndices`（0 起、最多4张）和 `question`。只能查看本次 run 已提交的图片，不接受模型构造 URL/文件路径。带图 run 自动加入服务已授权的 OCR 工具；无授权且未选视觉账号仍拒绝。直接 `/tools/execute` 不接受该工具，须通过绑定上下文的 run 调用。
普通图片消息 admin 设置增加 `backend: "model" | "ocr"`，默认仍关闭。OCR 模式不要求重复配置视觉模型账号；图片描述按用户所有权缓存，后续对话复用，不重复计费识别。前端显示“正在查看图片内容”进度，失败返回可重试错误，不开放 CAD 工具。
OCR 结果中的区域是模型建议矩形，字段未经过工程审核。插件只转发 OCR 已校验结果，不把置信度当作准确率，不将临时快照当作已发布知识库。

### 本轮验收记录

- 2026-10-03：本地服务鉴权、CAD 跨容器工具目录、OCR 跨容器鉴权（configured=true）、即时知识 CRUD/更新/检索/来源坐标/快照导出均实测通过。
- 真实模型调用任务 `23f48108-ce11-4ef1-91ed-58b76654ba37`：COMPLETED，session_recall + ocr_analyze，合成卡片识别，446条事件，SSE回放/续读通过；记录 `.local/integrations/verification.local.json`。
- 普通用户图片开关在实际数据库中仍为 false；未为了测试改变现有用户权限。
- 前端全量 87/87 通过，构建成功。后端完整回归最初82通过、1条旧线程数断言失败；该断言与单进程并发语义无关，修正后部署/插件专项通过。新增测试覆盖带图OCR回退、令牌文件、浏览器拒绝、取消清理、来源大小、并发限流、OCR固定来源/取消/缓存所有权。
- 迁移版本 `b2f456d78905` 已应用；数据库备份 `/data/rag-chat.before-cad-20261003.db`。没有重启Docker Desktop或创建新网络。
- 真实CAD run `1619f4ab-a894-43fa-bcb7-cd4f281b3260` 自然完成，四次证据/资料调用成功，但未调用 cad_propose_parts，因此提案闭环没有通过。正文29911字、9374条delta、9564条usage；没有reasoning事件，审计reasoningEnabled=false，所用模型为 SiliconFlow DeepSeek-V4-Flash，不能称为客户端把reasoning_content拼入正文。
- 后续修复：CAD中文简洁提示词、需要提案时直接调用工具（不把正文JSON当已提交）、每次建议不超过5个候选、最终800字以内；服务模型每次最大4096输出token，length截断报OUTPUT_LIMIT而非成功；累计usage仅每次模型调用完成后发一条。不会自动重发上次收费请求。最后定向真实提案测试由主CAD任务发起。
- 上述修复已部署；最终模型流/插件/Agent/聊天回归31项通过，前端87项通过，图片权限/缓存及部署专项通过。真实供应商是否遵守新提示词仍须下一次定向调用验证，不能由单元测试替代。
- 待主CAD任务验收：真实图纸UI→提案→人工审核往返；本轮没有执行工程参数修改或冒充上述验收已完成。

## 实施与验证顺序

1. `plugins/security.py, registry.py, api.py`：服务拒绝浏览器身份、项目隔离、JSON schema 与有限 HTTP 调用测试。
2. `plugins/models.py, knowledge.py`：空间 CRUD、中文召回、替换卸载、过期和显式持久快照测试。
3. `plugins/runs.py` + Agent 可选 runtime：持久任务、幂等、取消、SSE 重放、固定上下文、工具调用审计测试。
4. `plugins/images.py` + 消息/表单接缝：图片鉴权、大小/格式、管理员关闭、视觉账号过滤、历史显示测试。
5. 联调 OCR HTTP 插件、迁移和构建；在本节更新真实进展。保留已有工作，不批量提交或重置。
