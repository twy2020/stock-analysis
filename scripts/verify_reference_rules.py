"""Run inside the engine container: real market data, bounded outputs, no model."""
import json
import os
from pathlib import Path
import httpx


token = Path(os.environ['STOCK_ENGINE_TOKEN_FILE']).read_text().strip()
headers = {'Authorization': 'Bearer ' + token}
scope = {'tenant_id':'stock-research', 'actor_id':'verification', 'conversation_id':'reference-rules'}


def execute(tool, arguments):
    response = httpx.post('http://127.0.0.1:18310/tools/execute', headers=headers, timeout=100,
        json={'contractVersion':'1', 'tool':tool, 'arguments':arguments, 'context':scope})
    result = response.json()
    assert result.get('status') == 'succeeded', result.get('error')
    return result['data']


schema = execute('stock_schema', {})
assert 'minHits' in schema['querySchema']['properties']
mcp = httpx.post('http://127.0.0.1:18310/mcp', headers=headers, timeout=10,
    json={'jsonrpc':'2.0', 'id':1, 'method':'tools/list'}).json()
query_tool = next(tool for tool in mcp['result']['tools'] if tool['name']=='stock_query')
assert 'minHits' in query_tool['inputSchema']['properties']
rules = {
    'task':'analyze', 'universe':{'codes':['000001']}, 'window':{'bars':100, 'warmup':260},
    'indicators':[
        {'id':'ConfirmedPeak', 'expression':'CONFIRMEDPEAK(CLOSE,3,3)', 'panel':'separate'},
        {'id':'ConfirmedTrough', 'expression':'CONFIRMEDTROUGH(CLOSE,3,3)', 'panel':'separate'},
        {'id':'AboveMA20', 'expression':'ACTIVE(CROSS(CLOSE,MA(CLOSE,20)),CROSSDOWN(CLOSE,MA(CLOSE,20)))', 'panel':'separate'},
    ], 'output':{'previewRows':0},
}
artifact = execute('stock_query', rules)['stockArtifact']
assert not artifact['preview'] and all('rows' not in c for c in artifact['charts'])
assert len(artifact['charts']) == 5
page = execute('stock_dataset', {'datasetRef':artifact['datasetRef'], 'fields':['date','ConfirmedPeak','ConfirmedTrough','AboveMA20'], 'limit':5})
assert len(page['rows']) == 5
assert all(row['ConfirmedPeak'] in (None, 0, 1) for row in page['rows'])
screen = execute('stock_query', {'task':'screen', 'universe':rules['universe'], 'window':rules['window'],
    'condition':'CONFIRMEDPEAK(CLOSE,3,3)', 'screenMode':'any', 'minHits':2, 'output':{'previewRows':1}})['stockArtifact']
assert screen['summary']['minHits'] == 2
assert all(row['hitCount'] >= 2 for row in screen['preview'])
backtest = execute('stock_backtest', {'task':'backtest', 'universe':rules['universe'], 'window':rules['window'],
    'buy':'CONFIRMEDTROUGH(CLOSE,3,3)', 'sell':'CONFIRMEDPEAK(CLOSE,3,3)', 'output':{'previewRows':0}})['stockArtifact']
assert 'finalEquity' in backtest['summary']
print(json.dumps({'lastDate':artifact['summary']['000001']['lastDate'], 'charts':len(artifact['charts']),
    'schemaMinHits':True, 'mcpMinHits':True, 'datasetRowsRead':len(page['rows']),
    'screenMatchedStocks':screen['summary']['matchedStocks'], 'screenQualifiedHits':screen['summary']['qualifiedHits'],
    'backtestFills':backtest['summary']['fills'], 'modelCalls':0}, ensure_ascii=False))
