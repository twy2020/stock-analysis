import json
import time
import uuid
from app.extensions import database
from . import knowledge, registry
from .models import KnowledgeDocument
from .security import PluginError


def tool(name, description, properties, required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{
        'type':'object','properties':properties,'required':list(required),'additionalProperties':False}}}


class PluginRuntime:
    def __init__(self, service, context, sid, names, cancelled=lambda:False, images=None, run_id=None):
        self.service, self.context, self.sid = service, context, sid
        self.cancelled = cancelled
        self.images = images or []
        self.run_id = run_id or str(uuid.uuid4())
        self.max_output_tokens = min(8192,max(256,int(service.get('maxOutputTokens',4096))))
        self.deadline = time.monotonic()+300
        self.entries = {k:v for k,v in registry.catalog(service,agent=True).items() if k in names}
        self.tools = [tool(name,e['description'],e['inputSchema'].get('properties',{}),e['inputSchema'].get('required',[])) for name,e in self.entries.items()]
        # Preserve complete schemas, including enums and nested constraints.
        for item in self.tools: item['function']['parameters']=self.entries[item['function']['name']]['inputSchema']
        self.tools += [
            tool('session_list_documents','列出本次图纸会话已装载的资料',{}),
            tool('session_recall','检索本次会话资料。技术结论先查证，保留来源和坐标。',{
                'question':{'type':'string','minLength':1,'maxLength':8192},'topK':{'type':'integer','minimum':1,'maximum':20},
                'documentIds':{'type':'array','items':{'type':'string'},'maxItems':100}},['question']),
            tool('session_unload_document','从临时会话卸载资料，不删除原图纸。',{'documentId':{'type':'string'}},['documentId']),
            tool('session_load_document','调用已授权的只读证据工具，将返回 data.document 装载或更新到临时空间。document 必须含 id/title/revision/chunks。',{
                'tool':{'type':'string','enum':[n for n,e in self.entries.items() if e.get('effect')=='read']},
                'arguments':{'type':'object'}},['tool','arguments'])]
        if not any(e.get('effect')=='read' for e in self.entries.values()):
            self.tools = [t for t in self.tools if t['function']['name']!='session_load_document']

    def execute(self, name, raw, operation):
        if self.cancelled(): raise PluginError('CANCELLED')
        if time.monotonic()>self.deadline: raise PluginError('RUN_DEADLINE')
        entry = next((t['function'] for t in self.tools if t['function']['name']==name),None)
        if not entry: raise PluginError('TOOL_FORBIDDEN',403)
        try: args=json.loads(raw)
        except ValueError: raise PluginError('INVALID_ARGUMENTS')
        registry.validate(entry['parameters'],args)
        space = knowledge.owned(self.service,self.sid)
        if space.context!=self.context: raise PluginError('CONTEXT_CONFLICT',409)
        request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self.run_id+':'+str(operation.get('operationId'))))
        if name in self.entries and self.entries[name].get('transport')=='ocr-vision-v1':
            from .vision import analyze
            from langgraph.config import get_stream_writer
            selected = args['imageIndices']
            if any(i>=len(self.images) for i in selected): raise PluginError('IMAGE_NOT_FOUND')
            images = [{'image_id':str(i),'mime_type':self.images[i]['mediaType'],
                       'data_base64':self.images[i]['data'], 'source_ref':self.context} for i in selected]
            identity = {**self.context,'service_id':self.service['id'],'tenant_id':self.service['tenantId']}
            result = None
            for event in analyze(self.entries[name], images, args['question'], identity, request_id, cancelled=self.cancelled):
                if event['type']=='result': result=event['result']
                else: get_stream_writer()({**event,'parentOperationId':operation.get('operationId')})
            return {'contractVersion':'1','status':'succeeded','data':result}
        if name=='session_list_documents':
            return {'items':[{'id':d.id,'title':d.title,'revision':d.revision} for d in knowledge.documents(space)]}
        if name=='session_recall': return knowledge.search(space,args)
        if name=='session_unload_document':
            if space.kind!='temporary': raise PluginError('PERSISTENT_SPACE_READ_ONLY',403)
            database.session.query(KnowledgeDocument).filter_by(space_id=space.id,id=args['documentId']).delete()
            database.session.commit()
            return {'unloaded':args['documentId']}
        if name=='session_load_document':
            if space.kind!='temporary': raise PluginError('PERSISTENT_SPACE_READ_ONLY',403)
            selected = self.entries.get(args['tool'])
            if not selected or selected.get('effect')!='read': raise PluginError('TOOL_FORBIDDEN',403)
            result=registry.execute(self.service,self.context,args['tool'],args['arguments'],request_id=request_id,agent=True)
            doc=(result.get('data') or {}).get('document')
            if not isinstance(doc,dict): raise PluginError('DOCUMENT_RESULT_REQUIRED')
            return knowledge.put(space,doc.get('id'),{k:v for k,v in doc.items() if k!='id'})
        return registry.execute(self.service,self.context,name,args,request_id=request_id,agent=True)
