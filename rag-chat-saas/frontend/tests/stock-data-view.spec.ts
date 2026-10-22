import { expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StockDataTable from '../src/components/stock/StockDataTable.vue'
import StockArtifact from '../src/components/stock/StockArtifact.vue'
import StockSummary from '../src/components/stock/StockSummary.vue'
import { renderableChart } from '../src/components/stock/presentation'
import type { StockRow } from '../src/types'

vi.mock('../src/api/client',()=>({api:vi.fn()}))
import { api } from '../src/api/client'

it('renders no-chart stock directory as a table without chart controls or invented price labels',async()=>{
  const artifact={version:'1',datasetRef:'ds_table',title:'股票目录',rowCount:2,summary:{totalResultRows:2},provenance:{query:{task:'query',source:'stocks'}},warnings:[],charts:[],table:[{code:'000001',name:'平安银行'},{code:'000002',name:'万科A'}]}
  vi.mocked(api).mockResolvedValue(artifact)
  const wrapper=mount(StockArtifact,{props:{artifact,messageId:'m'}})
  await flushPromises()
  expect(wrapper.find('table').text()).toContain('平安银行')
  expect(wrapper.findAll('[role=tab]').map(tab=>tab.text())).not.toContain('图表')
  expect(wrapper.find('[aria-label="导出图表 PNG"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('未复权 · 日线')
})

it('keeps all row fields, filters and sorts loaded records, switches details and emits exact rows',async()=>{
  const rows:StockRow[]=[{code:'000001',close:20},{code:'000002',name:'万科A',close:10}]
  const wrapper=mount(StockDataTable,{props:{rows,total:100}})
  expect(wrapper.findAll('th').map(th=>th.text())).toContain('股票名称')
  await wrapper.findAll('th button').find(button=>button.text()==='收盘价')!.trigger('click')
  expect(wrapper.findAll('tbody tr')[0].text()).toContain('000002')
  await wrapper.get('input').setValue('万科')
  expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  await wrapper.get('[aria-label="记录详情模式"]').trigger('click')
  expect(wrapper.find('dl').text()).toContain('万科A')
  await wrapper.get('[aria-label="引用此行"]').trigger('click')
  expect(wrapper.emitted('reference')![0][0]).toEqual(rows[1])
  expect(wrapper.text()).toContain('已加载 2 / 100 行')
})

it('paginates instead of rendering every loaded row and reports empty data',async()=>{
  const wrapper=mount(StockDataTable,{props:{rows:Array.from({length:45},(_,i)=>({code:String(i)})),total:45}})
  expect(wrapper.findAll('tbody tr')).toHaveLength(20)
  await wrapper.get('[aria-label="下一页"]').trigger('click')
  expect(wrapper.findAll('tbody tr')[0].text()).toContain('20')
  await wrapper.get('input').setValue('missing')
  expect(wrapper.get('[role=status]').text()).toBe('没有匹配的记录')
})

it('renders actual structured summary values and refuses empty or unsupported charts',()=>{
  const wrapper=mount(StockSummary,{props:{summary:{coverage:{complete:false},aggregate:{mean:12.5}}}})
  expect(wrapper.text()).toContain('否')
  expect(wrapper.text()).toContain('12.5')
  expect(renderableChart({kind:'line',rows:[]})).toBe(false)
  expect(renderableChart({kind:'line',rows:[{date:'2026-09-30',close:10}]})).toBe(true)
})
