import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import FeedbackBubble from '../src/components/FeedbackBubble.vue'
import AdminFeedback from '../src/components/AdminFeedback.vue'
import FeedbackForm from '../src/components/feedback/FeedbackForm.vue'
import { useChatStore } from '../src/stores/chat'

beforeEach(() => {
  setActivePinia(createPinia())
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => vi.unstubAllGlobals())
it('previews an attachment in the page and preserves the message center and draft on close',async()=>{
 vi.stubGlobal('ResizeObserver',class{observe(){} disconnect(){}})
 vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:vi.fn(()=>'blob:preview'),revokeObjectURL:vi.fn()}))
 vi.stubGlobal('fetch',vi.fn(async()=>Response.json({system:0,feedback:0})))
 const wrapper=mount(FeedbackBubble,{props:{draft:''},attachTo:document.body})
 await wrapper.get('[aria-label="消息中心"]').trigger('click');await flushPromises()
 await wrapper.get('textarea').setValue('保留我的反馈')
 const file=new File(['png'],'预览.png',{type:'image/png'})
 await wrapper.get('textarea').trigger('paste',{clipboardData:{items:[{kind:'file',type:file.type,getAsFile:()=>file}],getData:()=>''}})
 await wrapper.get('.feedback-image-preview').trigger('click');await flushPromises()
 const body=new DOMWrapper(document.body)
 expect(body.findAll('dialog[open]')).toHaveLength(2)
 expect(body.get('.image-viewer img').attributes('src')).toBe('blob:preview')
 await body.get('.image-viewer').trigger('cancel');await flushPromises()
 expect(body.findAll('dialog[open]')).toHaveLength(1)
 expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('保留我的反馈')
 expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
 wrapper.unmount()
})
it('ignores an older feedback detail response after another feedback is selected',async()=>{
 const replies:Record<string,(response:Response)=>void>={}
 vi.stubGlobal('fetch',vi.fn((url:string)=>new Promise<Response>(resolve=>{replies[url]=resolve})))
 const wrapper=mount(AdminFeedback,{props:{feedbackId:'old'}});await flushPromises();await wrapper.setProps({feedbackId:'new'});await flushPromises()
 const detail=(id:string)=>({id,username:id,comment:id,conversationTitle:'问题',createdAt:'2026-09-28T00:00:00Z',status:'NEW',images:[],snapshot:{messages:[]}})
 replies['/api/v1/admin/feedback/new'](Response.json(detail('new')));await flushPromises();replies['/api/v1/admin/feedback/old'](Response.json(detail('old')));await flushPromises()
 expect(wrapper.get('.feedback-text').text()).toBe('new');wrapper.unmount()
})

it('accepts pasted images, limits attachments and submits them with feedback', async () => {
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => `blob:${Math.random()}`), revokeObjectURL: vi.fn() }))
  const fetcher = vi.fn().mockResolvedValue(Response.json({ id: 'feedback' }))
  vi.stubGlobal('fetch', fetcher)
  const wrapper = mount(FeedbackForm, { props: { draft: '' } })
  const file = new File(['png'], 'clipboard.png', { type: 'image/png' })
  const clipboardData = { items: [{ kind: 'file', type: file.type, getAsFile: () => file }], getData: () => '' }
  for (let i = 0; i < 4; i++) await wrapper.get('textarea').trigger('paste', { clipboardData })
  expect(wrapper.findAll('.feedback-images img')).toHaveLength(3)
  expect(wrapper.get('[role="alert"]').text()).toContain('最多上传 3 张')
  await wrapper.get('textarea').setValue('粘贴图片测试')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(fetcher.mock.calls[0][1].body.getAll('images')).toHaveLength(3)
  wrapper.unmount()
})

it('captures the visible conversation when opened and submits multipart feedback', async () => {
  const chat = useChatStore()
  chat.activeConversation = { id: 'own', title: '当前对话', knowledgeBaseId: 'kb', createdAt: '', updatedAt: '' }
  chat.messages = [{ id: 'm', role: 'ASSISTANT', status: 'STREAMING', content: '点击时的回复', citations: [] }]
  const fetcher = vi.fn().mockResolvedValue(Response.json({ id: 'feedback' }, { status: 201 }))
  vi.stubGlobal('fetch', fetcher)
  const wrapper = mount(FeedbackForm, { props: { draft: '未发送的问题' } })
  await flushPromises()
  chat.messages[0].content = '继续生成的内容'
  await wrapper.get('textarea').setValue('格式错乱')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  const [url, options] = fetcher.mock.calls[0]
  expect(url).toBe('/api/v1/feedback')
  expect(options.headers.has('Content-Type')).toBe(false)
  expect(options.body.get('conversationId')).toBe('own')
  expect(JSON.parse(options.body.get('snapshot')).messages[0].content).toBe('点击时的回复')
  expect(JSON.parse(options.body.get('snapshot')).draft).toBe('未发送的问题')
  expect(wrapper.emitted('submitted')?.[0]).toEqual(['feedback'])
  wrapper.unmount()
})

it('preserves a failed submission for retry and clears it on account switch', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('连接失败')))
  const wrapper = mount(FeedbackBubble, { props: { draft: '' } })
  await wrapper.get('[aria-label="消息中心"]').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('不能翻页')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe('连接失败')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('不能翻页')
  useChatStore().resetForSession()
  await flushPromises()
  expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
  expect(wrapper.find('textarea').exists()).toBe(false)
  wrapper.unmount()
})

it('allows an admin to open feedback, read the snapshot and update status', async () => {
  const row = { id: 'f', username: 'member', comment: '需要改进', conversationTitle: '问题', createdAt: '2026-09-28T06:00:00Z', status: 'NEW', imageCount: 0 }
  let status='NEW'
  const fetcher = vi.fn(async (url:string,options:any)=>{
    if(url.includes('/stats'))return Response.json({total:1,new:1,reviewing:0,closed:0,unread:0})
    if(options?.method==='PATCH')status=JSON.parse(options.body).status
    if(url.includes('/feedback/f'))return Response.json({...row,status,images:[],replies:[],latestReplyId:0,unread:false,snapshot:{messages:[{role:'USER',content:'当时的问题'}]}})
    return Response.json({items:[row],total:1})
  })
  vi.stubGlobal('fetch', fetcher)
  const wrapper = mount(AdminFeedback)
  await flushPromises()
  await wrapper.get('.text-button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('当时的问题')
  await wrapper.get('.ticket-reply-form .secondary-button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('工单已关闭')
  expect(wrapper.find('.ticket-reply-form').exists()).toBe(false)
  wrapper.unmount()
})
