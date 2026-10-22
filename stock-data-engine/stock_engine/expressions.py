"""Causal, unit-aware expression evaluator using Python's parser, never eval."""
import ast
import re
import numpy as np
import pandas as pd

FIELDS = {'O': 'open', 'H': 'high', 'L': 'low', 'C': 'close', 'V': 'volume', 'A': 'amount'}
UNITS = {'open': 'price', 'high': 'price', 'low': 'price', 'close': 'price', 'volume': 'lots', 'amount': 'money'}


def evaluate(expression, bars):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 2000:
        raise ValueError('Expression must contain 1 to 2000 characters')
    text = re.sub(r'\bAND\b', 'and', expression, flags=re.I)
    text = re.sub(r'\bOR\b', 'or', text, flags=re.I).replace('&&', ' and ').replace('||', ' or ')
    text = re.sub(r'\bNOT\b', 'not', text, flags=re.I)
    text = re.sub(r'(?<![<>=!])=(?!=)', '==', text.replace('<>', '!=').replace('^', '**'))
    try: tree = ast.parse(text.strip(), mode='eval')
    except (SyntaxError, RecursionError): raise ValueError('Invalid expression') from None
    if sum(1 for _ in ast.walk(tree)) > 256: raise ValueError('Expression too complex')
    index = bars.index

    def series(value): return value if isinstance(value, pd.Series) else pd.Series(float(value), index=index)
    def compatible(a, b):
        if a != b and a != 'scalar' and b != 'scalar': raise ValueError('Incompatible units: ' + a + ' / ' + b)
        return b if a == 'scalar' else a
    def boolean(unit):
        if unit not in ('bool', 'scalar'): raise ValueError('Logical operations require predicates')
    def period(node):
        if not isinstance(node, ast.Constant) or type(node.value) is not int or not 1 <= node.value <= 1000:
            raise ValueError('Periods must be literal integers from 1 to 1000; future references forbidden')
        return node.value
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float) and np.isfinite(node.value):
            if abs(node.value) > 1e12: raise ValueError('Constant too large')
            return series(node.value), 'scalar'
        if isinstance(node, ast.Name):
            name = FIELDS.get(node.id.upper(), node.id.lower())
            if name not in UNITS or name not in bars: raise ValueError('Unknown data field: ' + node.id)
            value = pd.to_numeric(bars[name], errors='coerce').astype(float)
            if name in ('volume', 'amount'): value = value.where(bars.get('volume', value) > 0)
            return value, UNITS[name]
        if isinstance(node, ast.UnaryOp):
            value, unit = visit(node.operand)
            if isinstance(node.op, ast.Not):
                boolean(unit); return (value == 0).astype(float).where(value.notna()), 'bool'
            if isinstance(node.op, ast.USub): return -value, unit
            if isinstance(node.op, ast.UAdd): return value, unit
        if isinstance(node, ast.BoolOp):
            pairs = [visit(v) for v in node.values]
            for _, unit in pairs: boolean(unit)
            valid = pd.concat([v.notna() for v, _ in pairs], axis=1).all(axis=1)
            matrix = pd.concat([v != 0 for v, _ in pairs], axis=1)
            result = matrix.all(axis=1) if isinstance(node.op, ast.And) else matrix.any(axis=1)
            return result.astype(float).where(valid), 'bool'
        if isinstance(node, ast.BinOp):
            a, ua = visit(node.left); b, ub = visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                unit = compatible(ua, ub)
                return (a+b if isinstance(node.op, ast.Add) else a-b), unit
            if isinstance(node.op, ast.Mult):
                if ua not in ('scalar','ratio') and ub not in ('scalar','ratio'): raise ValueError('Normalize quantities before multiplication')
                return a*b, ub if ua in ('scalar','ratio') else ua
            if isinstance(node.op, ast.Div):
                unit = 'ratio' if ua == ub else ua if ub in ('scalar','ratio') else None
                if unit is None: raise ValueError('Incompatible division units')
                return a/b.replace(0, np.nan), unit
            if isinstance(node.op, ast.Pow) and ua == ub == 'scalar' and isinstance(node.right, ast.Constant) and abs(node.right.value) <= 10:
                return a.pow(b), 'scalar'
        if isinstance(node, ast.Compare):
            left, unit = visit(node.left); out = series(1); valid = left.notna()
            for op, child in zip(node.ops, node.comparators):
                right, other = visit(child); compatible(unit, other); valid &= right.notna()
                functions = {ast.Gt: lambda: left > right, ast.Lt: lambda: left < right,
                             ast.GtE: lambda: left >= right, ast.LtE: lambda: left <= right,
                             ast.Eq: lambda: np.isclose(left, right, rtol=1e-9, atol=0),
                             ast.NotEq: lambda: ~np.isclose(left, right, rtol=1e-9, atol=0)}
                if type(op) not in functions: raise ValueError('Unsupported comparison')
                out *= functions[type(op)](); left, unit = right, other
            return out.where(valid), 'bool'
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id.upper(); args = node.args
            if name in ('CONFIRMEDPEAK', 'CONFIRMEDTROUGH') and len(args) == 3:
                s, _ = visit(args[0]); left = period(args[1]); right = period(args[2])
                candidate = s.shift(right)
                previous = s.shift(right+1).rolling(left, min_periods=left)
                following = s.rolling(right, min_periods=right)
                a = previous.max() if name == 'CONFIRMEDPEAK' else previous.min()
                b = following.max() if name == 'CONFIRMEDPEAK' else following.min()
                hit = (candidate > a) & (candidate > b) if name == 'CONFIRMEDPEAK' else (candidate < a) & (candidate < b)
                return hit.astype(float).where(candidate.notna() & a.notna() & b.notna()), 'bool'
            if name == 'ACTIVE' and len(args) == 2:
                start, us = visit(args[0]); end, ue = visit(args[1]); boolean(us); boolean(ue)
                valid = start.notna() & end.notna()
                # End takes priority; state is emitted at the current bar, never backdated.
                changes = series(np.nan).where(~(valid & (start != 0)), 1.)
                changes = changes.where(~(valid & (end != 0)), 0.)
                state = changes.ffill().fillna(0.)
                return state.where(valid), 'bool'
            if name in ('MA', 'EMA', 'SUM', 'STD', 'HHV', 'LLV', 'REF', 'RSI', 'PCTCHANGE', 'COUNT', 'EVERY', 'NEWHIGH', 'NEWLOW', 'ISMAX', 'ISMIN') and len(args) == 2:
                s, unit = visit(args[0]); n = period(args[1]); roll = s.rolling(n, min_periods=n)
                if name == 'MA': return s.dropna().rolling(n).mean().reindex(index) if unit in ('lots','money') else roll.mean(), unit
                if name == 'EMA': return s.ewm(span=n, adjust=False, min_periods=n).mean(), unit
                if name == 'SUM': return roll.sum(), unit
                if name == 'STD': return roll.std(ddof=0), unit
                if name == 'HHV': return roll.max(), unit
                if name == 'LLV': return roll.min(), unit
                if name == 'REF': return s.shift(n), unit
                if name == 'PCTCHANGE': return (s/s.shift(n).replace(0, np.nan)-1)*100, 'ratio'
                if name == 'RSI':
                    delta = s.diff(); up = delta.clip(lower=0); down = -delta.clip(upper=0)
                    # Wilder seed is the arithmetic mean of the first n changes.
                    def smooth(values):
                        out = pd.Series(np.nan, index=index)
                        for i in range(n, len(values)):
                            if i == n or pd.isna(out.iloc[i-1]): out.iloc[i] = values.iloc[i-n+1:i+1].mean() if values.iloc[i-n+1:i+1].notna().all() else np.nan
                            elif pd.notna(values.iloc[i]): out.iloc[i] = (out.iloc[i-1]*(n-1)+values.iloc[i])/n
                        return out
                    gain, loss = smooth(up), smooth(down)
                    value = (100-100/(1+gain/loss.replace(0, np.nan))).where(loss != 0, 100.)
                    return value.where((gain != 0) | (loss != 0), 50.).where(gain.notna() & loss.notna()), 'ratio'
                if name in ('COUNT', 'EVERY'):
                    boolean(unit); count = (s != 0).astype(float).where(s.notna()).rolling(n).sum()
                    return (count == n).astype(float).where(count.notna()) if name == 'EVERY' else count, 'bool' if name == 'EVERY' else 'ratio'
                extreme = roll.max() if name in ('NEWHIGH', 'ISMAX') else roll.min()
                if name in ('NEWHIGH', 'NEWLOW'):
                    extreme = s.shift(1).rolling(n).max() if name == 'NEWHIGH' else s.shift(1).rolling(n).min()
                    return (s > extreme if name == 'NEWHIGH' else s < extreme).astype(float).where(extreme.notna() & s.notna()), 'bool'
                return (s >= extreme if name == 'ISMAX' else s <= extreme).astype(float).where(extreme.notna() & s.notna()), 'bool'
            if name in ('CROSS', 'CROSSDOWN', 'MIN', 'MAX') and len(args) == 2:
                a, ua = visit(args[0]); b, ub = visit(args[1]); unit = compatible(ua, ub)
                if name in ('MIN', 'MAX'): return pd.Series(np.minimum(a,b) if name == 'MIN' else np.maximum(a,b), index=index), unit
                valid = a.notna() & b.notna() & a.shift(1).notna() & b.shift(1).notna()
                return ((a > b) & (a.shift(1) <= b.shift(1)) if name == 'CROSS' else (a < b) & (a.shift(1) >= b.shift(1))).astype(float).where(valid), 'bool'
            if name == 'ABS' and len(args) == 1:
                s, unit = visit(args[0]); return s.abs(), unit
            if name == 'IF' and len(args) == 3:
                c, uc = visit(args[0]); boolean(uc); a, ua = visit(args[1]); b, ub = visit(args[2])
                return a.where(c != 0, b).where(c.notna()), compatible(ua, ub)
        raise ValueError('Unsupported or non-causal expression')

    with np.errstate(all='ignore'):
        values, unit = visit(tree.body)
    return values.replace([np.inf, -np.inf], np.nan), unit
