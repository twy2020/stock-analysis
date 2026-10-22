import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageBubble from '../src/components/chat/MessageBubble.vue'
import { failureMessage } from '../src/components/chat/failure'

it('distinguishes endpoint, timeout and authentication failures and hides absent retrieval',()=>{
  expect(failureMessage('INVALID_PROVIDER_ENDPOINT')).toContain('接口地址')
  expect(failureMessage('TIMEOUT')).toContain('超时')
  expect(failureMessage('AUTHENTICATION')).toContain('API Key')
  const wrapper=mount(MessageBubble,{props:{showDiagnostics:true,message:{id:'no-rag',role:'ASSISTANT',status:'COMPLETED',content:'回答',citations:[],retrieval:{queryId:'',durationMs:0}}}})
  expect(wrapper.find('.retrieval-meta').exists()).toBe(false)
})

it('shows specific rejection reasons during streaming and after history reload',()=>{
  const base={id:'failed',role:'ASSISTANT' as const,status:'FAILED',content:'',citations:[]}
  const live=mount(MessageBubble,{props:{message:{...base,errorCode:'STOCK_EVIDENCE_REQUIRED'}}})
  expect(live.get('.message-failed').text()).toContain('未取得本轮指标计算证据')
  const saved=mount(MessageBubble,{props:{message:{...base,retrieval:{queryId:'',durationMs:0,errorCode:'INVALID_STOCK_ANSWER'}}}})
  expect(saved.get('.message-failed').text()).toContain('未返回有效的最终答复')
  expect(failureMessage('CANCELLED')).toBe('已停止回复')
  expect(failureMessage('OUTPUT_LIMIT')).toContain('超出本轮上限')
})
