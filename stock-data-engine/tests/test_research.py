import tempfile
import unittest
import pandas as pd
from stock_engine.analytics import event_study
from stock_engine.backtest import run_backtest
from stock_engine.service import Engine


def bars(count=100):
    close=pd.Series([10+i*.1 for i in range(count)])
    return pd.DataFrame({'date':pd.date_range('2025-01-01',periods=count).strftime('%Y-%m-%d'),
        'open':close,'close':close,'high':close+1,'low':close-1,'volume':[100.]*count,'amount':[10000.]*count})


class Market:
    def get(self,path,*args,**kwargs):
        if path=='/health':return {'last_date':'2025-04-10'}
        return {'items':[{'code':c,'name':c,'is_st':False} for c in ['000001','000002']]}
    def bars(self,*args):return bars(),{},False


class ResearchTests(unittest.TestCase):
    def test_multi_window_analysis_fetches_bars_once_and_separates_indicator_period(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);market=Market();market.bars=Mock(wraps=market.bars);engine.market=market
            args={'task':'analyze','universe':{'codes':['000001']},'window':{'bars':100},'analysisWindows':[100,10,5,1],
                'indicators':[{'id':'MA20','expression':'MA(CLOSE,20)','panel':'price'}],'output':{'previewRows':0}}
            artifact=engine.execute('stock_query',args,{'tenant_id':'t','actor_id':'u','conversation_id':'c'})['data']['stockArtifact']
            self.assertEqual(market.bars.call_count,1)
            windows=artifact['summary']['000001']['windows']
            self.assertEqual([windows[str(n)]['observations'] for n in [100,10,5,1]],[100,10,5,1])
            self.assertAlmostEqual(windows['5']['priceReturn'],19.9/19.5-1)
            self.assertAlmostEqual(windows['5']['indicators']['MA20']['last'],18.95)
            self.assertEqual(windows['5']['indicators']['MA20']['validObservations'],5)
            self.assertNotIn('returnDistribution',windows['5'])
            self.assertEqual(windows['1']['observations'],1)
            self.assertIsNone(windows['1']['annualizedVolatility'])

    def test_bad_indicator_is_rejected_before_market_io(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);engine.market=Mock()
            with self.assertRaisesRegex(ValueError,'duplicates'):
                engine.execute('stock_query',{'task':'analyze','indicators':[{'id':'close','expression':'MA(CLOSE,20)'}]},
                    {'tenant_id':'t','actor_id':'u','conversation_id':'c'})
            engine.market.get.assert_not_called()

    def test_unknown_table_field_does_not_discard_completed_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);engine.market=Market()
            artifact=engine.execute('stock_query',{'task':'analyze','universe':{'codes':['000001']},
                'output':{'fields':['date','close','nonexistentIndicator'],'previewRows':1}},
                {'tenant_id':'t','actor_id':'u','conversation_id':'c'})['data']['stockArtifact']
            self.assertEqual(set(artifact['preview'][0]),{'date','close'})
            self.assertTrue(any('nonexistentIndicator' in warning for warning in artifact['warnings']))
            self.assertTrue(artifact['charts'])

    def test_analysis_latest_bar_and_indicators_are_engine_owned_and_query_runs_once(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);market=Market();market.bars=Mock(wraps=market.bars);engine.market=market
            artifact=engine.execute('stock_query',{'task':'analyze','universe':{'codes':['000001']},
                'indicators':[{'id':'MA20','expression':'MA(CLOSE,20)','panel':'price'}],
                'output':{'previewRows':0,'summaryFields':['high.max','coverage.count']}},
                {'tenant_id':'t','actor_id':'u','conversation_id':'c'})['data']['stockArtifact']
            self.assertEqual(market.bars.call_count,1)
            self.assertAlmostEqual(artifact['summary']['000001']['lastBar']['close'],19.9)
            self.assertAlmostEqual(artifact['summary']['000001']['lastIndicators']['MA20'],18.95)
            self.assertEqual(artifact['preview'],[])
            self.assertNotIn('rows',artifact['charts'][0])

    def test_incomplete_event_windows_and_warmup_remain_missing_or_counted(self):
        result=event_study({'000001':bars()},'CLOSE>19.75',[1,5],cooldown=1,before=3,after=5)
        self.assertTrue(all(row['maxUp'] is None for row in result['table']))
        self.assertEqual(result['summary']['forward']['5']['n'],0)
        self.assertEqual(next(row for row in result['profile'] if row['offset']==1)['relativeCloseN'],1)
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);engine.market=Market()
            scope={'tenant_id':'t','actor_id':'u','conversation_id':'c'}
            artifact=engine.execute('stock_events',{'task':'events','universe':{'codes':['000001']},
                'window':{'start':'2025-03-22'},'condition':'CLOSE>0','periods':[1],
                'output':{'previewRows':0}},scope)['data']['stockArtifact']
            page=engine.execute('stock_dataset',{'datasetRef':artifact['datasetRef'],'section':'profile',
                'fields':['offset','RSI14','RSI14N'],'limit':20},scope)['data']
            self.assertEqual(next(row for row in page['rows'] if row['offset']==0)['RSI14N'],2)

    def test_event_profile_has_per_feature_counts_and_incomplete_horizons(self):
        result=event_study({'000001':bars()},'CLOSE>0',[1,5],cooldown=10,before=3,after=5)
        self.assertEqual(len(result['profile']),9)
        zero=next(r for r in result['profile'] if r['offset']==0)
        self.assertIn('RSI14',zero)
        self.assertIn('RSI14N',zero)
        self.assertIn('maxUp',result['table'][0])
        self.assertAlmostEqual(result['table'][0]['maxUp'],(11.5/10)-1)
        self.assertAlmostEqual(result['table'][0]['return5'],.05)
        self.assertIsNone(result['table'][0]['momentum5'])
        self.assertEqual(result['table'][0]['beforeReturn'],None)
        self.assertIn('事件前后价格路径',[c['title'] for c in result['charts']])

    def test_delayed_partial_fills_and_complete_trade_accounting(self):
        data=run_backtest(bars(8),'CLOSE>0','CLOSE>0',cash=10000,fee=0,slippage=0,sell_tax=0,
                          buy_size=50,sell_size=50,buy_delay=1,sell_delay=0)
        self.assertEqual(data['table'][0]['date'],'2025-01-03')
        self.assertEqual(data['table'][0]['shares'],400)
        self.assertEqual(data['table'][1]['shares'],200)
        self.assertEqual(data['summary']['completedTrades'],1)
        self.assertIn('averagePosition',data['summary'])

    def test_historical_screen_and_multi_stock_backtest_stay_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);engine.market=Market()
            scope={'tenant_id':'t','actor_id':'u','conversation_id':'c'}
            query={'task':'screen','universe':{'codes':['000001']},'condition':'CLOSE>19',
                   'screenMode':'history','output':{'previewRows':0}}
            result=engine.execute('stock_query',query,scope)['data']['stockArtifact']
            self.assertEqual(result['summary']['matchedEvents'],9)
            self.assertGreater(len(result['charts']),0)
            self.assertNotIn('rows',result['charts'][0])
            result=engine.execute('stock_backtest',{'task':'backtest','universe':{'codes':['000001','000002']},
                'buy':'CLOSE>0','sell':'CLOSE<0','output':{'previewRows':0}},scope)['data']['stockArtifact']
            self.assertEqual(result['summary']['scannedStocks'],2)
            self.assertEqual(result['rowCount'],2)
            self.assertNotIn('rows',result['charts'][0])

    def test_warnings_do_not_accumulate_between_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine('http://localhost',directory);engine.market=Market()
            scope={'tenant_id':'t','actor_id':'u','conversation_id':'c'}
            engine.market.bars=lambda *args:(bars(),{},True)
            args={'task':'analyze','universe':{'codes':['000001']}}
            first=engine.execute('stock_query',args,scope)['data']['stockArtifact']
            second=engine.execute('stock_query',args,scope)['data']['stockArtifact']
            self.assertEqual(first['warnings'],second['warnings'])
