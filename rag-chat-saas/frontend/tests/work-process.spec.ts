import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import WorkProcess from '../src/components/chat/WorkProcess.vue'
import { workRows } from '../src/components/chat/workProcess'
import { progressLabel } from '../src/components/chat/progress'
import type { Message } from '../src/types'

it('marks interrupted active steps failed and uses terminal duration',()=>{
  const rows=workRows([{stage:'AGENT_THINKING',elapsedMsTotal:200},{stage:'PROCESS_FAILED',status:'FAILED',elapsedMsTotal:120500}],false,0,false)
  expect(rows).toHaveLength(2)
  expect(rows[0]).toMatchObject({failed:true,elapsedMs:120300})
  expect(rows[0]?.label).not.toBe('已分析问题')
})

it('does not present queuing or ordinary tool execution as retrieval', () => {
  const rows = workRows([
    { stage: 'QUEUED', elapsedMs: 0 },
    { stage: 'AGENT_THINKING' },
    { stage: 'TOOL_EXECUTING', tool: 'custom_tool' },
    { stage: 'RESPONSE_STREAMING' },
  ], false, 0, false)
  expect(rows.map(row => row.stage)).not.toContain('QUEUED')
  expect(rows.map(row => row.label).join('')).not.toContain('检索')
  expect(progressLabel({ stage: 'UNKNOWN_STAGE' })).not.toContain('检索')
  expect(workRows([{ stage: 'SEARCHING', tool: 'recall' }], true, 0, false)[0]?.label).toBe('正在查阅资料')
})

it('preserves manual event expansion across new events and respects manual collapse', async () => {
  const message: Message = {id:'recent',role:'ASSISTANT',status:'STREAMING',content:'',citations:[],processEvents:Array.from({length:12},()=>({stage:'AGENT_THINKING'}))}
  const wrapper = mount(WorkProcess,{props:{message}})
  expect(wrapper.findAll('.work-scroll .work-row')).toHaveLength(1)
  await wrapper.get('.reasoning-disclosure').trigger('click')
  expect(wrapper.findAll('.work-scroll .work-row')).toHaveLength(12)
  expect(wrapper.get('.work-scroll').classes()).toContain('expanded-history')
  await wrapper.setProps({message:{...message,processEvents:[...message.processEvents!,{stage:'MODEL_REASONING'}]}})
  expect(wrapper.findAll('.work-scroll .work-row')).toHaveLength(13)
  expect(wrapper.get('.reasoning-disclosure').attributes('aria-expanded')).toBe('true')
  await wrapper.get('.reasoning-disclosure').trigger('click')
  expect(wrapper.findAll('.work-scroll .work-row')).toHaveLength(1)
  await wrapper.setProps({message:{...message,processEvents:[...message.processEvents!,{stage:'MODEL_REASONING'},{stage:'TOOL_PREPARING'}]}})
  expect(wrapper.findAll('.work-scroll .work-row')).toHaveLength(1)
  wrapper.unmount()
})

it('keeps manually opened history visible when answering starts and the reply completes', async () => {
  const message:Message={id:'persistent',role:'ASSISTANT',status:'STREAMING',content:'',citations:[],processEvents:[{stage:'AGENT_THINKING'},{stage:'TOOL_PREPARING'}]}
  const wrapper=mount(WorkProcess,{props:{message}})
  await wrapper.get('.reasoning-disclosure').trigger('click')
  const writing={...message,content:'回复',processEvents:[...message.processEvents!,{stage:'RESPONSE_STREAMING'}]}
  await wrapper.setProps({message:writing})
  expect(wrapper.find('.work-history').exists()).toBe(true)
  expect(wrapper.get('.work-summary').attributes('aria-expanded')).toBe('true')
  await wrapper.setProps({message:{...writing,status:'COMPLETED'}})
  expect(wrapper.find('.work-history').exists()).toBe(true)
  await wrapper.get('.work-summary').trigger('click')
  expect(wrapper.find('.work-history').exists()).toBe(false)
  await wrapper.setProps({message:{...message,id:'next'}})
  expect(wrapper.findAll('.work-scroll .work-row')).toHaveLength(1)
  wrapper.unmount()
})
it('names stock computations without misleading zero retrieval counts',()=>{
  expect(progressLabel({stage:'TOOL_COMPLETED',tool:'stock_query',resultCount:0})).toBe('已完成股票分析')
  expect(progressLabel({stage:'TOOL_EXECUTING',tool:'mcp__stock__stock_events'})).toBe('正在执行事件统计')
})

