import type { StockChartData, StockAnnotation, StockRow } from '../../types'
import type { EChartsOption } from 'echarts/types/dist/shared'

const colors = ['#167d91', '#d39a2d', '#7466a7', '#3a8c62', '#c75967']
export function stockOption(chart: StockChartData, annotations: StockAnnotation[] = [], dark=false, pinned=false): EChartsOption {
  const muted=dark?'#a8b6bd':'#77818c', grid=dark?'rgba(198,219,219,.10)':'#edf0f2'
  const palette=dark?['#69c9c0','#e9b957','#b9a3e0','#8ac68d','#ed8a98']:colors
  const rows = chart.rows
  const dates = rows.map(r => chart.kind === 'histogram' ? `${(Number(r.low) * 100).toFixed(1)}~${(Number(r.high) * 100).toFixed(1)}%` : String(r[chart.xField??'date']))
  let series: any[] = []
  if (chart.kind === 'candlestick') {
    series.push({ name: '日线', type: 'candlestick', data: rows.map(r => [r.open,r.close,r.low,r.high]),
      itemStyle: { color:'#d95661',color0:'#25937a',borderColor:'#d95661',borderColor0:'#25937a' },
      markPoint: { symbol:'pin',symbolSize:36,label:{fontSize:10}, data: [
        ...annotations.filter(a => !a.endDate && ['open','close','high','low'].includes(a.field)).map(a => ({name:a.label,value:a.label,coord:[a.date,a.value]})),
        ...rows.flatMap(row=>['buyPrice','sellPrice','signalPrice'].filter(field=>typeof row[field]==='number').map(field=>({name:field,value:field==='buyPrice'?'买':field==='sellPrice'?'卖':'信号',coord:[row.date,row[field]],itemStyle:{color:field==='sellPrice'?'#25937a':'#d95661'}}))).slice(-60)
      ] },
      markArea: { itemStyle:{color:'rgba(22,125,145,.09)'},data:annotations.filter(a=>a.endDate).map(a=>[{name:a.label,xAxis:a.date},{xAxis:a.endDate}]) },
    })
  }
  if (chart.kind === 'volume' || chart.kind === 'histogram') {
    series.push({name:chart.kind === 'volume'?'成交量':'事件数',type:'bar',barMaxWidth:16,
      data:rows.map(r=>({value:chart.kind==='volume'?r.volume:r.count,itemStyle:{color:chart.kind==='histogram'?'#167d91':Number(r.close)>=Number(r.open)?'#d95661':'#25937a'}}))})
  }
  if (chart.kind === 'line' || chart.kind === 'candlestick') {
    for (const [i, field] of (chart.fields ?? []).entries()) series.push({name:field,type:'line',showSymbol:false,
      connectNulls:false,data:rows.map(r=>r[field]),lineStyle:{width:1.6,color:palette[i%palette.length]},itemStyle:{color:palette[i%palette.length]},
      markPoint:{symbolSize:32,data:annotations.filter(a=>a.field===field&&!a.endDate).map(a=>({name:a.label,value:a.label,coord:[a.date,a.value]}))}})
  }
  const panelFormatter=(params:any)=>{
    const item=Array.isArray(params)?params[0]:params
    const row=rows[item?.dataIndex]
    if(!row)return ''
    const value=(v:unknown)=>typeof v==='number'?new Intl.NumberFormat('zh-CN',{maximumFractionDigits:4}).format(v):v==null?'--':String(v)
    const cells=chart.kind==='candlestick'?[
      `开 ${value(row.open)}`,`高 ${value(row.high)}`,`收 ${value(row.close)}`,`低 ${value(row.low)}`,
    ]:chart.kind==='volume'?[`成交量 ${value(row.volume)}`]:chart.kind==='histogram'?[`事件数 ${value(row.count)}`]:[]
    cells.push(...(chart.fields??[]).map(field=>`${field} ${value(row[field])}`))
    const lines=[String(item.axisValueLabel??item.axisValue??'')]
    for(let i=0;i<cells.length;i+=2)lines.push(cells.slice(i,i+2).join('    '))
    return lines.join('\n')
  }
  return {animation:false,color:colors,tooltip:{trigger:'axis',renderMode:'richText',confine:true,enterable:false,alwaysShowContent:pinned,
      position:pinned?[8,38]:undefined,backgroundColor:dark?'rgba(32,41,43,.62)':'rgba(255,255,255,.62)',borderWidth:0,
      formatter:pinned?panelFormatter:undefined,padding:pinned?8:10,
      extraCssText:'pointer-events:none',textStyle:{color:dark?'#edf5f4':'#30383d',fontSize:pinned?11:14,lineHeight:pinned?18:22},axisPointer:{type:'cross'}},
    legend:{top:4,left:44,type:'scroll',textStyle:{fontSize:11,color:dark?'#c6d5d4':'#5d6570'}},
    grid:{top:40,left:58,right:18,bottom:58,containLabel:false},
    xAxis:{type:'category',data:dates,boundaryGap:chart.kind!=='line',axisLine:{lineStyle:{color:dark?'#3c4a4c':'#d8dee4'}},axisLabel:{fontSize:10,color:muted}},
    yAxis:{type:'value',scale:true,splitLine:{lineStyle:{color:grid}},axisLabel:{fontSize:10,color:muted,formatter:(v:number)=>chart.unit==='fraction'?`${(v*100).toFixed(1)}%`:Math.abs(v)>=10000?`${(v/10000).toFixed(1)}万`:String(Number(v.toFixed(2)))}},
    dataZoom:chart.kind==='histogram'?[]:[{type:'inside'},{type:'slider',height:18,bottom:12,borderColor:'transparent',backgroundColor:dark?'rgba(200,225,222,.04)':'transparent',textStyle:{color:muted},dataBackground:{lineStyle:{color:muted},areaStyle:{color:dark?'#617b79':'#bed3e2'}},fillerColor:dark?'rgba(112,210,184,.12)':'rgba(22,125,145,.12)',handleSize:'90%'}],series}
}

export function csvRows(rows: StockRow[]): string {
  const keys = [...new Set(rows.flatMap(r=>Object.keys(r)))]
  const escape = (value: unknown) => {
    let text = value == null ? '' : String(value)
    if (typeof value === 'string' && /^[\s]*[=+\-@]/.test(text)) text = "'"+text
    return `"${text.replaceAll('"','""')}"`
  }
  return '\uFEFF'+[keys.map(escape).join(','),...rows.map(r=>keys.map(k=>escape(r[k])).join(','))].join('\r\n')
}
