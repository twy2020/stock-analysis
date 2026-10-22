import tempfile
import unittest
import pandas as pd

from stock_engine.expressions import evaluate
from stock_engine.service import Engine


class ReferenceRuleTests(unittest.TestCase):
    def test_confirmed_extrema_are_reported_on_confirmation_bar(self):
        bars = pd.DataFrame({'close': [1., 3., 2., 1., 4., 2., 1.]})
        peaks, unit = evaluate('CONFIRMEDPEAK(CLOSE,1,2)', bars)
        troughs, _ = evaluate('CONFIRMEDTROUGH(CLOSE,1,1)', bars)
        self.assertEqual(unit, 'bool')
        self.assertTrue(peaks.iloc[:3].isna().all())
        self.assertEqual(peaks.iloc[3], 1.)
        self.assertEqual(peaks.iloc[6], 1.)
        self.assertEqual(troughs.iloc[4], 1.)
        tied, _ = evaluate('CONFIRMEDPEAK(CLOSE,1,1)', pd.DataFrame({'close': [1., 3., 3., 1.]}))
        self.assertEqual(tied.dropna().sum(), 0)
        for length in range(1, len(bars)+1):
            prefix, _ = evaluate('CONFIRMEDPEAK(CLOSE,1,2)', bars.iloc[:length])
            pd.testing.assert_series_equal(prefix, peaks.iloc[:length])

    def test_active_state_end_wins_and_is_causal(self):
        bars = pd.DataFrame({'close': [1., 3., 2., 1., 3., 1.]})
        state, unit = evaluate('ACTIVE(CLOSE>2,CLOSE<2)', bars)
        self.assertEqual(unit, 'bool')
        self.assertEqual(state.tolist(), [0., 1., 1., 0., 1., 0.])
        both, _ = evaluate('ACTIVE(CLOSE>0,CLOSE>0)', bars)
        self.assertEqual(both.sum(), 0)
        missing, _ = evaluate('ACTIVE(CLOSE>REF(CLOSE,1),CLOSE<REF(CLOSE,1))', bars)
        self.assertTrue(pd.isna(missing.iloc[0]))
        gaps, _ = evaluate('ACTIVE(CLOSE>2,CLOSE<2)', pd.DataFrame({'close':[3., float('nan'), 2., 1.]}))
        self.assertEqual(gaps.iloc[0], 1.)
        self.assertTrue(pd.isna(gaps.iloc[1]))
        self.assertEqual(gaps.iloc[2], 1.)
        self.assertEqual(gaps.iloc[3], 0.)
        for length in range(1, len(bars)+1):
            prefix, _ = evaluate('ACTIVE(CLOSE>2,CLOSE<2)', bars.iloc[:length])
            pd.testing.assert_series_equal(prefix, state.iloc[:length])
        with self.assertRaises(ValueError): evaluate('ACTIVE(CLOSE,1)', bars)
        with self.assertRaises(ValueError): evaluate('CONFIRMEDPEAK(CLOSE,1,-1)', bars)

    def test_screen_min_hits_counts_window_before_last_hit_projection(self):
        class Market:
            def get(self, path, *args, **kwargs):
                if path == '/health': return {'last_date': '2026-09-06'}
                return {'items': [{'code': '000001', 'name': 'test', 'is_st': False}]}
            def bars(self, *args):
                return pd.DataFrame({'date': pd.date_range('2026-09-01', periods=6).strftime('%Y-%m-%d'),
                    'close': [1., 3., 1., 3., 1., 3.], 'open': [1.]*6, 'high': [4.]*6,
                    'low': [1.]*6, 'volume': [1.]*6, 'amount': [1.]*6}), {}, False
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine('http://localhost', directory); engine.market = Market()
            scope = {'tenant_id':'t', 'actor_id':'u', 'conversation_id':'c'}
            args = {'task':'screen', 'universe':{'codes':['000001']}, 'condition':'CLOSE>2',
                    'screenMode':'any', 'minHits':3, 'output':{'previewRows':1}}
            result = engine.execute('stock_query', args, scope)['data']['stockArtifact']
            self.assertEqual(result['summary']['matchedStocks'], 1)
            self.assertEqual(result['summary']['qualifiedHits'], 3)
            self.assertEqual(result['preview'][0]['hitCount'], 3)
            self.assertEqual(result['preview'][0]['date'], '2026-09-06')
            none = engine.execute('stock_query', {**args, 'minHits':4}, scope)['data']['stockArtifact']
            self.assertEqual(none['summary']['matchedStocks'], 0)
            cropped = engine.execute('stock_query', {**args, 'window':{'bars':2}}, scope)['data']['stockArtifact']
            self.assertEqual(cropped['summary']['matchedStocks'], 0)
            with self.assertRaises(ValueError):
                engine.execute('stock_query', {**args, 'screenMode':'latest'}, scope)
