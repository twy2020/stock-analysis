import { mount, flushPromises } from '@vue/test-utils'
import { expect,it,vi,afterEach } from 'vitest'
import AdminAudit from '../src/components/AdminAudit.vue'
afterEach(()=>vi.unstubAllGlobals())
it('shows citation failure evidence separately from successful model calls',async()=>{
 const urls:string[]=[]
 vi.stubGlobal('fetch',vi.fn(async(url)=>{urls.push(String(url));return Response.json({items:[{id:'e',kind:'exception',action:'chat.answer_failed',status:'FAILED',username:'user',runId:'r',createdAt:'2026-09-29T06:00:00Z',details:{errorCategory:'INVALID_CITATION',errorCode:'INVALID_CITATION',generationCompleted:true,invalidLabels:[3],sourceCount:0,question:'继续解释',answer:'回答[3]',answerLength:5,recentEvents:[{stage:'RESPONSE_STREAMING',elapsedMsTotal:1000}]}}],total:1,pageSize:30,summary:{counts:{FAILED:1},averageMs:1000}})}))
 const wrapper=mount(AdminAudit);await flushPromises()
 await wrapper.findAll('.audit-kinds button').find(b=>b.text()==='问答异常')!.trigger('click');await flushPromises()
 expect(urls.at(-1)).toContain('kind=exception')
 expect(wrapper.text()).toContain('引用校验失败')
 await wrapper.get('tbody .text-button').trigger('click')
 const detail=wrapper.get('[role="dialog"]')
 expect(detail.text()).toContain('模型输出已结束，后续处理失败')
 expect(detail.text()).toContain('无效引用编号')
 expect(detail.text()).toContain('异常时的回答快照')
 expect(detail.text()).toContain('RESPONSE_STREAMING');wrapper.unmount()
})
it('rejects reversed dates without requesting and resets filters',async()=>{
 const fetcher=vi.fn(async()=>Response.json({items:[],total:0,pageSize:30,summary:{counts:{},averageMs:0}}));vi.stubGlobal('fetch',fetcher)
 const wrapper=mount(AdminAudit);await flushPromises()
 const dates=wrapper.findAll('input[type="datetime-local"]');await dates[0].setValue('2026-09-28T10:00');await dates[1].setValue('2026-09-27T10:00')
 await wrapper.get('form').trigger('submit');await flushPromises();expect(fetcher).toHaveBeenCalledTimes(1);expect(wrapper.get('[role="alert"]').text()).toContain('开始时间不能晚于结束时间')
 await wrapper.findAll('button').find(button=>button.text()==='重置')!.trigger('click');await flushPromises();expect(fetcher).toHaveBeenCalledTimes(2);expect(wrapper.find('[role="alert"]').exists()).toBe(false);wrapper.unmount()
})
it('filters paginated logs and opens meaningful request and rotation details',async()=>{
 const urls:string[]=[]
 vi.stubGlobal('fetch',vi.fn(async(url)=>{urls.push(String(url));return Response.json({items:[{id:'a',kind:'model',action:'chat.completions',username:'alice',status:'FAILED',runId:'r',latencyMs:1500,createdAt:'2026-09-28T08:00:00Z',details:{provider:'测试供应商',account:'备用',model:'chat-model',rotated:true,previousAccount:'主账号',rotationReason:'RATE_LIMIT',errorCategory:'TIMEOUT',httpStatus:504,firstTokenMs:250}}],total:31,pageSize:30,summary:{counts:{FAILED:1},averageMs:1500}})}))
 const wrapper=mount(AdminAudit);await flushPromises()
 expect(wrapper.text()).toContain('测试供应商 / 备用')
 await wrapper.get('input[aria-label="搜索日志"]').setValue('alice')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(urls.at(-1)).toContain('q=alice')
 await wrapper.get('tbody .text-button').trigger('click')
 expect(wrapper.get('[role="dialog"]').text()).toContain('供应商限流')
 expect(wrapper.get('[role="dialog"]').text()).toContain('请求超时')
 expect(wrapper.get('[role="dialog"]').text()).toContain('0.25 秒')
 await wrapper.get('[aria-label="关闭详情"]').trigger('click')
 const next=wrapper.findAll('.audit-pagination button').at(-1)!
 await next.trigger('click');await flushPromises();expect(urls.at(-1)).toContain('page=2')
})
