# 当前知识库工具问答

SaaS 使用 LangGraph 1.0.10 编排模型与工具循环，保留现有 OpenAI 兼容供应商适配、账户并发池、SSE、引用持久化与原文阅读器。RAG 不运行 Agent，不保存模型提示词。

## 工具

- `list_documents(offset=0, limit=100)`：分页读取当前发布版本的文档目录；`hasMore` 表示仍有后续内容。
- `recall(question, documentIds=[], topK=8)`：当前知识库检索，可指定最多 50 个文档。文档归属和发布版本由 RAG 校验，范围条件在召回前应用；不跨库。
- `current_time()`：SaaS 服务端时间，ISO 8601、UTC+08:00、星期序号。

模型自主选择工具。系统提示词要求专业知识、文件、标准、条款和数值判断必须先进行本轮检索；问候、闲聊和纯文字润色无需检索。工具调用是模型决策，提示词不是对所有模型行为的形式化保证。

单轮最多 6 轮工具执行、12 次调用。未知工具及非法参数返回可恢复错误。工具输出按数据处理，不能修改系统指令。多个召回的引用连续编号并保存各自 queryId。模型流中断后保留已收到内容，不拼接其他账户的回答。

## RAG 业务执行接口

`POST /api/v1/consumer/knowledge-bases/{knowledgeBaseId}/tools/execute`

```json
{"operation":"list_documents","arguments":{"offset":0,"limit":100}}
```

```json
{"operation":"recall","arguments":{"question":"设计压力要求","topK":8,"mode":"hybrid","documentIds":["文档UUID"]}}
```

沿用 consumer Bearer key、知识库范围授权、发布版本绑定、限流和并发限制。原 `/retrieve` 与 `/retrieve/stream` 同时支持可选 `documentIds`；SaaS 使用流式路径接收检索过程。目录仅包含当前可检索发布版本的文档，未入库或未发布文件不会混入。

验收问题：`你好`（不检索）；`现在北京时间是多少`（时间工具）；`列出当前库全部文档`（目录分页）；`只在《某文件》中查找适用范围`（目录→限定召回）；`比较两份文件的设计压力要求`（限定多个文件→带来源回答）。
