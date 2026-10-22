import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class EngineTests(unittest.TestCase):
    def test_company_metadata_codes_are_filtered_when_upstream_ignores_codes(self):
        from stock_engine.service import Engine
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory)
            def get(path,*args,**kwargs):
                if path=='/health':return {'last_date':'2026-09-30'}
                return {'items':[{'code':'000001','name':'银行'},{'code':'300024','name':'机器人'}],'total':2}
            engine.market=Mock();engine.market.get.side_effect=get
            result=engine.execute('stock_query',{'task':'query','source':'stocks','universe':{'codes':['300024']},'output':{'fields':['code','name']}},
                                  {'tenant_id':'a','actor_id':'u','conversation_id':'c'})
            self.assertEqual(result['data']['stockArtifact']['preview'],[{'code':'300024','name':'机器人'}])
            engine.market.bars.assert_not_called()
    def test_dataset_field_error_exposes_schema_and_summary_without_requery(self):
        from stock_engine.service import Engine
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);engine.market=Mock()
            scope={'tenant_id':'a','actor_id':'u','conversation_id':'c'}
            ref=engine.store.put(scope,{'table':[{'code':'000001'}],'summary':{'000001':{'lastClose':12,'lastDate':'2026-09-11'}}})
            result=engine.execute('stock_dataset',{'datasetRef':ref,'fields':['lastClose','lastDate']},scope)
            self.assertEqual(result['error'],'UNKNOWN_DATASET_FIELDS')
            self.assertEqual(result['data']['availableFields'],['code'])
            self.assertIn('000001.lastClose',result['data']['availableSummaryFields'])
            engine.market.get.assert_not_called()
    def test_metadata_cache_is_bounded_temporary_and_does_not_cache_health(self):
        import json
        from unittest.mock import patch
        from stock_engine.client import MarketClient
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def iter_bytes(self):yield json.dumps({'items':[{'code':'000001','name':'test'}]}).encode()
        client=MarketClient('http://localhost/api/db')
        with patch('stock_engine.client.httpx.stream',return_value=Response()) as fetch,patch('stock_engine.client.time.monotonic',return_value=100) as timer:
            first=client.get('/stocks',{'q':'000001'});first['items'][0]['name']='changed'
            self.assertEqual(client.get('/stocks',{'q':'000001'})['items'][0]['name'],'test')
            self.assertEqual(fetch.call_count,1)
            timer.return_value=131
            client.get('/stocks',{'q':'000001'})
            self.assertEqual(fetch.call_count,2)
            client.get('/health');client.get('/health')
            self.assertEqual(fetch.call_count,4)
            for i in range(12):client.get('/stocks',{'q':str(i)})
            self.assertLessEqual(len(client.metadata_cache),8)

    def test_invalid_summary_projection_preserves_evidence_and_lists_real_paths(self):
        from stock_engine.service import Engine
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory)
            scope={'tenant_id':'a','actor_id':'u','conversation_id':'c'}
            value={'summary':{'300750':{'lastClose':12},'coverage':{'scannedStocks':1}},'table':[{'close':12}],'warnings':[]}
            artifact=engine.publish(scope,value,0,['close.mean','300750.lastClose'])['data']['stockArtifact']
            self.assertEqual(artifact['summary'],{'300750.lastClose':12})
            self.assertEqual(artifact['ignoredSummaryFields'],['close.mean'])
            self.assertIn('coverage.scannedStocks',artifact['availableSummaryFields'])
            stored=engine.store.get(scope,artifact['datasetRef'])
            self.assertEqual(stored['table'],[{'close':12}])
            self.assertTrue(stored['warnings'])
            second=engine.publish(scope,value,0,['coverage.count'])['data']['stockArtifact']
            self.assertEqual(second['summary']['300750']['lastClose'],12)
            data=engine.execute('stock_dataset',{'datasetRef':artifact['datasetRef'],'section':'summary','fields':['300750.lastClose']},scope)['data']
            self.assertEqual(data['summary'],{'300750.lastClose':12})

    def test_causal_indicators_and_units(self):
        from stock_engine.expressions import evaluate
        import pandas as pd
        bars = pd.DataFrame({'close': [1., 2., 3., 4.], 'volume': [10., 0., 30., 40.]})
        result, unit = evaluate('MA(CLOSE,3)', bars)
        self.assertTrue(pd.isna(result.iloc[1]))
        self.assertEqual(result.iloc[2], 2.)
        self.assertEqual(unit, 'price')
        with self.assertRaises(ValueError): evaluate('RSI(CLOSE,2)>MA(CLOSE,2)', bars)
        with self.assertRaises(ValueError): evaluate('REF(CLOSE,-1)', bars)
        with self.assertRaises(ValueError): evaluate('__import__("os")', bars)
        with self.assertRaises(ValueError): evaluate('MA(CLOSE,2) and 1', bars)

    def test_missing_not_remains_missing(self):
        from stock_engine.expressions import evaluate
        import pandas as pd
        result, _ = evaluate('NOT(CLOSE>REF(CLOSE,1))', pd.DataFrame({'close': [1., 2.]}))
        self.assertTrue(pd.isna(result.iloc[0]))
        self.assertEqual(result.iloc[1], 0.)

    def test_horizon_counts_and_cooldown(self):
        from stock_engine.analytics import event_study
        import pandas as pd
        bars = pd.DataFrame({'date': ['2026-09-%02d' % d for d in range(1, 7)],
                             'close': [10., 11., 12., 13., 14., 15.], 'volume': [1.] * 6})
        data = event_study({'000001': bars}, 'CLOSE>0', [1, 3], cooldown=2)
        self.assertEqual(data['summary']['events'], 3)
        self.assertEqual(data['summary']['forward']['1']['n'], 3)
        self.assertEqual(data['summary']['forward']['3']['n'], 2)
        self.assertAlmostEqual(data['summary']['forward']['1']['mean'], (0.1 + 1/12 + 1/14)/3)

    def test_next_open_costs_and_no_same_day_sell(self):
        from stock_engine.backtest import run_backtest
        import pandas as pd
        bars = pd.DataFrame({'date': ['2026-09-01', '2026-09-02', '2026-09-03'],
                             'open': [10., 20., 30.], 'close': [10., 20., 30.],
                             'high': [11., 21., 31.], 'low': [9., 19., 29.], 'volume': [1., 1., 1.]})
        data = run_backtest(bars, 'CLOSE>0', 'CLOSE>0', cash=10000, fee=0.001, slippage=0, sell_tax=0)
        fills = data['table']
        self.assertEqual(fills[0]['date'], '2026-09-02')
        self.assertEqual(fills[0]['price'], 20.)
        self.assertEqual(fills[0]['shares'], 400)
        self.assertEqual(fills[1]['date'], '2026-09-03')
        self.assertAlmostEqual(data['summary']['finalEquity'], 13980)

    def test_dataset_scope_and_annotation_values(self):
        from stock_engine.service import DatasetStore
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetStore(directory)
            scope = {'tenant_id': 'a', 'actor_id': 'u', 'conversation_id': 'c'}
            ref = store.put(scope, {'table': [{'date': '2026-09-01', 'close': 12.3}]})
            self.assertEqual(store.get(scope, ref)['table'][0]['close'], 12.3)
            with self.assertRaises(ValueError): store.get({**scope, 'actor_id': 'v'}, ref)

    def test_browser_table_export_uses_scoped_full_saved_dataset(self):
        from stock_engine.app import create_app
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(token='test', data_dir=directory)
            engine = app.extensions['stock_engine']
            scope = {'tenant_id':'a','actor_id':'u','conversation_id':'c'}
            ref = engine.store.put(scope, {'table':[{'close':i} for i in range(300)]})
            client = app.test_client()
            headers = {'Authorization':'Bearer test'}
            body = {'datasetRef':ref,'context':scope}
            self.assertEqual(len(client.post('/artifacts/read',json=body,headers=headers).json['table']),200)
            result = client.post('/artifacts/read',json={**body,'view':'table'},headers=headers)
            self.assertEqual(len(result.json['table']),300)
            self.assertNotIn('charts',result.json)
            denied = client.post('/artifacts/read',json={**body,'view':'table','context':{**scope,'actor_id':'other'}},headers=headers)
            self.assertEqual(denied.status_code,400)

    def test_http_and_mcp_are_authenticated(self):
        from stock_engine.app import create_app
        with tempfile.TemporaryDirectory() as directory:
            client = create_app(token='test', data_dir=directory).test_client()
            self.assertEqual(client.post('/tools/execute', json={}).status_code, 401)
            self.assertEqual(client.post('/mcp', json={}).status_code, 401)
            response = client.post('/mcp', headers={'Authorization': 'Bearer test'}, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(any(t['name'] == 'stock_events' for t in response.json['result']['tools']))

    def test_query_schema_keeps_bulk_data_out_of_model_context_and_warmup(self):
        from stock_engine.service import Engine
        import pandas as pd
        class Market:
            def get(self, path, *args, **kwargs):
                if path == '/health': return {'last_date':'2026-09-06'}
                return {'items':[{'code':'000001','name':'test','is_st':False}]}
            def bars(self, *args):
                frame = pd.DataFrame({'date':['2026-09-%02d' % d for d in range(1,7)],
                    'open':[10.,11.,12.,13.,14.,15.], 'close':[10.,11.,12.,13.,14.,15.],
                    'high':[11.,12.,13.,14.,15.,16.], 'low':[9.,10.,11.,12.,13.,14.],
                    'volume':[1.]*6,'amount':[100.]*6})
                return frame, {}, False
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine('http://localhost/api/db',directory); engine.market = Market()
            scope = {'tenant_id':'a','actor_id':'b','conversation_id':'c'}
            result = engine.execute('stock_query',{'task':'events','universe':{'codes':['000001']},
                'window':{'start':'2026-09-04','bars':10},'condition':'CLOSE>MA(CLOSE,3)',
                'periods':[1],'cooldown':1,'output':{'previewRows':0}},scope)
            artifact = result['data']['stockArtifact']
            self.assertEqual(artifact['summary']['events'],3)
            self.assertEqual(artifact['preview'],[])
            self.assertNotIn('rows',artifact['charts'][0])
            stored = engine.store.get(scope,artifact['datasetRef'])
            self.assertEqual(len(stored['table']),3)
            with self.assertRaises(ValueError): engine.execute('stock_query',{'task':'query','output':{'previewRows':1000}},scope)

    def test_annotation_has_engine_derived_value_and_new_immutable_ref(self):
        from stock_engine.service import Engine
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine('http://localhost/api/db',directory)
            scope = {'tenant_id':'a','actor_id':'u','conversation_id':'c'}
            ref = engine.store.put(scope,{'provenance':{},'table':[{'date':'2026-09-01','close':12.3}],'charts':[]})
            args = {'datasetRef':ref,'date':'2026-09-01','field':'close','label':'support'}
            result = engine.execute('stock_annotate',args,scope)['data']['stockArtifact']
            self.assertEqual(result['annotations'][0]['value'],12.3)
            self.assertNotEqual(result['datasetRef'],ref)
            self.assertNotIn('annotations',engine.store.get(scope,ref))
            with self.assertRaises(ValueError): engine.execute('stock_annotate',{**args,'value':999},scope)

    def test_declarative_filter_and_aggregate(self):
        from stock_engine.service import Engine
        class Market:
            def get(self,path,*args,**kwargs):
                if path=='/health':return {'last_date':'2026-09-30'}
                return {'items':[{'code':'000001','board':'main','close':10,'amount':100},
                                 {'code':'000002','board':'main','close':20,'amount':300},
                                 {'code':'300001','board':'cyb','close':30,'amount':600}]}
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost/api/db',directory);engine.market=Market()
            result=engine.execute('stock_query',{'task':'query','source':'snapshot',
                'filters':[{'field':'close','op':'gte','value':20}],
                'aggregations':[{'field':'amount','op':'mean','as':'averageAmount'}],
                'output':{'previewRows':0}}, {'tenant_id':'a','actor_id':'b','conversation_id':'c'})
            summary=result['data']['stockArtifact']['summary']
            self.assertEqual(summary['aggregates'][0]['averageAmount'],450)
            self.assertEqual(summary['filteredRows'],2)

    def test_dataset_summary_projection_and_byte_budget(self):
        from stock_engine.service import Engine
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine('http://localhost/api/db', directory)
            scope = {'tenant_id':'a','actor_id':'u','conversation_id':'c'}
            ref = engine.store.put(scope, {'summary': {'coverage': {'large': 'x'*25000, 'count': 12}}})
            with self.assertRaisesRegex(ValueError, 'DATASET_CONTEXT_BUDGET'):
                engine.execute('stock_dataset', {'datasetRef':ref,'section':'summary'}, scope)
            data = engine.execute('stock_dataset', {'datasetRef':ref,'section':'summary',
                'fields':['coverage.count']}, scope)['data']
            self.assertEqual(data['summary'], {'coverage.count':12})

    def test_volume_ma_excludes_suspension_observations(self):
        import pandas as pd
        from stock_engine.expressions import evaluate
        result,_=evaluate('MA(VOLUME,2)',pd.DataFrame({'volume':[10.,0.,30.,40.]}))
        self.assertEqual(result.iloc[2],20.)
        self.assertTrue(pd.isna(result.iloc[1]))


if __name__ == '__main__': unittest.main()
