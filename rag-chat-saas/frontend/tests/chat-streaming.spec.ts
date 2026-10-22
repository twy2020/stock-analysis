import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { useChatStore } from '../src/stores/chat'
import MessageBubble from '../src/components/chat/MessageBubble.vue'
import ChatView from '../src/views/ChatView.vue'
import { createMemoryHistory, createRouter } from 'vue-router'

afterEach(() => { useChatStore().leavePage(); vi.unstubAllGlobals() })

const run = { id: 'run', conversationId: 'c1', userMessageId: 'u1', assistantMessageId: 'a1', status: 'RUNNING' }
const messages = [{ id:'u1', role:'USER', content:'问题', status:'COMPLETED', citations:[] }, { id:'a1', role:'ASSISTANT', content:'', status:'STREAMING', citations:[] }]

it('keeps existing message nodes visible while polling a completed conversation', async () => {
  setActivePinia(createPinia())
  const chat = useChatStore()
  const conversation = { id: 'c1', title: '问题', knowledgeBaseId: 'kb1', createdAt: '', updatedAt: '' }
  chat.activeConversation = conversation
  chat.messages = [{ id:'a1', role:'ASSISTANT', content:'完整回答', status:'COMPLETED', citations:[] }]
  const wrapper = mount(defineComponent({ setup: () => () => chat.messages.map(message => h(MessageBubble, { key: message.id, message })) }))
  const original = wrapper.get('.message-row').element
  let release!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/conversations')) return Response.json([{ ...conversation, completedRunId: 'run' }])
    if (url.endsWith('/messages')) return Response.json(chat.messages)
    return new Promise<Response>(resolve => { release = resolve })
  }))
  const refresh = chat.refreshConversations()
  await flushPromises()
  expect(wrapper.find('.message-row').exists()).toBe(true)
  release(Response.json({ ...conversation, completedRunId:'run' }))
  await refresh
  await nextTick()
  expect(wrapper.get('.message-row').element).toBe(original)
  wrapper.unmount()
})

it('sends the composer thinking checkbox selection with the question', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const chat = useChatStore()
  vi.spyOn(chat, 'load').mockResolvedValue()
  chat.reasoningAvailable = true
  chat.selectedKnowledgeBaseId = 'kb1'
  chat.knowledgeBases = [{ id: 'kb1', name: '规范库', versionNumber: 1, publicationRevision: 1 }]
  chat.activeConversation = { id: 'c1', title: '问题', knowledgeBaseId: 'kb1', createdAt: '', updatedAt: '' }
  const requests: Record<string, unknown>[] = []
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    if (url.endsWith('/runs')) { requests.push(JSON.parse(options.body)); return Response.json(run) }
    if (url.endsWith('/messages')) return Response.json(messages)
    if (url.endsWith('/conversations')) return Response.json([])
    return new Response('event: complete\ndata: {"content":"回答","citations":[]}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  }))
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: ChatView }] })
  const wrapper = mount(ChatView, { global: { plugins: [pinia, router] } })
  ;(wrapper.get('.message-transcript').element as HTMLElement).scrollTo = vi.fn()
  const checkbox = wrapper.get('input[aria-label="深度思考"]')
  expect(checkbox.attributes('disabled')).toBeUndefined()
  expect((checkbox.element as HTMLInputElement).checked).toBe(false)
  await checkbox.setValue(true)
  await wrapper.get('textarea').setValue('如何确定设计压力')
  await wrapper.get('form.composer').trigger('submit')
  await flushPromises()
  expect(requests[0]).toMatchObject({ content: '如何确定设计压力', reasoningEnabled: true })
  await checkbox.setValue(false)
  await wrapper.get('textarea').setValue('再解释一下')
  await wrapper.get('form.composer').trigger('submit')
  await flushPromises()
  expect(requests[1]).toMatchObject({ content: '再解释一下', reasoningEnabled: false })
  wrapper.unmount()
})

