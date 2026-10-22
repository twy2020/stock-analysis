import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { api } from '../src/api/client'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../src/api/client', () => ({ api: vi.fn((path: string) => {
  if (path.endsWith('/settings/model')) return Promise.resolve({backend:'local'})
  if (path.endsWith('/settings/rag')) return Promise.resolve({ baseUrl: 'https://rag.internal', apiKeyConfigured: true, timeoutSeconds: 20 })
  if (path.endsWith('/providers')) return Promise.resolve([{ id:'p1', providerType:'DEEPSEEK', name:'DeepSeek', baseUrl:'https://model/v1', status:'ACTIVE', accounts:[{ id:'a1', name:'主账号', baseUrl:'https://model/v1', model:'deepseek-chat', concurrencyLimit:2, weight:1, status:'ACTIVE', apiKeyConfigured:true }] }])
  if (path.endsWith('/users')) return Promise.resolve([{ id:'u1', username:'admin', role:'ADMIN', status:'ACTIVE', passwordChangeRequired:false, lastLoginAt:null }])
  if (path.endsWith('/health')) return Promise.resolve({ rag:{status:'UP',latencyMs:12}, providers:[] })
  if (path.endsWith('/stats')) return Promise.resolve({ ragRequests:4, providerRequests:5, providerFailures:1, tokens:320, averageProviderLatencyMs:180, activeUsers:1 })
  return Promise.resolve({})
}) }))

import AdminView from '../src/views/AdminView.vue'

it('keeps an empty provider visible so its first account can be added',async()=>{
  const previous=vi.mocked(api).getMockImplementation()!
  vi.mocked(api).mockImplementation((path:string,...args:any[])=>path.endsWith('/providers')?Promise.resolve([{id:'empty',name:'Empty Provider',providerType:'OPENAI_COMPATIBLE',baseUrl:'https://example.com/v1',status:'ACTIVE',accounts:[]}]):previous(path,...args) as any)
  const wrapper=mount(AdminView)
  try{
    await flushPromises()
    await wrapper.get('.admin-tabs button:nth-child(3)').trigger('click')
    await flushPromises()
    expect(wrapper.get('.data-table').text()).toContain('Empty Provider')
  }finally{wrapper.unmount();vi.mocked(api).mockImplementation(previous)}
})

describe('admin workspace', () => {
  it('uses dense rows and keeps provider creation in an explicit modal', async () => {
    const wrapper = mount(AdminView)
    await flushPromises()
    expect(wrapper.text()).toContain('RAG 请求')
    expect(wrapper.text()).toContain('4')
    await wrapper.get('.admin-tabs button:nth-child(3)').trigger('click')
    await flushPromises()
    expect(wrapper.get('.data-table').text()).toContain('deepseek-chat')
    expect(wrapper.get('.data-table').text()).toContain('https://model/v1')
    await wrapper.get('.row-actions .text-button').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('编辑模型账号')
    expect(wrapper.get('input[type="password"]').attributes('placeholder')).toContain('留空')
    await wrapper.get('[title="关闭"]').trigger('click')
    await wrapper.findAll('.compact-button')[0].trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('[role="dialog"]').text()).toContain('添加模型账号')
  })

  it('discovers chat models for a custom OpenAI-compatible provider and exposes manual pricing', async () => {
    vi.mocked(api).mockImplementation((path: string) => {
      if (path.endsWith('/settings/model')) return Promise.resolve({backend:'local'}) as any
      if (path.endsWith('/models/discover')) return Promise.resolve({ models: [
        { id: 'chat-large', price: null },
      ], fetchedAt: '2026-09-25T00:00:00Z' }) as any
      if (path.endsWith('/settings/rag')) return Promise.resolve({ baseUrl: '', apiKeyConfigured: false, timeoutSeconds: 20 }) as any
      if (path.endsWith('/providers')) return Promise.resolve([]) as any
      if (path.endsWith('/users')) return Promise.resolve([]) as any
      if (path.endsWith('/health')) return Promise.resolve({ rag: { status: 'NOT_CONFIGURED', latencyMs: null }, providers: [] }) as any
      if (path.endsWith('/stats')) return Promise.resolve({ ragRequests: 0, providerRequests: 0, providerFailures: 0, tokens: 0, averageProviderLatencyMs: 0, activeUsers: 0 }) as any
      return Promise.resolve({}) as any
    })
    const wrapper = mount(AdminView)
    await flushPromises()
    await wrapper.get('.admin-tabs button:nth-child(3)').trigger('click')
    await flushPromises()
    await wrapper.findAll('.compact-button').at(-1)!.trigger('click')
    await wrapper.get('[data-testid="provider-type"]').setValue('OPENAI_COMPATIBLE')
    await wrapper.get('[data-testid="provider-url"]').setValue('https://custom.example/v1')
    await wrapper.get('[data-testid="provider-key"]').setValue('secret')
    await wrapper.get('[data-testid="discover-models"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="model-catalog"]').text()).toContain('chat-large')
    await wrapper.get('[data-testid="model-choice-chat-large"]').trigger('click')
    expect((wrapper.get('[data-testid="provider-model"]').element as HTMLInputElement).value).toBe('chat-large')
    expect(wrapper.text()).toContain('暂无报价')
    expect(wrapper.find('[data-testid="manual-price"]').exists()).toBe(true)
  })
})

it('keeps navigation and stats usable while connection checks are pending, and saves only the changed user', async () => {
  vi.mocked(api).mockClear()
  vi.mocked(api).mockImplementation((path: string) => {
    if (path.endsWith('/settings/model')) return Promise.resolve({backend:'local'}) as any
    if(path.endsWith('/health')) return new Promise(()=>{}) as any
    if(path.endsWith('/stats')) return Promise.resolve({ragRequests:42,providerRequests:10,providerFailures:0,tokens:50,averageProviderLatencyMs:20,activeUsers:1}) as any
    if(path.endsWith('/users')) return Promise.resolve([{id:'u1',username:'tester',role:'USER',status:'ACTIVE',passwordChangeRequired:false,lastLoginAt:null}]) as any
    return Promise.resolve({}) as any
  })
  const wrapper=mount(AdminView)
  await flushPromises()
  expect(wrapper.find('.console-skeleton').exists()).toBe(false)
  expect(wrapper.text()).toContain('42')
  await wrapper.findAll('.admin-tabs button').find(button=>button.text()==='用户')!.trigger('click')
  await flushPromises()
  expect(wrapper.get('.data-table').text()).toContain('tester')
  vi.mocked(api).mockClear()
  await wrapper.get('.data-table .text-button').trigger('click')
  await flushPromises()
  expect(wrapper.get('.data-table').text()).toContain('停用')
  expect(vi.mocked(api).mock.calls.map(call=>call[0])).toEqual(['/api/v1/admin/users/u1'])
  await wrapper.get('.admin-tabs button:nth-child(1)').trigger('click')
  await wrapper.findAll('.admin-tabs button').find(button=>button.text()==='用户')!.trigger('click')
  expect(vi.mocked(api).mock.calls.filter(call=>call[0].includes('/users'))).toHaveLength(1)
  wrapper.unmount()
})
