import math
import random
import time
import numpy as np
import pandas as pd
from .expressions import evaluate

RAW_WARNINGS = [
    '未复权价格：除权除息可能产生非经济性跳变，收益与跨日指标仅供探索。',
    '股票池来自当前上市列表，历史研究存在生存偏差；没有财务、行业、复权或实时行情数据。',
]


def records(frame):
    return frame.replace([np.inf, -np.inf], np.nan).astype(object).where(pd.notna(frame), None).to_dict('records')


def distribution(values):
    values = np.asarray(values, dtype=float); values = values[np.isfinite(values)]
    n = len(values)
    if not n: return {'n': 0, 'mean': None, 'median': None, 'upProbability': None, 'quantiles': {}, 'histogram': []}
    hist, edges = np.histogram(values, bins=min(11, max(1, int(math.sqrt(n)))))
    up = int(np.sum(values > 0)); p = up/n; z = 1.96
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return {'n': n, 'mean': float(values.mean()), 'median': float(np.median(values)),
            'std': float(values.std(ddof=1)) if n > 1 else None,
            'upProbability': p, 'downProbability': float(np.mean(values < 0)), 'flatProbability': float(np.mean(values == 0)),
            'upProbabilityWilson95': [center-half, center+half],
            'quantiles': {str(q): float(np.quantile(values, q)) for q in (.05,.25,.75,.95)},
            'histogram': [{'low': float(edges[i]), 'high': float(edges[i+1]), 'count': int(count)} for i,count in enumerate(hist)]}


def describe(bars):
    close = bars.close; returns = close/close.shift(1).replace(0, np.nan)-1
    active = bars.volume > 0
    return {'observations': len(bars), 'firstDate': bars.date.iloc[0], 'lastDate': bars.date.iloc[-1],
            'lastClose': float(close.iloc[-1]), 'priceReturn': float(close.iloc[-1]/close.iloc[0]-1),
            'annualizedVolatility': float(returns.std(ddof=1)*math.sqrt(252)) if returns.notna().sum() > 1 else None,
            'maxPriceDrawdown': float((1-close/close.cummax()).max()),
            'activeObservations': int(active.sum()), 'zeroVolumeObservations': int((~active).sum()),
            'averageActiveVolume': float(bars.loc[active,'volume'].mean()) if active.any() else None,
            'totalAmount': float(bars.amount.sum()), 'returnDistribution': distribution(returns)}


def event_features(bars):
    close=bars.close.replace(0,np.nan)
    missing=pd.Series(np.nan,index=bars.index)
    high=bars.get('high',missing);low=bars.get('low',missing);opening=bars.get('open',missing)
    ma=lambda n: close.rolling(n).mean()
    middle=ma(20); deviation=close.rolling(20).std(ddof=0)
    active_volume=bars.volume.where(bars.volume>0)
    volume_ma=lambda n:active_volume.dropna().rolling(n).mean().reindex(bars.index)
    rsi,_=evaluate('RSI(CLOSE,14)',bars)
    return pd.DataFrame({'dailyReturn':close/close.shift(1)-1,'amplitude':(high-low)/close,
        'body':(close-opening)/opening.replace(0,np.nan),'volumeRatio5':active_volume/volume_ma(5),
        'distanceMA5':close/ma(5)-1,'distanceMA20':close/middle-1,'distanceMA60':close/ma(60)-1,
        'RSI14':rsi,'bollPosition':(close-middle+2*deviation)/(4*deviation).replace(0,np.nan),
        'bollWidth':4*deviation/middle,'distanceHigh20':close/high.rolling(20).max()-1,
        'distanceLow20':close/low.rolling(20).min()-1,'momentum5':close/close.shift(5)-1,
        'volumeRatio20':active_volume/volume_ma(20)}).replace([np.inf,-np.inf],np.nan)


