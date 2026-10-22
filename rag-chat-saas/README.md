# RAG Chat SaaS

面向内部用户的知识库问答服务。后端使用 Flask、SQLAlchemy 和 SQLite，前端使用 Vue 3、TypeScript 与 PDF.js。RAG 检索、证据定位和原文授权由 `rag-service` 的 Consumer API 提供。

## 一键启动

服务器需要 Docker Desktop 或 Docker Engine + Compose v2。在项目根目录执行：

```powershell
.\scripts\start.ps1
```

首次执行会生成忽略版本控制的 `.env`，并在终端显示一次管理员初始密码。打开 `http://127.0.0.1:18100/`，使用账号 `admin` 登录并立即修改初始密码。再次执行脚本不会修改已有密钥、密码或数据。

Linux 服务器执行：

```bash
chmod +x scripts/start.sh scripts/backup.sh
./scripts/start.sh
```

首次启动同样会生成权限为当前用户只读写的 `.env`，并输出一次管理员初始密码。脚本需要系统提供 `openssl`，重复执行不会覆盖现有配置或数据。

Compose 只使用一个明确命名的网络 `rag-chat-saas-net` 和一个数据卷 `rag-chat-saas-data`。网络默认固定使用 `10.252.250.0/24`，避免继续消耗 Docker 默认地址池；如果服务器已有重叠网段，在 `.env` 中修改 `APP_NETWORK_SUBNET`。重复启动会复用同一网络，不会创建随机网络。停止服务使用 `docker compose down`；不要在日常操作中添加 `-v`，否则会删除 SQLite 数据卷。

当前部署模型是单后端容器、单 Gunicorn 进程和八个请求线程。这样模型账号的并发上限对整个容器严格生效，也符合 SQLite 的单实例定位；不要直接横向扩容后端副本。需要多副本时，应先把账号租约和数据库迁移到共享服务。

## 管理配置

首次改密后进入“系统管理”：

- RAG 连接：填写 RAG Consumer API 的根地址与一次性签发的 API Key。
- 模型供应商：支持 SiliconFlow、DeepSeek 及其他 OpenAI 兼容端点；每个账号设置模型、并发上限和调度权重。
- 用户：创建本地用户、分配角色、启用或停用。新用户首次登录必须改密。
- 概览：检查 RAG 与模型账号状态，查看请求量、失败率、Token 与平均耗时。

RAG Key 和模型 Key 使用 `APP_MASTER_KEY` 加密后写入 SQLite，管理接口不会返回明文。更换 `APP_MASTER_KEY` 前必须先完成凭据迁移，否则已有密文无法解密。

## RAG Consumer Key

建议为本服务签发独立 Key，至少包含：

- `knowledge-base:list`
- `retrieval:execute`
- `evidence:read`
- `document:download`

Key 可绑定允许访问的知识库、过期时间、速率和并发限制。SaaS 不传递租户、工作区、Publication 或 IndexBuild ID。

## 数据与备份

SQLite 位于容器数据卷 `/data/rag-chat.db`，启用 WAL、外键和 busy timeout。在线一致性备份：

```powershell
.\scripts\backup.ps1
```

备份文件包含用户、会话、对话、消息、引用、加密配置和统计记录，不包含主密钥；恢复时必须同时保留原 `.env`。生产环境应定期将数据库备份和 `.env` 分别保存到受控位置。

Linux 使用 `./scripts/backup.sh`，也可把目标路径作为第一个参数传入。

恢复备份会短暂停止后端，并在数据卷内保留一份恢复前数据库。恢复脚本不会修改 `.env` 或 `APP_MASTER_KEY`：

```powershell
.\scripts\restore.ps1 -Backup .\backup-rag-chat-20260925-120000.db
```

Linux：

```bash
chmod +x scripts/restore.sh
./scripts/restore.sh ./backup-rag-chat-20260925-120000.db
```

脚本先执行 SQLite 完整性检查，替换数据库后重新启动服务并等待健康检查。备份必须与当前 `.env` 中的 `APP_MASTER_KEY` 配套，否则加密配置无法解密。

## HTTPS

直接通过 HTTPS 发布时，把 `.env` 中的 `SESSION_SECURE` 改为 `true`。如果由外部反向代理终止 TLS，保留 Nginx 到后端的内部 HTTP，并确保代理传递 `X-Forwarded-Proto`。不得公开后端容器端口或 SQLite 数据卷。

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
npm test
npm run build
Set-Location ..
docker compose config --quiet
```

前端开发地址默认为 `http://127.0.0.1:18100`，Vite 会把 `/api` 代理到本地后端 `18101`。容器部署统一通过 Nginx 访问，不直接暴露 Flask。
# Stock Analysis Deployment

This copy now belongs to Stock Lab. Start from `../scripts/start-stock.ps1`;
chat runs on port 18110 and Core on 18210. RAG defaults off. See the root README
for query schemas, data-engine tools, research semantics and isolated Docker resources.
The historical implementation notes below describe the original knowledge-chat system.