it('submits stock questions without a knowledge base when RAG is disabled', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const chat = useChatStore()
  vi.spyOn(chat, 'load').mockResolvedValue()
  const send = vi.spyOn(chat, 'send').mockResolvedValue(true)
  chat.ragEnabled = false
  chat.selectedKnowledgeBaseId = ''
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({enabled:false})))
  const router = createRouter({history:createMemoryHistory(),routes:[{path:'/',component:ChatView}]})
  const wrapper = mount(ChatView, {global:{plugins:[pinia,router]}})
  expect(wrapper.find('input[aria-label="RAG"]').exists()).toBe(false)
  await wrapper.get('textarea').setValue('分析平安银行')
  expect(wrapper.get('button[aria-label="发送"]').attributes('disabled')).toBeUndefined()
  await wrapper.get('form.composer').trigger('submit')
  await flushPromises()
  expect(send).toHaveBeenCalledWith('分析平安银行',{imageIds:[]})
  wrapper.unmount()
})

it('updates the visible stage and answer from SSE before the response completes', async () => {
  setActivePinia(createPinia())
  const chat = useChatStore()
  chat.selectedKnowledgeBaseId = 'kb1'
  chat.activeConversation = { id: 'c1', title: '问题', knowledgeBaseId: 'kb1', createdAt: '', updatedAt: '' }
  let stream!: ReadableStreamDefaultController<Uint8Array>
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    if (url.endsWith('/runs')) return Response.json(run)
    if (url.endsWith('/messages')) return Response.json(messages)
    if (url.endsWith('/conversations')) return Response.json([])
    return new Response(new ReadableStream({ start(c) { stream = c } }))
  }))
  const wrapper = mount(defineComponent({ setup: () => () => chat.messages[1]
    ? h(MessageBubble, { message: chat.messages[1], showDiagnostics: true }) : h('div') }))
  const pending = chat.send('设计压力如何确定')
  await flushPromises()
  const emit = async (event: string, data: unknown) => {
    stream.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))
    await flushPromises()
    if (event === 'delta' || event === 'reasoning') await new Promise(resolve => setTimeout(resolve, 280))
    await nextTick()
  }
  try {
    await emit('progress', { stage: 'SEARCHING' })
    expect(chat.sending).toBe(true)
    expect(wrapper.text()).toContain('正在查找相关内容')
    expect(wrapper.text()).not.toContain('正在连接')
    expect(wrapper.findAll('[role="status"]')).toHaveLength(1)
    await emit('progress', { stage: 'RETRIEVE_FUSED', candidateCount: 20, elapsedMsTotal: 350 })
    await emit('progress', { stage: 'RERANK', candidateCount: 8, elapsedMsTotal: 800 })
    expect(wrapper.get('.work-scroll').text()).not.toContain('20 条')
    expect(wrapper.get('.work-scroll').text()).toContain('8 条')
    await wrapper.get('.reasoning-disclosure').trigger('click')
    expect(wrapper.get('.work-scroll').text()).toContain('20 条')
    await emit('progress', { stage: 'MODEL_REASONING', elapsedMsTotal: 900 })
    await emit('reasoning', { content: '先核对适用范围。' })
    await emit('reasoning', { content: '再比较设计条件。' })
    expect(wrapper.get('.work-reasoning-text').text()).toBe('先核对适用范围。再比较设计条件。')
    await emit('progress', { stage: 'RESPONSE_STREAMING', elapsedMsTotal: 1000 })
    await emit('delta', { content: '设计压力' })
    expect(wrapper.find('.work-scroll').exists()).toBe(true)
    expect(wrapper.get('.work-summary').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.work-reasoning-text').text()).toContain('再比较设计条件')
    expect(chat.sending).toBe(true)
    expect(wrapper.get('.answer-markdown').text()).toBe('设计压力')
    await emit('delta', { content: '按工况确定。' })
    expect(wrapper.get('.answer-markdown').text()).toBe('设计压力按工况确定。')
    expect(wrapper.get('.message-content').element.firstElementChild?.classList.contains('work-process')).toBe(true)
    expect(wrapper.find('ol').exists()).toBe(false)
    await emit('progress', { stage: 'MODEL_NOTE', content: '先检查目录。', elapsedMsTotal: 1200 })
    await emit('answer_reset', {})
    expect(chat.messages[1].content).toBe('')
    expect(wrapper.find('.answer-markdown').exists()).toBe(false)
    expect(wrapper.text()).toContain('先检查目录。')
  } finally {
    await emit('complete', { content: '设计压力按工况确定。', citations: [] })
    await pending
    wrapper.unmount()
  }
})