def event_study(stocks, condition, periods, cooldown=5, before=5, after=10, deadline=None):
    rows = []; baselines = {str(p): [] for p in periods}; raw_hits = 0; stock_count = 0
    candidates=[]; accepted=0; rng=random.Random(2026); features={}
    for code, bars in stocks.items():
        signal, unit = (bars['_signal'], 'bool') if '_signal' in bars else evaluate(condition, bars)
        if unit != 'bool': raise ValueError('Event condition must be a predicate')
        hits = np.flatnonzero((signal.fillna(0) != 0) & (bars.volume > 0))
        raw_hits += len(hits); last = -cooldown-1; stock_count += 1
        feature_columns=[column for column in bars if column.startswith('_feature_')]
        features[code]=bars[feature_columns].rename(columns=lambda column:column[9:]) if feature_columns else event_features(bars)
        for p in periods:
            forward = bars.close.shift(-p)/bars.close.replace(0,np.nan)-1
            baselines[str(p)].extend(forward[signal.notna() & (bars.volume > 0)].dropna().tolist())
        for i in hits:
            if i-last < max(1,cooldown): continue
            last = i; accepted+=1
            if len(candidates)<4000:candidates.append((code,i))
            else:
                index=rng.randrange(accepted)
                if index<4000:candidates[index]=(code,i)
    sums={}; counts={}
    for code,i in sorted(candidates):
            if deadline and time.monotonic()>deadline:raise ValueError('QUERY_BUDGET_EXCEEDED')
            bars=stocks[code]; feature=features[code]
            row = {'code': code, 'date': bars.date.iloc[i]}
            for p in periods:
                row['return'+str(p)] = float(bars.close.iloc[i+p]/bars.close.iloc[i]-1) if i+p < len(bars) else None
            complete=i+after<len(bars)
            row['beforeReturn']=float(bars.close.iloc[i]/bars.close.iloc[i-before]-1) if i>=before else None
            row['afterReturn']=float(bars.close.iloc[i+after]/bars.close.iloc[i]-1) if complete else None
            row['maxUp']=float(bars.high.iloc[i+1:i+after+1].max()/bars.close.iloc[i]-1) if complete and 'high' in bars else None
            row['maxDown']=float(bars.low.iloc[i+1:i+after+1].min()/bars.close.iloc[i]-1) if complete and 'low' in bars else None
            row.update({key:float(value) if pd.notna(value) else None for key,value in feature.iloc[i].items()})
            rows.append(row)
            for offset in range(-before,after+1):
                j=i+offset
                if not 0<=j<len(bars):continue
                values={**feature.iloc[j].to_dict(),'relativeClose':bars.close.iloc[j]/bars.close.iloc[i]-1}
                for key,value in values.items():
                    if pd.notna(value) and np.isfinite(value):
                        pair=(offset,key);sums[pair]=sums.get(pair,0)+float(value);counts[pair]=counts.get(pair,0)+1
    keys=[*next(iter(features.values())).columns,'relativeClose'] if features else []
    profile=[{'offset':offset,**{key:sums.get((offset,key),0)/counts[(offset,key)] if counts.get((offset,key)) else None for key in keys},
              **{key+'N':counts.get((offset,key),0) for key in keys}} for offset in range(-before,after+1)]
    forward = {str(p): distribution([r['return'+str(p)] for r in rows if r['return'+str(p)] is not None]) for p in periods}
    baseline = {str(p): distribution(baselines[str(p)]) for p in periods}
    warnings = [*RAW_WARNINGS, '事件收益相对事件收盘，不含费用，不能当作策略收益。',
                'Wilson 区间假定独立样本；跨股票共振与重叠窗口会使区间偏窄，不构成显著性证明。']
    if cooldown < max(periods): warnings.append('冷却期小于最长观察窗口，事件窗口仍可能重叠。')
    if any(v['n'] < 30 for v in forward.values()): warnings.append('部分观察期有效样本少于30，不能据此作稳定推断。')
    if accepted>len(rows):warnings.append('事件超过4000，使用固定种子2026蓄水池抽样；分布和画像基于保留样本。')
    return {'summary': {'events': len(rows), 'rawHits': int(raw_hits), 'stocks': stock_count,
                        'acceptedEvents':accepted,'sampledEvents':accepted>len(rows),'before':before,'after':after,
                        'featureUnits':'returns, amplitude, body, distances, bollWidth: fractions; RSI14: 0..100; volumeRatio/bollPosition: ratios',
                        'cooldownBars': cooldown, 'forward': forward, 'baseline': baseline,
                        'horizon': 'observed daily bars, including suspension placeholders'}, 'table': rows, 'profile':profile,'warnings': warnings,
            'charts': [{'kind': 'histogram', 'title': f'事件后 {p} 根收益分布', 'unit': 'count',
                        'rows': forward[str(p)]['histogram']} for p in periods]+[
                        {'kind':'line','title':'事件前后价格路径','unit':'fraction','xField':'offset','rows':profile,'fields':['relativeClose']},
                        {'kind':'line','title':'事件前后 RSI14','unit':'indicator','xField':'offset','rows':profile,'fields':['RSI14']},
                        {'kind':'line','title':'事件前后量比','unit':'ratio','xField':'offset','rows':profile,'fields':['volumeRatio5','volumeRatio20']}]}
