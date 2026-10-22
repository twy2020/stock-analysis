import hmac
import json
import os
from pathlib import Path
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException
from .catalog import TOOLS
from .service import Engine


def create_app(token=None, data_dir=None, base=None):
    token = token or os.getenv('STOCK_ENGINE_TOKEN','')
    if not token and os.getenv('STOCK_ENGINE_TOKEN_FILE'):
        token = Path(os.environ['STOCK_ENGINE_TOKEN_FILE']).read_text('utf-8-sig').strip()
    if not token: raise ValueError('Configure an engine token before starting')
    app = Flask(__name__); app.config['MAX_CONTENT_LENGTH'] = 128*1024
    engine = Engine(base or os.getenv('MARKET_API_URL','http://192.168.3.5:8765/api/db'),
                    data_dir or os.getenv('STOCK_DATA_DIR','data/datasets'),
                    os.getenv('STOCK_ALLOW_SQL','true').lower() == 'true')
    app.extensions['stock_engine'] = engine

    @app.before_request
    def authorize():
        if request.path == '/health': return None
        header = request.headers.get('Authorization','')
        if not hmac.compare_digest(header,'Bearer '+token): return {'error':'AUTHENTICATION_REQUIRED'},401
        if request.headers.get('Origin'): return {'error':'SERVICE_ONLY'},403

    @app.errorhandler(ValueError)
    def invalid(exc): return {'contractVersion':'1','status':'failed','error':str(exc)},400

    @app.errorhandler(Exception)
    def unexpected(exc):
        if isinstance(exc,HTTPException): return exc
        app.logger.exception('Stock engine failed')
        return {'contractVersion':'1','status':'failed','error':'ENGINE_INTERNAL_ERROR'},500

    @app.get('/health')
    def health(): return {'status':'UP','service':'stock-data-engine','version':'1'}

    @app.post('/tools/execute')
    def execute():
        body = request.get_json()
        if not isinstance(body,dict) or body.get('contractVersion') != '1': raise ValueError('INVALID_CONTRACT')
        try: return jsonify(engine.execute(body.get('tool'),body.get('arguments',{}),body.get('context',{})))
        except ValueError as exc: return {'contractVersion':'1','status':'failed','error':str(exc),'retryable':False}

    @app.post('/artifacts/read')
    def artifact():
        body = request.get_json()
        if not isinstance(body,dict): raise ValueError('INVALID_CONTRACT')
        value = engine.store.get(body.get('context',{}),body.get('datasetRef',''))
        if body.get('view') == 'table':
            return jsonify({'version':'stock-artifact/1','datasetRef':body['datasetRef'],
                'table':value.get('table',[]),'rowCount':len(value.get('table',[]))})
        # Full data travels only on this non-model route; display tables are paged.
        return jsonify({'version':'stock-artifact/1','datasetRef':body['datasetRef'],
                        **{k:value.get(k,default) for k,default in [('title','股票分析'),('summary',{}),('charts',[]),
                           ('annotations',[]),('provenance',{}),('warnings',[]),('schema',{})]},
                        'warnings':list(dict.fromkeys(value.get('warnings',[]))),
                        'table':value.get('table',[])[:200],'rowCount':len(value.get('table',[]))})

    @app.post('/mcp')
    def mcp():
        body = request.get_json()
        if not isinstance(body,dict) or body.get('jsonrpc') != '2.0': raise ValueError('INVALID_RPC')
        rid = body.get('id'); method = body.get('method'); params = body.get('params',{})
        if method == 'notifications/initialized': return '',202
        if method == 'initialize':
            result = {'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'stock-data-engine','version':'1.0'}}
        elif method == 'tools/list':
            result = {'tools':TOOLS}
        elif method == 'tools/call':
            args = dict(params.get('arguments',{})); context = params.get('_meta',{}).get('context',{})
            try:
                data = engine.execute(params.get('name'),args,context)
                result = {'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'structuredContent':data,'isError':False}
            except ValueError as exc:
                result = {'content':[{'type':'text','text':str(exc)}],'isError':True}
        else: return jsonify({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'METHOD_NOT_FOUND'}})
        return jsonify({'jsonrpc':'2.0','id':rid,'result':result})

    return app
