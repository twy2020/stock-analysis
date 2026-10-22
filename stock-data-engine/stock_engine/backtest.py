"""Single-stock exploratory simulator, causal signals and conservative fills."""
import math
import time
import pandas as pd
from .expressions import evaluate
from .analytics import RAW_WARNINGS


def run_backtest(bars, buy, sell, cash=100000, fee=.0003, slippage=.001, sell_tax=.0005,
                 buy_size=100, sell_size=100, buy_delay=0, sell_delay=0, deadline=None):
    if cash <= 0 or not all(0 <= v <= .05 for v in (fee, slippage, sell_tax)): raise ValueError('Invalid costs or cash')
    if not all(type(v) is int and 1<=v<=100 for v in (buy_size,sell_size)) or not all(type(v) is int and 0<=v<=30 for v in (buy_delay,sell_delay)):raise ValueError('Invalid execution settings')
    buys, ub = (bars['_buy'],'bool') if '_buy' in bars else evaluate(buy, bars)
    sells, us = (bars['_sell'],'bool') if '_sell' in bars else evaluate(sell, bars)
    if ub != 'bool' or us != 'bool': raise ValueError('Buy/sell must be predicates')
    initial = cash; shares = 0; cost_basis = 0; entry_cash = 0; cycle_pnl=0.; fills = []; curve = []; skipped = []; completed=[]; positions=[]
    fees = 0.; wins = 0; trades = 0; pending = None
    benchmark_cash = initial; benchmark_shares = 0; benchmark_started = False; buy_index = -1
    for i, row in bars.iterrows():
        if deadline and i%100==0 and time.monotonic()>deadline:raise ValueError('QUERY_BUDGET_EXCEEDED')
        active = row.volume > 0 and row.open > 0
        locked = row.high == row.low
        # One-price sessions cannot establish whether the order could fill.
        action=pending[0] if pending and i>=pending[1] else None
        if action and (not active or locked):
            skipped.append({'date': row.date, 'side': action, 'reason': 'suspension_or_one_price_bar'})
            pending = None
            action=None
        if action == 'sell' and shares and i > buy_index:
            qty=shares if sell_size==100 else min(shares,max(100,int(shares*sell_size/100/100)*100))
            price = row.open*(1-slippage); charge = qty*price*(fee+sell_tax)
            proceeds = qty*price-charge; cash += proceeds; fees += charge
            allocated=entry_cash*qty/shares; pnl=proceeds-allocated;cycle_pnl+=pnl;entry_cash-=allocated
            fills.append({'date': row.date, 'side': 'sell', 'price': float(price), 'shares': qty,
                          'fee': charge, 'pnl': pnl})
            shares-=qty
            if not shares:
                trades += 1; wins += cycle_pnl > 0; cost_basis = 0
                completed.append({'entryDate':bars.date.iloc[buy_index],'exitDate':row.date,'holdingBars':i-buy_index,'pnl':cycle_pnl})
                cycle_pnl=0.
        elif action == 'buy' and not shares:
            price = row.open*(1+slippage); qty = int(cash*buy_size/100/(price*(1+fee))/100)*100
            if qty:
                charge = qty*price*fee; entry_cash = qty*price+charge; cash -= entry_cash; fees += charge
                shares = qty; cost_basis = price; buy_index = i
                fills.append({'date': row.date, 'side': 'buy', 'price': float(price), 'shares': qty, 'fee': charge})
            else: skipped.append({'date': row.date, 'side': 'buy', 'reason': 'insufficient_cash_for_lot'})
        if action:pending = None
        if i > 0 and not benchmark_started and active and not locked:
            price = row.open*(1+slippage); benchmark_shares = int(initial/(price*(1+fee))/100)*100
            benchmark_cash -= benchmark_shares*price*(1+fee); benchmark_started = True
        equity = cash+shares*row.close
        positions.append(shares*row.close/equity if equity else 0)
        curve.append({'date': row.date, 'equity': float(equity),
                      'benchmark': float(benchmark_cash+benchmark_shares*row.close)})
        if not pending:
            if shares and pd.notna(sells.iloc[i]) and sells.iloc[i] != 0: pending = ('sell',i+1+sell_delay)
            elif not shares and pd.notna(buys.iloc[i]) and buys.iloc[i] != 0: pending = ('buy',i+1+buy_delay)
    equity = pd.Series([r['equity'] for r in curve]); returns = equity.pct_change().dropna()
    final = float(equity.iloc[-1]); days = max(1,len(bars)-1)
    return {'summary': {'initialCash': initial, 'finalEquity': final, 'totalReturn': final/initial-1,
                        'annualizedReturn': (final/initial)**(252/days)-1,
                        'maxDrawdown': float((1-equity/equity.cummax()).max()), 'completedTrades': trades,
                        'winRate': wins/trades if trades else None, 'feesPaid': fees,
                        'benchmarkReturn': curve[-1]['benchmark']/initial-1, 'skippedFills': len(skipped),
                        'openShares': shares, 'unexecutedLastSignal': pending[0] if pending else None,
                        'fills':len(fills),'averagePosition':sum(positions)/len(positions),
                        'holdBars':sum(p>0 for p in positions),'flatBars':sum(p==0 for p in positions),
                        'buySize':buy_size,'sellSize':sell_size,'buyDelay':buy_delay,'sellDelay':sell_delay,
                        'feeRate': fee, 'sellTaxRate': sell_tax, 'slippageRate': slippage,
                        'execution': 'close signal / open after 1 + delay observed bars; T+1; 100-share lots; single stock',
                        'costBasis': cost_basis},
            'table': fills, 'trades':completed,'skippedFills': skipped, 'warnings': [*RAW_WARNINGS,
                '单股探索性回测，不是组合收益。没有公司行为、历史ST状态、逐日涨跌停规则或订单簿。',
                '停牌与一字K线跳过当日委托；其他涨跌停成交可行性仍无法保证；期末持仓按市值计价，未强制平仓。',
                '费率为用户指定的简化常数，不代表历史税费制度；未收最低佣金或过户费。'],
            'charts': [{'kind': 'line', 'title': '策略与买入持有权益', 'unit': 'CNY', 'rows': curve,
                        'fields': ['equity','benchmark']}]}
