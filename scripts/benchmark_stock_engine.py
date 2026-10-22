"""Run inside the stock engine container; exercise real read-only data, not a model."""
import json
import os
import time
from pathlib import Path
import httpx

token = Path(os.environ['STOCK_ENGINE_TOKEN_FILE']).read_text().strip()
arguments = {
    'task': 'analyze', 'universe': {'q': '平安银行'},
    'window': {'bars': 300, 'warmup': 260}, 'analysisWindows': [300, 100, 10, 5],
    'indicators': [
        {'id': 'BOLL_MID', 'expression': 'MA(CLOSE,20)', 'panel': 'price'},
        {'id': 'BOLL_UPPER', 'expression': 'MA(CLOSE,20)+2*STD(CLOSE,20)', 'panel': 'price'},
        {'id': 'BOLL_LOWER', 'expression': 'MA(CLOSE,20)-2*STD(CLOSE,20)', 'panel': 'price'},
        {'id': 'RSI14', 'expression': 'RSI(CLOSE,14)', 'panel': 'separate'},
    ], 'output': {'previewRows': 0},
}
report = []
for attempt in range(2):
    start = time.monotonic()
    response = httpx.post('http://127.0.0.1:18310/tools/execute',
        headers={'Authorization': 'Bearer ' + token}, timeout=100,
        json={'contractVersion': '1', 'tool': 'stock_query', 'arguments': arguments,
              'context': {'tenant_id': 'stock-research', 'actor_id': 'performance-check', 'conversation_id': 'multi-window-check'}})
    result = response.json()
    assert result.get('status') == 'succeeded', result.get('error')
    artifact = result['data']['stockArtifact']
    summary = artifact['summary']['000001']
    assert [summary['windows'][str(n)]['observations'] for n in [300, 100, 10, 5]] == [300, 100, 10, 5]
    assert all(summary['windows'][str(n)]['complete'] for n in [300, 100, 10, 5])
    assert not artifact['preview'] and all('rows' not in chart for chart in artifact['charts'])
    report.append({'attempt': attempt + 1, 'seconds': round(time.monotonic() - start, 3),
                   'windows': list(summary['windows']), 'actualLastDate': summary['lastDate'],
                   'chartCount': len(artifact['charts']), 'responseBytes': len(response.content)})
print(json.dumps(report, ensure_ascii=False))
