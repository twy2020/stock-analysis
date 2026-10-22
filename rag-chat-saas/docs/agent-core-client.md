# Chat SaaS 接入独立 Agent Core

SaaS 保留用户、组织、会话、消息、图片归属与引用阅读；Core 执行模型和工具循环。启用 Core 后，SaaS 无需配置本地模型账号。Core 与业务数据库独立，OCR 视觉模型继续由 OCR 插件管理。

## 服务端配置

```text
AGENT_BACKEND=core
AGENT_CORE_URL=http://host.docker.internal:18700
AGENT_CORE_TOKEN_FILE=/run/integrations/agent-core-service.token
AGENT_CORE_MODEL_PROFILE=primary
AGENT_CORE_CALLBACK_TOKEN_SHA256=<专用回调令牌的 SHA256>
```

Core caller 配置的 tenantId 必须对应 SaaS 组织 ID，domains 含 chat，modelProfiles 含 primary，tools 可授权 ocr_analyze。ragCallback 固定指向本 SaaS `/api/internal/agent-core/rag`，使用独立回调令牌。模型不能覆盖地址、凭据、用户、会话或知识库。

现有本机迁移配置是 `.local/integrations/compose.core.local.json`：

```powershell
docker compose -f compose.yaml -f .local/integrations/compose.core.local.json up -d --build backend frontend
```

`scripts/bootstrap_agent_core.py` 可从现有服务器配置一次性迁移通用模型到 Core 私有文件。它不打印密钥、不重启服务，且拒绝覆盖已有 Core 配置。OCR 模型密钥不迁移。不要提交 `.local` 文件。

## 运行与失败语义

- ChatRun/message ID 作为 Core request_id；创建成功后的 core_run 事件和 coreRunId 随消息保存。
- SSE 断线带 Last-Event-ID 重新连接同一任务，过滤已消费事件，不重新提交模型任务。
- 用户取消、生成器关闭和 SaaS 重启恢复均向所属 Core 任务传播取消。
- 无法确认取消时保留本地失败状态并记录日志；可对 FAILED/CANCELLED 任务再次请求取消。不保证已经发给模型供应商的请求停止计费。
- Core 出错时本地不会再执行 Agent、直连视觉模型或自动重做收费请求。
- legacy `AGENT_BACKEND=local` 仅供旧部署显式兼容；当前集成部署启用 core。两者不是故障转移关系。

## 图片与检索

管理员保留图片消息开关。Core 模式的图片能力由 Core 获准的 OCR 插件决定，无需在 SaaS 再选视觉账号。SaaS 验证图片归属，Core 通过 OCR 分析，通用推理模型收到识读结果；不把未经查看的图片当成已知内容。

RAG 回调校验用户仍有效、会话归属、组织和绑定知识库，然后调用既有 RagClient API。Core 累计本轮引用编号，SaaS 保留 queryId/citationId、原文和页码，并验证最终回答中的引用编号。

## 验证

`backend/tests/test_core_bridge.py` 覆盖无本地模型账号执行、引用与用量持久化、故障不回退、SSE续读、取消、重启恢复、图片归属转换及RAG资源绑定。

```powershell
cd backend
../.venv-integration/Scripts/python.exe -m pytest tests/test_core_bridge.py tests/test_chat.py tests/test_chat_jobs.py tests/test_chat_images.py tests/test_agent.py -q
```
