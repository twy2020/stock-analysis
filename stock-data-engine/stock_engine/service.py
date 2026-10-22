import copy
import hashlib
import json
import random
import re
import time
import uuid
from datetime import datetime, timezone, date
from pathlib import Path
import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator
from .catalog import TOOLS, QUERY
from .client import MarketClient, code
from .expressions import evaluate, UNITS
from .analytics import describe, distribution, records, event_study, event_features, RAW_WARNINGS
from .backtest import run_backtest


def clean(value):
    if isinstance(value, dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [clean(v) for v in value]
    if isinstance(value, (float,np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, np.bool_): return bool(value)
    return value


def context_result(data):
    result = {'contractVersion':'1','status':'succeeded','data':data}
    if len(json.dumps(result,ensure_ascii=False).encode('utf-8')) > 20000:
        raise ValueError('DATASET_CONTEXT_BUDGET: reduce limit or select specific fields; summary fields support dotted paths')
    return result


def summary_paths(summary, limit=60):
    paths=[]
    def walk(node,prefix=''):
        for key,item in node.items():
            if len(paths)>=limit:return
            path=prefix+'.'+key if prefix else key
            paths.append(path)
            if isinstance(item,dict):walk(item,path)
    walk(summary)
    return paths


def price_charts(frame, symbol, name, indicators):
    display=frame.drop(columns=[column for column in frame if column.startswith('_')]).assign(code=symbol,name=name)
    plot=records(display.tail(2000))
    result=[{'kind':'candlestick','title':name+' · '+symbol,'unit':'CNY','rows':plot,
             'fields':[item['id'] for item in indicators if item.get('panel','price')=='price']},
            {'kind':'volume','title':'成交量 · '+symbol,'unit':'lots','rows':plot,'fields':['volume']}]
    result.extend({'kind':'line','title':item['id']+' · '+symbol,'unit':'indicator','rows':plot,'fields':[item['id']]}
                  for item in indicators if item.get('panel')=='separate')
    return result


class DatasetStore:
    def __init__(self, directory):
        self.directory = Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
    @staticmethod
    def scope(context):
        keys = ('tenant_id','actor_id','conversation_id')
        if any(not isinstance(context.get(k),str) or not 1<=len(context[k])<=160 for k in keys): raise ValueError('INVALID_DATASET_SCOPE')
        return {k:context[k] for k in keys}
    def put(self, context, value):
        reference = 'ds_'+uuid.uuid4().hex
        document = {'scope':self.scope(context),'created':time.time(),'value':clean(value)}
        # Immutable datasets avoid lost updates between simultaneous runs.
        path = self.directory/(reference+'.json'); temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(document,ensure_ascii=False,allow_nan=False),encoding='utf-8'); temporary.replace(path)
        return reference
    def get(self, context, reference):
        if not re.fullmatch(r'ds_[a-f0-9]{32}',reference): raise ValueError('INVALID_DATASET_REFERENCE')
        try: row = json.loads((self.directory/(reference+'.json')).read_text('utf-8'))
        except (OSError,ValueError): raise ValueError('DATASET_NOT_FOUND') from None
        if row['scope'] != self.scope(context): raise ValueError('DATASET_SCOPE_FORBIDDEN')
        if time.time()-row['created'] > 30*86400: raise ValueError('DATASET_EXPIRED')
        return row['value']


class Engine:
    def __init__(self, base, directory, allow_sql=False):
        self.market = MarketClient(base); self.store = DatasetStore(directory); self.allow_sql = allow_sql
    def publish(self, context, value, preview=5, summary_fields=None):
        value = clean(value)
        summary = copy.deepcopy(value.get('summary',{}))
        if isinstance(summary.get('coverage'),dict):
            coverage = summary['coverage']
            coverage['rangeCount'] = len(coverage.get('ranges',{}))
            coverage['ranges'] = dict(list(coverage.get('ranges',{}).items())[:5])
            coverage['skipped'] = coverage.get('skipped',[])[:5]
        if summary_fields:
            projected = {}; invalid = []
            for path in summary_fields:
                node = summary
                for key in path.split('.'):
                    if not isinstance(node,dict) or key not in node:
                        invalid.append(path);break
                    node = node[key]
                else: projected[path] = node
            if invalid:
                # Projection mistakes must not discard already computed evidence.
                value['warnings'] = [*value.get('warnings',[]),'忽略不存在的摘要路径：'+', '.join(invalid)+'。行情字段用output.fields；数理聚合用aggregations；请读取availableSummaryFields中的真实路径。']
            summary = projected or summary
        ref = self.store.put(context,value)
        artifact = {'version':'stock-artifact/1','datasetRef':ref,'title':value.get('title','股票分析'),
                    'summary':summary,'provenance':value.get('provenance',{}),'warnings':value.get('warnings',[]),
                    'rowCount':len(value.get('table',[])), 'preview':value.get('table',[])[:preview],
                    'charts':[{'kind':c['kind'],'title':c['title']} for c in value.get('charts',[])],
                    'annotations':value.get('annotations',[]),
                    'schema':value.get('schema',{}), 'referenceSyntax':'[data:'+ref+']'}
        result = {'contractVersion':'1','status':'succeeded','data':{'stockArtifact':artifact}}
        if summary_fields and invalid:
            artifact['availableSummaryFields']=summary_paths(value.get('summary',{}))
            artifact['ignoredSummaryFields']=invalid
        if len(json.dumps(result,ensure_ascii=False).encode()) > 20000:
            artifact['preview'] = []; artifact['summary'] = {'availableFields':list(summary), 'notice':'摘要超过预算，请使用stock_dataset读取具体摘要字段。'}
        return result

    def execute(self, name, args, context):
        entry = next((t for t in TOOLS if t['name'] == name),None)
        if not entry: raise ValueError('TOOL_FORBIDDEN')
        errors = list(Draft202012Validator(entry['inputSchema']).iter_errors(args))
        if errors: raise ValueError('INVALID_QUERY_SCHEMA: '+errors[0].message[:250])
        DatasetStore.scope(context)
        if name == 'stock_schema':
            return {'contractVersion':'1','status':'succeeded','data':{'querySchema':QUERY,
                'units':{'prices':'CNY unadjusted','volume':'lots (100 shares)','amount':'CNY','returns':'fractions','PCTCHANGE':'percent (100x fraction)'},
                'functions':'MA EMA SUM STD(ddof=0) HHV LLV REF RSI(Wilder) PCTCHANGE COUNT EVERY CROSS CROSSDOWN NEWHIGH NEWLOW ISMAX ISMIN CONFIRMEDPEAK CONFIRMEDTROUGH ACTIVE ABS MIN MAX IF; logical AND OR NOT',
                'missing':'Warmup and missing operands propagate null, including NOT; numeric series cannot be logical operands.',
                'semantics':'NEWHIGH compares preceding n bars, EMA has n-bar warmup. No future references. MA(VOLUME,n) uses last n active observations; zero-volume bars remain in price calendars. filters/groupBy/aggregations are post-query engine computations; request a sufficient source limit and check limitReached.',
                'budgets':{'maxStocks':300,'maxBarsPerStock':7000,'previewRows':20,'deadlineSeconds':90},
                'outputGuide':{'fields':'行情表格列和指标id，例如date/open/close/high/low/RSI14；用previewRows=1获取最新一行，order=desc需同时sortBy=date。',
                    'summaryFields':'摘要真实路径，例如300750.lastClose、300750.lastDate、300750.lastBar.high、300750.lastIndicators.RSI14、coverage.scannedStocks；首次可省略。不是close.mean或high.max。',
                    'aggregations':'只支持task=query；例如field=close,op=mean,as=meanClose；结果在summary.aggregates，不在summary.close.mean。',
                    'projectionWarnings':'不存在的summaryFields会被忽略并返回availableSummaryFields；已成功计算的数据集仍有效，不要因投影警告重跑查询。'},
                'research':{'whiteboard':'task=analyze with indicators; Bollinger bands: MA(CLOSE,20) +/- 2*STD(CLOSE,20)',
                    'multiWindow':'analysisWindows=[300,100,10,5] computes window statistics from one fetched history, returned in summary.<code>.windows. Observed windows do not change the indicator expression period. window.bars covers the largest window; complete=false means insufficient observations.',
                    'screen':'screenMode latest (default), history (all matching bars), any (last hit per stock). minHits counts active-bar hits inside the cropped window before history/any projection; each row includes hitCount. latest requires minHits=1.',
                    'confirmedExtrema':'CONFIRMEDPEAK(series,left,right) / CONFIRMEDTROUGH: strict extrema versus left prior and right following bars; ties excluded; emitted on confirmation date right bars after the candidate, never backdated. Missing neighbors yield null.',
                    'activeInterval':'ACTIVE(startPredicate,endPredicate): causal Boolean state including start and excluding end, end wins simultaneous hits, initially inactive, unknown predicates yield null while retaining state. Unlike retrospective MID it needs no future closing event.',
                    'events':'before/after profile has 14 features plus relativeClose, with per-feature N; section=profile reads bounded pages; at most 4000 sampled events, seed2026',
                    'backtest':'execution buySize/sellSize are percentages; delays add observed bars after the next open. Multiple stocks use separate equal initial cash, not a portfolio.'},
                'examples':[{'task':'analyze','universe':{'codes':['300750']},'window':{'bars':300,'warmup':260},
                    'analysisWindows':[300,100,10,5],
                    'indicators':[{'id':'MA20','expression':'MA(CLOSE,20)','panel':'price'},{'id':'RSI14','expression':'RSI(CLOSE,14)','panel':'separate'}],
                    'output':{'previewRows':1,'sortBy':'date','order':'desc','fields':['date','open','close','high','low','MA20','RSI14']}},
                    {'task':'screen','universe':{'board':'cyb','excludeST':True,'sample':100},'window':{'bars':300,'warmup':260},'condition':'CROSS(MA(CLOSE,5),MA(CLOSE,20))','output':{'previewRows':5}},
                            {'task':'events','universe':{'codes':['000001']},'window':{'bars':1400,'warmup':260},'condition':'CROSSDOWN(EMA(CLOSE,3),MA(CLOSE,30)-2*STD(CLOSE,30))','periods':[1,3,5,10],'cooldown':10}]}}
        if name == 'stock_health': return {'contractVersion':'1','status':'succeeded','data':self.market.get('/health')}
        if name == 'stock_dataset':
            value = self.store.get(context,args['datasetRef']); section = args.get('section','table')
            if section in ('summary','schema'):
                result = value.get(section,{})
                if args.get('fields'):
                    projected = {}
                    for path in args['fields']:
                        node = result
                        for key in path.split('.'):
                            if not isinstance(node,dict) or key not in node: raise ValueError('Unknown dataset field: '+path)
                            node = node[key]
                        projected[path] = node
                    result = projected
                # Dictionary pages prevent repeatedly injecting a wide summary.
                pairs = list(result.items()); offset = args.get('offset',0); limit = args.get('limit',5)
                return context_result({'datasetRef':args['datasetRef'],section:dict(pairs[offset:offset+limit]),'total':len(pairs),'nextOffset':offset+limit if offset+limit<len(pairs) else None})
            rows = value.get(section,[]); offset = args.get('offset',0); limit = args.get('limit',5)
            rows_page = rows[offset:offset+limit]
            if args.get('fields'):
                available = set().union(*(r.keys() for r in rows_page)) if rows_page else set(value.get('schema',{}))
                if set(args['fields'])-available:
                    return {'contractVersion':'1','status':'failed','error':'UNKNOWN_DATASET_FIELDS','retryable':False,
                            'data':{'datasetRef':args['datasetRef'],'section':section,'availableFields':sorted(available),
                                    'availableSummaryFields':summary_paths(value.get('summary',{}))[:40]},
                            'message':'fields只能读取该数据集保留的表格列。lastClose/lastDate属于summary；用section=summary及股票代码前缀读取，勿重复查询行情。'}
                rows_page = [{k:r.get(k) for k in args['fields']} for r in rows_page]
            return context_result({'datasetRef':args['datasetRef'],'rows':rows_page,'total':len(rows),'offset':offset,'nextOffset':offset+limit if offset+limit<len(rows) else None})
        if name == 'stock_annotate':
            value = self.store.get(context,args['datasetRef']); field = args['field']
            rows = [r for r in value.get('table',[]) if r.get('date') == args['date']]
            if len(rows) != 1 or not isinstance(rows[0].get(field),(int,float)) or isinstance(rows[0].get(field),bool): raise ValueError('Annotation requires one exact dated numeric record')
            if args.get('endDate'):
                end = [r for r in value.get('table',[]) if r.get('date') == args['endDate']]
                if len(end) != 1 or args['endDate'] < args['date']: raise ValueError('Invalid annotation range')
            value.setdefault('annotations',[]).append({'date':args['date'],'endDate':args.get('endDate'),
                 'field':field,'value':rows[0][field],'label':args['label'],'sourceDatasetRef':args['datasetRef']})
            if len(value['annotations']) > 30: raise ValueError('Annotation limit exceeded')
            value['provenance']['parentDatasetRef'] = args['datasetRef']
            return self.publish(context,value,0)
        if name == 'stock_sql': return self.sql(args,context)
        if name == 'stock_events': args = {**args,'task':'events'}
        if name == 'stock_backtest': args = {**args,'task':'backtest'}
        return self.query(args,context)

    def sql(self,args,context):
        if not self.allow_sql: raise ValueError('SQL_DISABLED')
        from sqlglot import parse, exp
        try: trees = parse(args['sql'],read='sqlite')
        except Exception: raise ValueError('Invalid SQL') from None
        if len(trees) != 1 or not isinstance(trees[0],exp.Query): raise ValueError('Only one read-only query is permitted')
        tree = trees[0]
        ctes = {c.alias for c in tree.find_all(exp.CTE)}
        if any(isinstance(n,(exp.DDL,exp.DML,exp.Command)) for n in tree.walk()): raise ValueError('SQL writes forbidden')
        if any(t.name not in {'stocks','bars'} | ctes or t.db or t.catalog for t in tree.find_all(exp.Table)): raise ValueError('Unknown SQL table')
        if any(isinstance(n,exp.Anonymous) and n.name.lower() in ('load_extension','readfile','writefile') for n in tree.walk()): raise ValueError('SQL function forbidden')
        started = time.monotonic(); health = self.market.get('/health')
        data = self.market.get('/sql',deadline=started+30,payload={'sql':args['sql'],'limit':args.get('limit',100)})
        rows = [dict(zip(data['columns'],r)) for r in data.get('rows',[])]
        value = {'title':'只读查询结果','summary':{'returnedRows':len(rows),'truncated':bool(data.get('truncated'))},
                 'table':rows,'schema':{k:'upstream' for k in data['columns']}, 'warnings':RAW_WARNINGS,
                 'provenance':self.provenance(health,{'sql':args['sql'],'limit':args.get('limit',100)}),'charts':[]}
        return self.publish(context,value,args.get('previewRows',5))

    def provenance(self, health, query):
        return {'source':'Market read-only HTTP API','dataAsOf':health.get('last_date'),
                'retrievedAt':datetime.now(timezone.utc).isoformat(),'adjustment':'none',
                'units':{'price':'CNY','volume':'lots','amount':'CNY','return':'fraction'},
                'query':query,'queryHash':hashlib.sha256(json.dumps(query,sort_keys=True).encode()).hexdigest()}

    def query(self, args, context):
        started = time.monotonic(); deadline = started+90; task = args['task']; window = args.get('window',{})
        for key in ('start','end'):
            if key in window: date.fromisoformat(window[key])
        if window.get('start') and window.get('end') and window['start'] > window['end']: raise ValueError('Invalid date range')
        universe = args.get('universe',{}); output = args.get('output',{}); source = args.get('source','bars')
        if 'minHits' in args and (task!='screen' or source!='bars'):
            raise ValueError('minHits requires screen with bars source')
        if task=='screen' and args.get('screenMode','latest')=='latest' and args.get('minHits',1)!=1:
            raise ValueError('minHits > 1 requires screenMode history or any')
        if args.get('analysisWindows') and (task not in ('analyze','query') or source!='bars'):
            raise ValueError('analysisWindows requires analyze/query with bars source')
        if args.get('analysisWindows') and not window.get('start') and max(args['analysisWindows'])>window.get('bars',300):
            raise ValueError('window.bars must cover the largest analysisWindows value')
        # Validate rules before network I/O so typos do not cost a market scan.
        probe=pd.DataFrame({key:[1.,2.] for key in UNITS})
        reserved={'date','code','name','pct_change',*UNITS}
        identifiers=[]
        for item in args.get('indicators',[]):
            if item['id'].lower() in reserved or item['id'].lower() in identifiers:
                raise ValueError('Indicator ID duplicates a data field or indicator; use MA20, BOLL_UPPER, RSI14 etc.')
            identifiers.append(item['id'].lower())
            _,unit=evaluate(item['expression'],probe)
            if item.get('panel','price')=='price' and unit!='price':raise ValueError('Non-price indicator requires separate panel')
        for key in ('condition','buy','sell'):
            if args.get(key) and evaluate(args[key],probe)[1]!='bool':raise ValueError('Conditions must be predicates')
        health = self.market.get('/health',deadline=deadline)
        if source != 'bars':
            if task != 'query' or args.get('indicators') or args.get('condition'): raise ValueError('Expressions require bars source')
            params = {'limit':output.get('limit',100),'exclude_st':int(universe.get('excludeST',True)),'format':'object'}
            if universe.get('board'): params['board'] = universe['board']
            if universe.get('codes'): params['codes'] = ','.join(code(c) for c in universe['codes'])
            if source == 'stocks': params.update(q=universe.get('q',''),offset=universe.get('offset',0),synced='yes')
            elif source == 'dates': params = {'limit':min(output.get('limit',100),5000),'order':'asc','count':1,**{k:window[k] for k in ('start','end') if k in window}}
            elif source == 'rank':
                params['limit'] = min(params['limit'],500); params['by'] = args.get('rankBy','amount'); params['order'] = output.get('order','desc')
                if window.get('start') and window.get('end'): params.update(start=window['start'],end=window['end'])
                elif window.get('end'): params['date'] = window['end']
            elif source == 'snapshot' and window.get('end'): params['date'] = window['end']
            call_params={k:v for k,v in params.items() if k not in ('codes','offset')} if source=='stocks' and universe.get('codes') else params
            if source=='stocks' and universe.get('codes'):call_params['limit']=5000
            response = self.market.get('/'+source,call_params,deadline); rows = response.get('items',[])
            if rows and isinstance(rows[0],list): rows = [dict(zip(response['fields'],r)) for r in rows]
            if source=='stocks' and universe.get('codes'):
                # The upstream stocks endpoint accepts q, not a codes filter.
                requested={code(c) for c in universe['codes']}
                candidates=rows
                if response.get('total',len(candidates))>5000:
                    candidates.extend(self.market.get('/stocks',{**call_params,'offset':5000},deadline).get('items',[]))
                rows=[r for r in candidates if r.get('code') in requested]
                response={**response,'total':len(rows)}
                rows=rows[:params['limit']]
            value = {'title':'市场查询 · '+source,'summary':{'returnedRows':len(rows),'total':response.get('total'),'date':response.get('date'),
                      'limitReached':len(rows)>=params['limit']},'table':rows,'charts':[],'warnings':RAW_WARNINGS}
        else:
            if universe.get('codes'):
                symbols = list(dict.fromkeys(code(c) for c in universe['codes'])); total = len(symbols)
                if len(symbols)<=3:
                    selected=[row for c in symbols for row in self.market.get('/stocks',{'q':c,'limit':100,'synced':'yes'},deadline).get('items',[]) if row.get('code')==c]
                else:
                    listing = self.market.get('/stocks',{'limit':5000,'synced':'yes'},deadline)
                    selected = list(listing.get('items',[]))
                    if listing.get('total',len(selected))>5000:
                        selected.extend(self.market.get('/stocks',{'limit':5000,'offset':5000,'synced':'yes'},deadline).get('items',[]))
                names = {r['code']:r for r in selected}
                if universe.get('excludeST',True): symbols = [c for c in symbols if c in names and not names[c].get('is_st',False)]
            else:
                listing = self.market.get('/stocks',{'limit':5000,'exclude_st':int(universe.get('excludeST',True)),
                    'synced':'yes','q':universe.get('q',''),'board':universe.get('board',''),'offset':universe.get('offset',0)},deadline)
                selected = list(listing.get('items',[])); total = listing.get('total',len(selected))
                if total>5000:
                    selected.extend(self.market.get('/stocks',{'limit':5000,'exclude_st':int(universe.get('excludeST',True)),
                        'synced':'yes','q':universe.get('q',''),'board':universe.get('board',''),'offset':universe.get('offset',0)+5000},deadline).get('items',[]))
                names = {r['code']:r for r in selected}
                symbols = sorted(random.Random(universe.get('seed',2026)).sample(list(names),min(universe.get('sample',50),len(names))))
                if task=='analyze' and universe.get('q'):
                    exact=[c for c,row in names.items() if row.get('name')==universe['q'] or c==universe['q'] or row.get('symbol')==universe['q']]
                    if len(exact)==1:symbols=exact;total=1
            if not symbols: raise ValueError('Empty stock universe')
            if task == 'analyze' and len(symbols) != 1: raise ValueError('Select exactly one stock for analyze')
            frames = {}; metadata = {}; skipped = []; capped = []
            for symbol in symbols:
                if time.monotonic()>deadline: raise ValueError('QUERY_BUDGET_EXCEEDED')
                try:
                    frame, meta, cap = self.market.bars(symbol,window,deadline)
                    metadata[symbol] = meta
                    for indicator in args.get('indicators',[]):
                        if indicator['id'] in set(frame.columns)|{'code','name'}: raise ValueError('Indicator ID duplicates a data field')
                        series, unit = evaluate(indicator['expression'],frame)
                        if indicator.get('panel','price') == 'price' and unit != 'price': raise ValueError('Non-price indicator requires separate panel')
                        frame[indicator['id']] = series
                    for expression_key, column in (('condition','_signal'),('buy','_buy'),('sell','_sell')):
                        if args.get(expression_key):
                            signal, unit = evaluate(args[expression_key],frame)
                            if unit != 'bool': raise ValueError('Conditions must be predicates')
                            frame[column] = signal
                    if task=='events':
                        features=event_features(frame)
                        for field in features:frame['_feature_'+field]=features[field]
                    if window.get('start'): frame = frame[frame.date >= window['start']]
                    else: frame = frame.tail(window.get('bars',300))
                    if frame.empty: raise ValueError('No bars in selected window')
                    frames[symbol] = frame.reset_index(drop=True)
                    if cap: capped.append(symbol)
                except ValueError as exc:
                    # Rule errors are never disguised as data coverage failures.
                    if any(word in str(exc).lower() for word in ('expression','unit','period','logical','indicator','predicate')): raise
                    skipped.append({'code':symbol,'reason':str(exc)})
            if not frames: raise ValueError('No usable stocks: '+str(skipped[:3]))
            coverage = {'selectedStocks':len(symbols),'scannedStocks':len(frames),'universeTotal':total,
                        'sampleSeed':universe.get('seed',2026),'sampled':len(symbols)<total,'skipped':skipped,'cappedStocks':capped,
                        'ranges':{c:{'first':f.date.iloc[0],'last':f.date.iloc[-1],'bars':len(f)} for c,f in frames.items()}}
            if task == 'events':
                if not args.get('condition'): raise ValueError('condition required')
                # Evaluate using warmup already computed above; signals survive cropping.
                value = event_study(frames, args['condition'], args.get('periods',[1,3,5,10]),args.get('cooldown',10),args.get('before',5),args.get('after',10),deadline)
            elif task == 'backtest':
                if not args.get('buy') or not args.get('sell'): raise ValueError('buy and sell required')
                costs = args.get('costs',{}); execution=args.get('execution',{}); results={}
                for symbol,frame in frames.items():
                    if time.monotonic()>deadline:raise ValueError('QUERY_BUDGET_EXCEEDED')
                    results[symbol]=run_backtest(frame,args['buy'],args['sell'],cash=costs.get('cash',100000),
                        fee=costs.get('fee',.0003),slippage=costs.get('slippage',.001),sell_tax=costs.get('sellTax',.0005),
                        buy_size=execution.get('buySize',100),sell_size=execution.get('sellSize',100),
                        buy_delay=execution.get('buyDelay',0),sell_delay=execution.get('sellDelay',0),deadline=deadline)
                if len(results)==1:
                    symbol=next(iter(results));value=results[symbol];frame=frames[symbol].copy()
                    frame['buyPrice']=np.nan;frame['sellPrice']=np.nan
                    for fill in value['table']:frame.loc[frame.date==fill['date'],fill['side']+'Price']=fill['price']
                    value['charts']+=price_charts(frame,symbol,names.get(symbol,{}).get('name',symbol),args.get('indicators',[]))
                else:
                    table=[{'code':symbol,'name':names.get(symbol,{}).get('name',symbol),**result['summary']} for symbol,result in results.items()]
                    traded=[row for row in table if row['fills']>0]
                    value={'table':table,'warnings':list(next(iter(results.values()))['warnings'])+['多股扫描按独立等额初始资金回测；均值是单股结果汇总，不是共享资金组合或市场组合收益。'],
                        'summary':{'scannedStocks':len(table),'tradedStocks':len(traded),'participation':len(traded)/len(table),
                            'profitableStocks':sum(row['totalReturn']>0 for row in traded),
                            'successRate':sum(row['totalReturn']>0 for row in traded)/len(traded) if traded else None,
                            'averageReturn':float(np.mean([row['totalReturn'] for row in traded])) if traded else None,
                            'averageBenchmarkReturn':float(np.mean([row['benchmarkReturn'] for row in traded])) if traded else None,
                            'averageDrawdown':float(np.mean([row['maxDrawdown'] for row in traded])) if traded else None,
                            'completedTrades':sum(row['completedTrades'] for row in traded),'aggregation':'means among stocks with fills; separate initial cash per stock'},
                        'charts':[{'kind':'histogram','title':'多股策略收益分布','unit':'count','rows':distribution([row['totalReturn'] for row in traded])['histogram']}]}
            elif task == 'screen':
                if not args.get('condition'): raise ValueError('condition required')
                table = [];matched=[];mode=args.get('screenMode','latest');qualified_hits=0
                for c,f in frames.items():
                    hits=f[(f['_signal'].fillna(0)!=0)&(f.volume>0)]
                    hit_count=len(hits)
                    if hit_count<args.get('minHits',1): continue
                    if mode=='latest':hits=hits[hits.date==f.date.iloc[-1]]
                    elif mode=='any':hits=hits.tail(1)
                    if not hits.empty:matched.append(c);qualified_hits+=hit_count
                    table.extend(records(hits.drop(columns=[col for col in hits if col.startswith('_')]).assign(code=c,name=names.get(c,{}).get('name',c),hitCount=hit_count)))
                charts=[]
                for c in (list(frames) if len(frames)==1 else matched[:3]):
                    frame=frames[c].copy();frame['signalPrice']=frame.close.where((frame['_signal'].fillna(0)!=0)&(frame.volume>0))
                    charts+=price_charts(frame,c,names.get(c,{}).get('name',c),args.get('indicators',[]))
                value = {'summary':{'matchedStocks':len(matched),'matchedEvents':len(table),'screenMode':mode,
                          'minHits':args.get('minHits',1),'qualifiedHits':qualified_hits,
                          'asOf':max(f.date.iloc[-1] for f in frames.values())},'table':table,'charts':charts,'warnings':list(RAW_WARNINGS)}
            elif task == 'compare':
                common = sorted(set.intersection(*(set(f.date) for f in frames.values())))
                if len(common)<2: raise ValueError('Not enough common dates to compare')
                joined = pd.DataFrame({'date':common}); summary = {}
                for c,f in frames.items():
                    prices = f.set_index('date').close.loc[common]; joined[c] = prices.to_numpy()/prices.iloc[0]-1
                    summary[c] = {'name':names.get(c,{}).get('name',c),'priceReturn':float(joined[c].iloc[-1]),'observations':len(common)}
                corr = joined[list(frames)].diff().corr().replace(np.nan,None).to_dict()
                value = {'summary':{'stocks':summary,'changeCorrelation':corr,'alignment':'intersection of observed dates'},'table':records(joined),
                         'charts':[{'kind':'line','title':'同日起点价格收益比较','unit':'fraction','rows':records(joined),'fields':list(frames)}],'warnings':RAW_WARNINGS}
            else:
                rows = []; charts = []; summary = {}
                for c,f in frames.items():
                    summary[c] = describe(f)
                    summary[c]['lastBar'] = records(f[['date','open','close','high','low','volume','amount']].tail(1))[0]
                    summary[c]['lastIndicators'] = clean({item['id']:f[item['id']].iloc[-1] for item in args.get('indicators',[])})
                    if args.get('analysisWindows'):
                        windows={}
                        for count in args['analysisWindows']:
                            segment=f.tail(count)
                            stats=describe(segment)
                            stats.pop('returnDistribution',None)
                            stats.update(requestedBars=count,complete=len(segment)==count)
                            stats['indicators']={}
                            for item in args.get('indicators',[]):
                                series=segment[item['id']];valid=series.dropna()
                                stats['indicators'][item['id']]=clean({'last':series.iloc[-1],'validObservations':len(valid),
                                    'mean':valid.mean(),'min':valid.min(),'max':valid.max(),
                                    'first':series.iloc[0]})
                            windows[str(count)]=stats
                        summary[c]['windows']=windows
                    display = f.drop(columns=[col for col in f if col.startswith('_')]); display = display.assign(code=c,name=names.get(c,{}).get('name',c))
                    rows.extend(records(display))
                    if task == 'analyze' or len(frames) == 1:
                        charts+=price_charts(f,c,names.get(c,{}).get('name',c),args.get('indicators',[]))
                if task == 'query' and args.get('condition'): rows = [r for c,f in frames.items() for r in records(f[(f['_signal'].fillna(0)!=0) & (f.volume>0)].assign(code=c,name=names.get(c,{}).get('name',c)))]
                value = {'summary':summary,'table':rows,'charts':charts,'warnings':list(RAW_WARNINGS)}
            value.setdefault('title',{'screen':'条件选股','events':'事件窗口统计','backtest':'策略回测','compare':'股票比较','analyze':'个股分析','query':'行情查询'}[task])
            value['summary']['coverage'] = coverage
            value['warnings']=list(value.get('warnings',[]))
            if capped: value.setdefault('warnings',[]).append('部分查询达到K线预算；覆盖范围以实际返回日期为准。')
            if any(len(f)>2000 for f in frames.values()): value.setdefault('warnings',[]).append('图表仅显示最近2000根，统计使用完整查询区间。')
        rows = value.get('table',[])
        if args.get('filters') or args.get('aggregations'):
            if task != 'query': raise ValueError('filters and aggregations apply only to query tasks')
            frame = pd.DataFrame(rows)
            for rule in args.get('filters',[]):
                field=rule['field']; op=rule['op']; target=rule['value']
                if field not in frame: raise ValueError('Unknown filter field')
                column=frame[field]
                operations={'eq':lambda:column==target,'ne':lambda:column!=target,'gt':lambda:column>target,
                    'gte':lambda:column>=target,'lt':lambda:column<target,'lte':lambda:column<=target,
                    'in':lambda:column.isin(target) if isinstance(target,list) else (_ for _ in ()).throw(ValueError('in requires an array'))}
                try:frame=frame[operations[op]() & column.notna()]
                except TypeError:raise ValueError('Incompatible filter value') from None
            value['summary']['filteredRows']=len(frame)
            if args.get('aggregations'):
                grouped=args.get('groupBy',[])
                if any(key not in frame for key in grouped):raise ValueError('Unknown grouping field')
                groups=frame.groupby(grouped,dropna=False,sort=True) if grouped else [((),frame)]
                aggregates=[]
                names=[a['as'] for a in args['aggregations']]
                if len(set(names))!=len(names) or set(names)&set(grouped):raise ValueError('Aggregate aliases must be unique')
                for keys,group in groups:
                    keys=keys if isinstance(keys,tuple) else (keys,)
                    row=dict(zip(grouped,keys))
                    for operation in args['aggregations']:
                        field=operation['field']; op=operation['op']
                        if field not in group:raise ValueError('Unknown aggregate field')
                        if op=='count':result=group[field].count()
                        else:
                            numbers=pd.to_numeric(group[field],errors='coerce')
                            if group[field].notna().sum()!=numbers.notna().sum():raise ValueError('Aggregate requires numeric values')
                            if op=='quantile':result=numbers.quantile(operation.get('q',.5))
                            elif op=='std':result=numbers.std(ddof=1)
                            else:result=getattr(numbers,op)()
                        row[operation['as']]=result
                    aggregates.append(clean(row))
                value['summary']['aggregates']=aggregates[:20]
                value['summary']['aggregateGroups']=len(aggregates)
                value['table']=aggregates;rows=aggregates;value['charts']=[]
            else:rows=records(frame)
        if output.get('sortBy'):
            key = output['sortBy']
            if rows and any(key not in r for r in rows): raise ValueError('Unknown sort field')
            rows = sorted(rows,key=lambda r:(r.get(key) is None,r.get(key)),reverse=output.get('order','desc')=='desc')
        value['summary']['totalResultRows'] = len(rows)
        if output.get('fields'):
            available = set().union(*(r.keys() for r in rows)) if rows else set()
            invalid=set(output['fields'])-available if rows else set()
            if invalid:
                value.setdefault('warnings',[]).append('忽略不存在的表格字段：'+', '.join(sorted(invalid))+'；实际字段：'+', '.join(sorted(available)))
            fields=[key for key in output['fields'] if key in available]
            if fields:rows = [{k:r.get(k) for k in fields} for r in rows]
        value['table'] = rows[:output.get('limit',5000)]
        value['summary']['tableTruncated'] = len(rows)>len(value['table'])
        value['schema'] = {k:UNITS.get(k,'derived') for row in value['table'][:1] for k in row if not k.startswith('_')}
        value['provenance'] = self.provenance(health,args)
        value['summary']['elapsedMs'] = int((time.monotonic()-started)*1000)
        return self.publish(context,value,output.get('previewRows',5),output.get('summaryFields'))
