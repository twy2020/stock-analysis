"""Exercise deployed plugin APIs using a private token file and synthetic data."""
import argparse
import base64
import io
import json
from pathlib import Path
import time
import uuid
import httpx
from PIL import Image, ImageDraw


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:18100/api/service/v1')
    parser.add_argument('--token-file',type=Path,default=Path(__file__).resolve().parents[1]/'.local/integrations/cad-service.token')
    parser.add_argument('--live',action='store_true',help='Make actual model and OCR calls using synthetic content')
    args=parser.parse_args()
    report={}
    context={'project_id':'04b16a9b-f69a-4ab2-b026-de4108ee1617','drawing_id':'9ca2b0a19683a8a01f4e','revision':'6'}
    with httpx.Client(base_url=args.base,headers={'Authorization':'Bearer '+args.token_file.read_text().strip()},timeout=30) as client:
        def call(method,path,body=None):
            response=client.request(method,path,json=body)
            if response.status_code>=400:
                raise RuntimeError(f'{method} {path}: HTTP {response.status_code}; code={response.json().get("code")}')
            return response.json() if response.content else None
        assert httpx.get(args.base+'/capabilities',timeout=10).status_code==401
        report['tools']=[t['name'] for t in call('GET','/capabilities')['tools']]
        sid=call('POST','/spaces',{'context':context})['id']
        path='/spaces/'+sid
        try:
            document={'title':'SaaS integration synthetic fixture','revision':'6','chunks':[
                {'id':'test-1','text':'联调测试卡：钢板厚度为12毫米。此为合成测试数据，不是工程结论。',
                 'source':{'page':1,'bbox':[.1,.2,.3,.4],'synthetic':True}}]}
            call('PUT',path+'/documents/test-document',document)
            found=call('POST',path+'/search',{'question':'钢板厚度'})
            assert found['results'][0]['source']['bbox']==[.1,.2,.3,.4]
            document['chunks'][0]['text']='联调测试卡更新：法兰孔距为200毫米。'
            call('PUT',path+'/documents/test-document',document)
            assert not call('POST',path+'/search',{'question':'钢板厚度'})['results']
            assert call('POST',path+'/search',{'question':'法兰孔距'})['results']
            report['knowledge']='load/update/search with coordinates passed'
            promoted=call('POST',path+'/promote',{'name':'Integration synthetic snapshot','requestId':str(uuid.uuid4())})['id']
            assert call('GET','/spaces/'+promoted+'/package')['format']=='session-knowledge-v1'
            call('DELETE','/spaces/'+promoted)
            report['snapshot']='promote/package/delete passed; not a published RAG KB'
            if args.live:
                image=Image.new('RGB',(640,240),'white')
                ImageDraw.Draw(image).text((30,60),'TEST CARD: BLUE PLATE\nTHICKNESS 12 mm',fill='black',font_size=28)
                output=io.BytesIO();image.save(output,format='PNG')
                request={'requestId':str(uuid.uuid4()),'context':context,'spaceId':sid,
                    'question':'这是集成测试。先调用 session_recall 查询法兰孔距，再调用 ocr_analyze 查看图片0的文字；最后分别用一句话报告二者。不要访问CAD工具或生成工程提案。',
                    'tools':['ocr_analyze'],'images':[{'mediaType':'image/png','data':base64.b64encode(output.getvalue()).decode()}]}
                run=call('POST','/runs',request)
                assert call('POST','/runs',request)['id']==run['id']
                deadline=time.monotonic()+310
                while time.monotonic()<deadline:
                    state=call('GET','/runs/'+run['id'])
                    if state['status'] not in ('QUEUED','RUNNING'):break
                    time.sleep(2)
                assert state['status']=='COMPLETED',{'id':run['id'],'status':state['status']}
                response=client.get('/runs/'+run['id']+'/events')
                response.raise_for_status()
                stream=response.text
                assert 'event: complete' in stream and 'event: tool_result' in stream
                assert 'ocr_analyze' in stream and 'IMAGE_ANALYZING' in stream
                ids=[int(line[4:]) for line in stream.splitlines() if line.startswith('id: ')]
                replay=client.get('/runs/'+run['id']+'/events',headers={'Last-Event-ID':str(ids[-1])})
                assert 'event:' not in replay.text
                report['liveRun']={'id':run['id'],'status':state['status'],'events':len(ids),'answer':state['content']}
            call('DELETE',path+'/documents/test-document')
            assert not call('POST',path+'/search',{'question':'法兰孔距'})['results']
            report['unload']='passed'
        finally:
            call('DELETE',path)
    target=Path(__file__).resolve().parents[1]/'.local/integrations'/('verification.local.json' if args.live else 'verification-basic.local.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
