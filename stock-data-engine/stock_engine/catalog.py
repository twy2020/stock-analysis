"""One declarative contract shared by HTTP, MCP and the Core registry."""
def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def integer(low, high, default=None):
    return {'type': 'integer', 'minimum': low, 'maximum': high, **({'default': default} if default is not None else {})}


EXPR = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
DATE = {'type': 'string', 'pattern': '^\\d{4}-\\d{2}-\\d{2}$'}
REF = {'type': 'string', 'pattern': '^ds_[a-f0-9]{32}$'}
CODE = {'type': 'string', 'pattern': '^(?:[0-9]{6}(?:\\.(?:SH|SZ|BJ))?|(?:sh|sz|bj)[0-9]{6})$'}
UNIVERSE = obj({'codes': {'type': 'array', 'items': CODE, 'minItems': 1, 'maxItems': 300, 'uniqueItems': True},
                'q': {'type': 'string', 'maxLength': 80}, 'board': {'type': 'string', 'maxLength': 80},
                'excludeST': {'type': 'boolean', 'default': True}, 'sample': integer(1,300,50),
                'seed': integer(0,2147483647,2026), 'offset': integer(0,10000,0)})
WINDOW = obj({'start': DATE, 'end': DATE, 'bars': integer(1,6000,300), 'warmup': integer(0,1000,260)})
INDICATORS = {'type': 'array', 'maxItems': 8, 'items': obj({
    'id': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_]{0,31}$'},
    'expression': EXPR, 'panel': {'enum': ['price','separate']}}, ['id','expression'])}
OUTPUT = obj({'fields': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                          'description':'表格列投影，例如date/open/close/high/low及自定义指标id；不是摘要字段。',
                          'items': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_]{0,31}$'}},
              'previewRows': integer(0,20,5), 'sortBy': {'type': 'string', 'maxLength': 32},
              'order': {'enum': ['asc','desc']}, 'limit': integer(1,5000,100),
              'summaryFields': {'type': 'array', 'maxItems': 20, 'items': {'type':'string','maxLength':80},
                'description':'仅选择真实摘要路径，不做统计计算。单股示例300750.lastClose、300750.lastBar.close、300750.lastIndicators.RSI14、coverage.scannedStocks。首次查询建议省略；close.mean/high.max/coverage.count不是内置路径，统计用aggregations。'}})
QUERY = obj({'task': {'enum': ['query','analyze','screen','events','backtest','compare']},
             'filters': {'type':'array','maxItems':20,'items':obj({'field':{'type':'string','maxLength':32},
                 'op':{'enum':['eq','ne','gt','gte','lt','lte','in']},'value':{'type':['string','number','boolean','array']}},['field','op','value'])},
             'groupBy': {'type':'array','maxItems':3,'uniqueItems':True,'items':{'type':'string','maxLength':32}},
             'aggregations': {'type':'array','maxItems':10,'items':obj({'field':{'type':'string','maxLength':32},
                 'op':{'enum':['count','sum','mean','median','std','min','max','quantile']},
                 'q':{'type':'number','minimum':0,'maximum':1},'as':{'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_]{0,31}$'}},['field','op','as'])},
             'source': {'enum': ['bars','snapshot','stocks','rank','dates']},
             'analysisWindows': {'type':'array','maxItems':8,'minItems':1,'uniqueItems':True,'items':integer(1,6000),
                'description':'analyze/query的观察窗口根数，例如[300,100,10,5]；一次取数并返回各窗口统计，指标周期仍由indicators表达式指定，不随观察窗口自动改变。window.bars至少为最大观察窗口。'},
             'universe': UNIVERSE, 'window': WINDOW, 'indicators': INDICATORS, 'condition': EXPR,
             'periods': {'type': 'array','minItems':1,'maxItems':10,'uniqueItems':True,'items':integer(1,60)},
             'cooldown': integer(0,120,10), 'buy': EXPR, 'sell': EXPR,
             'screenMode': {'enum':['latest','history','any']},
             'minHits': {**integer(1,6000,1), 'description':'screen history/any: minimum active-bar hits within the cropped observation window. latest requires 1; any returns the last hit with hitCount.'},
             'before':integer(0,60,5),'after':integer(1,60,10),
             'execution':obj({'buySize':integer(1,100,100),'sellSize':integer(1,100,100),
                               'buyDelay':integer(0,30,0),'sellDelay':integer(0,30,0)}),
             'costs': obj({'cash': {'type':'number','minimum':100,'maximum':1e9},
                           'fee': {'type':'number','minimum':0,'maximum':.05},
                           'slippage': {'type':'number','minimum':0,'maximum':.05},
                           'sellTax': {'type':'number','minimum':0,'maximum':.05}}),
             'rankBy': {'enum': ['amount','volume','close','high','low','amplitude','pct_change','change_pct','volatility','days']},
             'output': OUTPUT}, ['task'])

TOOLS = [
    {'name':'stock_schema','description':'获取数据引擎查询schema、表达式语义、量纲与示例。先按用户需求构造规则；全部计算由引擎执行。','inputSchema':obj({})},
    {'name':'stock_health','description':'查询实际行情覆盖与数据截至日期；不是实时行情。','inputSchema':obj({})},
    {'name':'stock_query','description':'执行AI编写的声明式查询/分析schema。支持股票池、时间窗、指标表达式、条件选股、事件统计、回测、比较及字段投影。默认只返回摘要、最多20行预览和datasetRef，完整数据不进入模型上下文。','inputSchema':QUERY},
    {'name':'stock_events','description':'执行事件统计schema，返回有效样本数、各观察期分布、同期基准、重叠限制。条件使用布尔表达式，不能把概率当收益。','inputSchema':QUERY},
    {'name':'stock_backtest','description':'执行探索性回测schema：单股明细或多股独立资金扫描，仓位比例与买卖延迟可配置，收盘信号、后续开盘、T+1、100股整手与费用。多股均值不是实际组合收益。','inputSchema':QUERY},
    {'name':'stock_dataset','description':'按需读取当前对话数据集的字段、事件profile或摘要，每次最多20行、20KB；摘要只支持真实路径，例如300750.lastClose、coverage.scannedStocks。超预算时缩小fields或limit。','inputSchema':obj({'datasetRef':REF,'section':{'enum':['table','profile','summary','schema']},'fields':{'type':'array','minItems':1,'maxItems':20,'items':{'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.]{0,159}$'}},'offset':integer(0,1000000,0),'limit':integer(1,20,5)},['datasetRef'])},
    {'name':'stock_annotate','description':'引用真实数据日期与字段添加点/区间标注。数值由引擎提取，AI仅提供标签，不得传入价格或坐标。','inputSchema':obj({'datasetRef':REF,'date':DATE,'endDate':DATE,'field':{'type':'string','maxLength':32},'label':{'type':'string','minLength':1,'maxLength':120}},['datasetRef','date','field','label'])},
    {'name':'stock_sql','description':'受控只读SQLite SELECT/WITH查询；仅stocks/bars表，最多5000行。结果保存在数据集，仅摘要/字段/少量预览进入上下文。复杂查询优先使用有预算的schema。','inputSchema':obj({'sql':{'type':'string','minLength':1,'maxLength':8000},'limit':integer(1,5000,100),'previewRows':integer(0,20,5)},['sql'])},
]