it('removes model-note padding lines without losing paragraph boundaries', () => {
  const rows = workRows([{ stage: 'MODEL_NOTE', content: '\n\n先查阅资料。\n\n\n然后核对。\n\n' }], true, 0, false)
  expect(rows[0]?.label).toBe('先查阅资料。\n\n然后核对。')
})

it('pairs repeated tool calls by operation id and measures live and completed durations', () => {
  const events = [
    { stage: 'SEARCHING', operationId: 'a', tool: 'recall', status: 'RUNNING', atMs: 1000, elapsedMsTotal: 0 },
    { stage: 'RERANK_RUNNING', parentOperationId: 'a', atMs: 2000, elapsedMsTotal: 1000 },
    { stage: 'TOOL_COMPLETED', operationId: 'a', tool: 'recall', elapsedMs: 1800, resultCount: 8, elapsedMsTotal: 1800 },
    { stage: 'SEARCHING', operationId: 'b', tool: 'recall', status: 'RUNNING', atMs: 3000, elapsedMsTotal: 2000 },
  ]
  const rows = workRows(events, true, 4500, true)
  expect(rows).toHaveLength(3)
  expect(rows[0]).toMatchObject({ elapsedMs: 1800, running: false, label: '已获取相关内容 · 8 条' })
  expect(rows[2]).toMatchObject({ elapsedMs: 1500, running: true })
  const publicRows = workRows(events, true, 4500, false)
  expect(publicRows).toHaveLength(2)
  expect(publicRows.map(r => r.label).join('')).not.toContain('8')
})

it('archives work on answer start, keeps reasoning last and closed, and permits reopening', async () => {
  vi.useFakeTimers()
  const message: Message = { id: 'a', role: 'ASSISTANT', content: '', status: 'STREAMING', citations: [],
    reasoningContent: '详细思考'.repeat(100), processEvents: [{ stage: 'AGENT_THINKING', atMs: Date.now(), elapsedMsTotal: 0 }] }
  const wrapper = mount(WorkProcess, { props: { message, diagnostics: true } })
  expect(wrapper.find('.work-shimmer').exists()).toBe(false)
  expect(wrapper.find('details').exists()).toBe(false)
  expect(wrapper.find('.work-reasoning-text').exists()).toBe(false)
  await wrapper.setProps({message:{...message,processEvents:[{stage:'MODEL_REASONING',atMs:Date.now(),elapsedMsTotal:0}]}})
  expect(wrapper.find('.thinking-live .work-reasoning-text').exists()).toBe(true)
  expect(wrapper.get('.work-reasoning-text').text()).toBe(message.reasoningContent)
  expect(wrapper.find('.stream-reveal').exists()).toBe(false)
  expect(wrapper.get('.work-reasoning-text').element.childElementCount).toBe(0)
  await wrapper.setProps({message:{...message,processEvents:[{stage:'SEARCHING',atMs:Date.now(),elapsedMsTotal:500}]}})
  expect(wrapper.find('.work-reasoning-text').exists()).toBe(false)
  await wrapper.setProps({ message: { ...message, content: '正式回复', processEvents: [...message.processEvents!, { stage: 'RESPONSE_STREAMING', atMs: Date.now(), elapsedMsTotal: 1250 }] } })
  expect(wrapper.find('.work-history').exists()).toBe(false)
  expect(wrapper.get('.work-summary').text()).toContain('1.3 秒')
  await wrapper.get('.work-summary').trigger('click')
  expect(wrapper.find('.work-history').exists()).toBe(true)
  await wrapper.setProps({ message: { ...message, status: 'COMPLETED', content: '正式回复', processEvents: [...message.processEvents!, {stage:'PROCESS_COMPLETED',elapsedMsTotal:2000}] } })
  expect(wrapper.find('.work-shimmer').exists()).toBe(false)
  wrapper.unmount()
  expect(vi.getTimerCount()).toBe(0)
  vi.useRealTimers()
})
