"""Bounded, read-only interfaces for the stock web MCP adapters."""
TOOLS = [
    {'name':'stock_web_search','description':'管理员配置的AI搜索管理器，按优先级选择搜索供应商并失败切换备用。本地搜索并发多引擎聚合。query单关键词或queries最多3个关键词；engines最多3个本地引擎，通常省略，由管理员选择。去重后合计最多8条来源，部分失败仍返回可用结果。只发送公开关键词；摘要不是核实证据，重要事实用stock_web_fetch读原文。最终以Markdown超链接引用工具真实来源。',
     'inputSchema':{'type':'object','additionalProperties':False,'anyOf':[{'required':['query']},{'required':['queries']}],'properties':{
         'query':{'type':'string','minLength':1,'maxLength':500},
         'queries':{'type':'array','minItems':1,'maxItems':3,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':500}},
         'engines':{'type':'array','minItems':1,'maxItems':3,'uniqueItems':True,'items':{'enum':['bing','baidu','sogou','so360','duckduckgo','google','yandex']}},
         'maxResults':{'type':'integer','minimum':1,'maximum':8,'default':5},
         'freshness':{'enum':['day','week','month','year']},
         'site':{'type':'string','pattern':'^[A-Za-z0-9.-]{1,253}$'}}}},
    {'name':'stock_web_fetch','description':'Dhole 只读浏览公开网页，HTTP优先、必要时浏览器渲染。返回有预算的正文和来源；长文按next_offset续读。不支持内网、登录、表单或写操作。',
     'inputSchema':{'type':'object','additionalProperties':False,'required':['url'],'properties':{
         'url':{'type':'string','minLength':1,'maxLength':2048},
         'offset':{'type':'integer','minimum':0,'maximum':200000,'default':0},
         'maxChars':{'type':'integer','minimum':500,'maximum':8000,'default':4000},
         'focus':{'type':'string','maxLength':300}}}},
]
