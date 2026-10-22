import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { renderMarkdown } from '../src/components/chat/renderMarkdown'
import WebSourceIcons from '../src/components/chat/WebSourceIcons.vue'
import { workRows } from '../src/components/chat/workProcess'

const source={id:'web_example',url:'https://example.com/report',title:'公告',domain:'example.com',engines:['bing'],read:true}
it('preserves Markdown web links even when numeric RAG citations exist',()=>{
  const html=renderMarkdown('事实[1](https://example.com/report)，文档[1]',[1])
  expect(html).toContain('href="https://example.com/report"')
  expect(html).toContain('target="_blank"')
  expect(html).toContain('noopener noreferrer')
  expect(html).toContain('data-citation-rank="1"')
  expect(renderMarkdown('[恶意](javascript:alert(1))')).not.toContain('href="javascript:')
})
it('carries sources into the paired event and falls back when its icon fails',async()=>{
  const rows=workRows([{stage:'TOOL_EXECUTING',operationId:'1',status:'RUNNING'},
    {stage:'TOOL_COMPLETED',operationId:'1',status:'COMPLETED',sources:[source]}],false,0,false)
  expect(rows).toHaveLength(1)
  expect(rows[0].sources).toEqual([source])
  const wrapper=mount(WebSourceIcons,{props:{sources:[source]}})
  expect(wrapper.get('a').attributes('href')).toBe(source.url)
  expect(wrapper.get('img').attributes('src')).toBe('https://example.com/favicon.ico')
  await wrapper.get('img').trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('svg').exists()).toBe(true)
})
