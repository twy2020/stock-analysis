import type { Message } from '../../types'

export function progressLabel(event: NonNullable<Message['processEvents']>[number]): string {
  const count = event.candidateCount == null ? '' : ` ${event.candidateCount} 条`
  const tools: Record<string, string> = { list_documents: '文档目录', recall: '相关内容', current_time: '当前时间' }
  const webTool=(event.tool??'').replace(/^mcp__stock-web__/,'')
  if(webTool==='stock_web_search'||webTool==='stock_web_fetch'){
    const action=webTool==='stock_web_search'?'联网搜索':'网页浏览'
    if(event.stage==='TOOL_FAILED'||event.status==='FAILED'){
      const errors:Record<string,string>={WEB_SEARCH_RATE_LIMITED:'搜索引擎限流',WEB_PROXY_UNAVAILABLE:'代理连接失败',WEB_TIMEOUT:'联网请求超时',WEB_SEARCH_UNAVAILABLE:'搜索引擎不可用',WEB_SOURCE_UNAVAILABLE:'网页来源不可用',WEB_RESEARCH_BUDGET:'已停止重复联网请求',WEB_PROVIDER_COOLDOWN:'搜索服务暂时冷却',WEB_PROVIDER_AUTH_FAILED:'搜索服务认证失败',WEB_SEARCH_NO_SOURCES:'搜索未返回来源',WEB_MCP_SCHEMA_UNSUPPORTED:'搜索工具参数不兼容',WEB_MCP_TOOL_SELECTION_REQUIRED:'搜索工具尚未指定'}
      return errors[event.code??'']??`${action}失败`
    }
    if(event.stage==='TOOL_COMPLETED')return `已完成${action}`
    if(event.stage==='TOOL_EXECUTING')return `正在${action}`
  }
  const stockTools:Record<string,string>={stock_schema:'查询规则',stock_health:'行情覆盖检查',stock_query:'股票分析',stock_events:'事件统计',stock_backtest:'策略回测',stock_dataset:'数据集读取',stock_annotate:'数据标注',stock_sql:'只读查询'}
  const stock=stockTools[(event.tool??'').replace(/^mcp__stock__/,'')]
  if(stock){
    if(event.stage==='TOOL_FAILED'||event.status==='FAILED')return `${stock}未完成`
    if(event.stage==='TOOL_COMPLETED')return `已完成${stock}`
    if(event.stage==='TOOL_EXECUTING')return `正在执行${stock}`
  }
  if (event.stage === 'TOOL_FAILED') return `未能获取${tools[event.tool ?? ''] ?? '所需信息'}`
  if (event.status === 'FAILED') return '此步骤未完成'
  switch (event.stage) {
    case 'QUEUED': return '等待分析'
    case 'TOOL_EXECUTING': return '正在执行工具'
    case 'ANSWER_REPAIR': return '正在核对并修正模型答复'
    case 'AGENT_THINKING': return '正在分析问题'
    case 'MODEL_CONNECT_RETRY': return '模型连接暂时失败，正在重连一次'
    case 'MODEL_REASONING': return '正在思考'
    case 'RESPONSE_STREAMING': return '正在撰写回复'
    case 'TOOL_PREPARING': return '正在准备调用工具'
    case 'PROCESS_COMPLETED': return '处理完成'
    case 'DOCUMENTS_LISTING': return '正在查看知识库文档目录'
    case 'TIME_READING': return '正在获取当前时间'
    case 'TOOL_COMPLETED': return event.tool === 'current_time' ? '已获取当前时间'
      : `已获取${tools[event.tool ?? ''] ?? '所需信息'}${event.resultCount == null ? '' : ` · ${event.resultCount} 条`}`
    case 'TOOL_FAILED': return '暂未取得所需信息，正在调整处理方式'
    case 'SEARCHING': return '正在查找相关内容'
    case 'EMBEDDING_RUNNING':
    case 'QUERY_EMBEDDING_RUNNING': return '正在匹配问题的含义'
    case 'RERANK_RUNNING': return `正在比较${count}内容与问题的相关性`
    case 'RETRIEVE_FUSED': {
      const names: Record<string, string> = { dense: '语义匹配', sparse: '关键词匹配', lexical: '关键词匹配', bm25: '关键词匹配' }
      const channels = Object.entries(event.channelCounts ?? {}).map(([name, value]) => `${names[name] ?? '其他匹配'} ${value} 条`).join('，')
      return `已合并${count}相关内容${channels ? `（${channels}）` : ''}`
    }
    case 'RERANK': return event.enabled === false ? '本轮未启用重排' : `已按相关性重新排序${count}内容`
    case 'CONTEXT': return '已整理可用于回答的原文'
    case 'CHECKING': return `正在核对${count}来源与页码`
    case 'ANSWERING': return '正在准备回答'
    case 'IMAGE_ANALYZING': return '正在查看图片内容'
    case 'RETRYING': return '正在切换可用模型'
    default: return '正在处理'
  }
}
