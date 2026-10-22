import httpx
import pytest
import respx


@respx.mock
def test_vision_adapter_polls_fixed_origin_and_preserves_trusted_context(app, tmp_path):
    from app.plugins.vision import analyze
    token = tmp_path/'vision.token'
    token.write_text('vision-test-secret')
    cfg = {'url':'https://vision.example/api/plugins/vision/v1','tokenFile':str(token)}
    def submit(request):
        import json
        body = json.loads(request.content)
        assert body['context'] == {'project_id':'p1'}
        assert request.headers['Authorization'] == 'Bearer vision-test-secret'
        return httpx.Response(202,json={'job_id':'abc','state':'queued','result_url':'https://evil.example/result'})
    respx.post(cfg['url']+'/jobs').mock(side_effect=submit)
    respx.get(cfg['url']+'/jobs/abc').mock(return_value=httpx.Response(200,json={'state':'completed'}))
    respx.get(cfg['url']+'/jobs/abc/result').mock(return_value=httpx.Response(200,json={'result':{
        'schema_version':1,'summary':'测试图像','regions':[],'evidence':[],'part_proposals':[]}}))
    with app.app_context():
        events = list(analyze(cfg, [{'image_id':'1','mime_type':'image/png','data_base64':'AA=='}],
            '识别图片', {'project_id':'p1'}, 'run-1'))
    assert events[-1]['result']['summary'] == '测试图像'
    assert events[0]['jobId'] == 'abc'


@respx.mock
def test_vision_cancellation_reaches_upstream_without_result(app, tmp_path):
    from app.plugins.vision import analyze
    from app.plugins.security import PluginError
    cfg = {'url':'https://vision.example/v1'}
    respx.post(cfg['url']+'/jobs').mock(return_value=httpx.Response(202,json={'job_id':'abc','state':'queued'}))
    cancel = respx.post(cfg['url']+'/jobs/abc/cancel').mock(return_value=httpx.Response(200,json={'state':'cancel_requested'}))
    with app.app_context():
        stream = analyze(cfg, [], 'test', {}, 'run-1', cancelled=lambda:True)
        next(stream)
        with pytest.raises(PluginError, match='CANCELLED'):
            next(stream)
    assert cancel.called
