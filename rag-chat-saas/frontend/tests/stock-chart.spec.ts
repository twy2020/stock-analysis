import { describe, it, expect } from 'vitest'
import { stockOption, csvRows } from '../src/components/stock/chart'
import { renderMarkdown } from '../src/components/chat/renderMarkdown'

describe('stock chart', () => {
  it('pins the same transparent panel away from the pointer and restores floating mode',()=>{
    const chart:any={kind:'line',title:'趋势',fields:['close'],rows:[{date:'2026-09-30',close:12}]}
    const fixed:any=stockOption(chart,[],false,true)
    expect(fixed.tooltip.position).toEqual([8,38])
    expect(fixed.tooltip.alwaysShowContent).toBe(true)
    expect(fixed.tooltip.enterable).toBe(false)
    expect(fixed.tooltip.backgroundColor).toBe('rgba(255,255,255,.62)')
    expect(fixed.tooltip.formatter([{dataIndex:0,axisValueLabel:'2026-09-30'}])).toContain('close 12')
    expect(fixed.tooltip.textStyle.fontSize).toBe(11)
    const floating:any=stockOption(chart,[],true,false)
    expect(floating.tooltip.position).toBeUndefined()
    expect(floating.tooltip.alwaysShowContent).toBe(false)
  })
  it('renders legacy bound history references instead of internal JSON',()=>{
    const ref='ds_'+'a'.repeat(32)
    const html=renderMarkdown('结论。历史数据集引用（数值需用stock_dataset在本轮复核）：'+JSON.stringify([{datasetRef:ref,title:'行情查询'}]),[],{}, {[ref]:'行情查询'})
    expect(html).toContain('data-dataset-ref="'+ref+'"')
    expect(html).not.toContain('stock_dataset')
    expect(html).not.toContain('datasetRef')
  })
  it('uses exact engine OHLC and annotation values', () => {
    const option: any = stockOption({kind:'candlestick',title:'K线',unit:'CNY',fields:[],rows:[
      {date:'2026-09-30',open:10,close:12,low:9,high:13,volume:100},
    ]}, [{date:'2026-09-30',field:'close',value:12,label:'事件'}])
    expect(option.series[0].data[0]).toEqual([10,12,9,13])
    expect(option.series[0].markPoint.data[0].coord).toEqual(['2026-09-30',12])
    expect(option.tooltip.renderMode).toBe('richText')
  })
  it('uses event offsets and engine-derived fill markers',()=>{
    const profile:any=stockOption({kind:'line',title:'事件路径',unit:'fraction',xField:'offset',fields:['relativeClose'],rows:[{offset:-1,relativeClose:-.02},{offset:0,relativeClose:0}]})
    expect(profile.xAxis.data).toEqual(['-1','0'])
    const price:any=stockOption({kind:'candlestick',title:'成交',unit:'CNY',rows:[{date:'2026-09-30',open:10,close:12,low:9,high:13,buyPrice:10.01}]})
    expect(price.series[0].markPoint.data[0].coord).toEqual(['2026-09-30',10.01])
  })
  it('exports CSV without executing spreadsheet formulas', () => {
    expect(csvRows([{name:'=SUM(A1)',close:12}])).toContain("'=SUM(A1)")
  })
  it('renders a readable dark analysis chart without changing engine values', () => {
    const option:any=stockOption({kind:'line',title:'净值',unit:'CNY',fields:['equity'],rows:[{date:'2026-09-30',equity:120}]},[],true)
    expect(option.xAxis.axisLabel.color).toBe('#a8b6bd')
    expect(option.series[0].data).toEqual([120])
  })
})
