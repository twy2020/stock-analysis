import { mount,flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { expect,it,vi } from 'vitest'
import { api } from '../src/api/client'
import StockAnalysisWorkspace from '../src/components/stock/StockAnalysisWorkspace.vue'
import StockArtifactView from '../src/components/stock/StockArtifact.vue'
vi.mock('../src/api/client',()=>({api:vi.fn()}))

it('loads another stock from the catalog and keeps its tabs, metrics and date together',async()=>{
  Element.prototype.scrollIntoView=vi.fn()
  const artifact:any={version:'stock-artifact/1',datasetRef:'ds_'+'c'.repeat(32),title:'多股行情',
    summary:{'000001':{lastClose:12},'600000':{lastClose:20}},provenance:{dataAsOf:'2026-09-30'},warnings:[],preview:[],rowCount:2,
    charts:[{kind:'candlestick',title:'平安银行 000001'},{kind:'volume',title:'000001 成交量'},
      {kind:'candlestick',title:'浦发银行 600000'},{kind:'volume',title:'600000 成交量'}]}
  vi.mocked(api).mockResolvedValue({...artifact,table:[],charts:artifact.charts.map((c:any,index:number)=>({...c,rows:[{date:index<2?'2026-09-11':'2026-09-18',close:index<2?12:20}]}))})
  const plot=defineComponent({props:['chart'],template:'<div class="test-plot">{{chart.title}}</div>'})
  const wrapper=mount(StockAnalysisWorkspace,{props:{messages:[{id:'multi',role:'ASSISTANT',content:'',status:'COMPLETED',citations:[],stockArtifacts:[artifact]}],selection:{datasetRef:artifact.datasetRef,index:0}},global:{stubs:{StockPlot:plot}}})
  await flushPromises()
  const target=wrapper.findAll('.analysis-catalog-entry').find(button=>button.attributes('title')==='浦发银行 600000')!
  await target.trigger('click')
  await flushPromises()
  expect(wrapper.get('.test-plot').text()).toBe('浦发银行 600000')
  const tabs=wrapper.findAll('[aria-label="生成的图表"] [role="tab"]')
  expect(tabs).toHaveLength(2)
  expect(tabs.every(tab=>!tab.attributes('title')?.includes('000001'))).toBe(true)
  expect(wrapper.get('.analysis-metrics').text()).toContain('20')
  expect(wrapper.get('.analysis-metrics').text()).not.toContain('12')
  expect(wrapper.get('.analysis-chart-heading').text()).toContain('2026-09-18')
  expect(api).toHaveBeenCalledWith(`/api/v1/stock/messages/multi/artifacts/${artifact.datasetRef}`)
  wrapper.unmount()
})

it('recovers missing historical chart metadata without emitting chart rows',async()=>{
  const artifact:any={version:'stock-artifact/1',datasetRef:'ds_'+'b'.repeat(32),title:'行情',summary:{},
    provenance:{},warnings:[],preview:[],rowCount:1,charts:[]}
  vi.mocked(api).mockResolvedValue({...artifact,table:[{date:'2026-09-30',close:12}],charts:[{kind:'line',title:'布林轨道',fields:['close'],rows:[{date:'2026-09-30',close:12}]}]})
  const wrapper=mount(StockArtifactView,{props:{artifact,messageId:'m'},global:{stubs:{StockPlot:true}}})
  await flushPromises()
  expect(wrapper.emitted('metadata')?.[0]?.[0]).toEqual([{kind:'line',title:'布林轨道'}])
  expect(wrapper.findComponent({name:'StockPlot'}).exists()).toBe(true)
  wrapper.unmount()
})

it('switches generated charts and inserts a reference from engine-owned rows',async()=>{
  Element.prototype.scrollIntoView=vi.fn()
  const artifact:any={version:'stock-artifact/1',datasetRef:'ds_'+'a'.repeat(32),title:'行情',summary:{'000001':{lastClose:12}},
    provenance:{dataAsOf:'2026-09-30'},warnings:[],preview:[],rowCount:1,
    charts:[{kind:'candlestick',title:'日线'},{kind:'volume',title:'成交量'}]}
  const rows=[{date:'2026-09-30',close:12,open:10,high:13,low:9,volume:100}]
  vi.mocked(api).mockResolvedValue({...artifact,table:rows,charts:artifact.charts.map((c:any)=>({...c,rows}))})
  const plot=defineComponent({props:['chart','dark'],template:'<div class="test-plot">{{chart.title}}</div>'})
  const wrapper=mount(StockAnalysisWorkspace,{props:{messages:[{id:'m',role:'ASSISTANT',content:'',status:'COMPLETED',citations:[],stockArtifacts:[artifact]}],selection:{datasetRef:artifact.datasetRef,index:0}},global:{stubs:{StockPlot:plot}}})
  await flushPromises()
  const tabs=wrapper.findAll('[aria-label="生成的图表"] [role="tab"]')
  expect(tabs).toHaveLength(2)
  await tabs[1].trigger('click')
  expect(wrapper.get('.test-plot').text()).toBe('成交量')
  await wrapper.get('[aria-label="引用此行"]').trigger('click')
  expect(wrapper.emitted('reference')?.[0]?.[0]).toContain('[data:'+artifact.datasetRef+']')
  await wrapper.get('[aria-label="关闭全屏分析"]').trigger('click')
  expect(wrapper.emitted('close')).toHaveLength(1)
  wrapper.unmount()
})
