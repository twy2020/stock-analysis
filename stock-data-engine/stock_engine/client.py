import re
import os
import time
import copy
import json
from threading import Lock
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
import httpx
import pandas as pd


def code(value):
    value = str(value).upper()
    if not re.fullmatch(r'(?:\d{6}(?:\.(?:SH|SZ|BJ))?|(?:SH|SZ|BJ)\d{6})', value): raise ValueError('Invalid stock code')
    return re.search(r'\d{6}',value).group()


class MarketClient:
    def __init__(self, base):
        parsed = urlsplit(base)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Invalid market URL')
        self.base = base.rstrip('/')
        token_file = os.getenv('MARKET_API_TOKEN_FILE')
        self.headers = {'Authorization':'Bearer '+Path(token_file).read_text('utf-8-sig').strip()} if token_file else {}
        self.metadata_cache={};self.cache_lock=Lock()

    def get(self, path, params=None, deadline=None, payload=None):
        remaining = min(25,deadline-time.monotonic()) if deadline else 25
        if remaining <= 0: raise ValueError('QUERY_BUDGET_EXCEEDED')
        key=json.dumps(params or {},sort_keys=True) if path=='/stocks' and payload is None else None
        if key is not None:
            with self.cache_lock:
                cached=self.metadata_cache.get(key)
                if cached and time.monotonic()-cached[0]<30:return copy.deepcopy(cached[1])
        try:
            with httpx.stream('POST' if payload else 'GET', self.base+path, params=params, json=payload,
                              headers=self.headers, timeout=remaining, follow_redirects=False, trust_env=False) as response:
                if response.status_code != 200: raise ValueError('Market query failed: HTTP '+str(response.status_code))
                content = bytearray()
                for block in response.iter_bytes():
                    content.extend(block)
                    if len(content) > 16*1024*1024: raise ValueError('MARKET_RESPONSE_BUDGET_EXCEEDED')
            data = json.loads(content)
            if not isinstance(data,dict) or data.get('error'): raise ValueError('Invalid market response')
            if key is not None:
                with self.cache_lock:
                    if len(self.metadata_cache)>=8:self.metadata_cache.pop(next(iter(self.metadata_cache)))
                    self.metadata_cache[key]=(time.monotonic(),copy.deepcopy(data))
            return data
        except httpx.HTTPError: raise ValueError('MARKET_UNAVAILABLE') from None

    def bars(self, symbol, window, deadline):
        params = {'limit': min(12000,window.get('bars',300)+window.get('warmup',260)), 'format':'object','order':'asc'}
        if window.get('end'): params['end'] = date.fromisoformat(window['end']).isoformat()
        if window.get('start'):
            start = date.fromisoformat(window['start']).isoformat()
            dates = self.get('/dates',{'end':start,'limit':window.get('warmup',260)+1,'order':'desc','count':0},deadline)
            values = [d['date'] if isinstance(d,dict) else d for d in dates.get('items',[])]
            params['start'] = min(values) if values else start
        data = self.get('/bars/'+code(symbol),params,deadline)
        rows = data.get('bars',[])
        if rows and isinstance(rows[0],list): rows = [dict(zip(data['fields'],row)) for row in rows]
        frame = pd.DataFrame(rows)
        required = ['date','open','high','low','close','volume','amount']
        if frame.empty or any(k not in frame for k in required): raise ValueError('No complete OHLCV data: '+str(symbol))
        if frame.date.duplicated().any(): raise ValueError('Duplicate market dates')
        frame = frame.sort_values('date').reset_index(drop=True)
        for key in required[1:]: frame[key] = pd.to_numeric(frame[key],errors='coerce')
        if frame[required[1:]].isna().any().any() or (frame.close <= 0).any() or (frame.open <= 0).any() or (frame.volume < 0).any():
            raise ValueError('Invalid OHLCV values')
        if ((frame.low > frame.high) | (frame.low > frame[['open','close']].min(axis=1)) | (frame.high < frame[['open','close']].max(axis=1))).any():
            raise ValueError('Inconsistent OHLC values')
        return frame, data, len(frame) >= params['limit']
