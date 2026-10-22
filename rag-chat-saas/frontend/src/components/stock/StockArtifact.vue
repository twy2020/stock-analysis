<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { FileDown, ImageDown, Maximize2, Table2, ChartCandlestick, RefreshCw, Database, Quote, Activity } from 'lucide-vue-next'
import { api } from '../../api/client'
import type { StockArtifact, StockChartData, StockRow } from '../../types'
import StockPlot from './StockPlot.vue'
import StockDataTable from './StockDataTable.vue'
import StockSummary from './StockSummary.vue'
import { renderableChart } from './presentation'
import { downloadFile, exportTable } from './files'
const props=defineProps<{artifact:StockArtifact;messageId:string}>()
const emit=defineEmits<{reference:[text:string];rendered:[];analysis:[datasetRef:string,index:number];metadata:[charts:StockArtifact['charts']]}>()
const plot=ref<InstanceType<typeof StockPlot>|null>(null),exporting=ref(false)
const data=ref<StockArtifact|null>(null),error=ref(''),loading=ref(false),view=ref(props.artifact.charts.length?'chart':'table'),selectedChart=ref(0),selectedDate=ref('')
const active=computed(()=>data.value??props.artifact)
const charts=computed(()=>active.value.charts.filter(renderableChart) as StockChartData[])
const hasSummary=computed(()=>Object.keys(active.value.summary).length>0)
const marketSeries=computed(()=>!active.value.provenance.query?.sql&&(active.value.provenance.query?.source??'bars')==='bars')
const symbolSummaries=computed(()=>Object.entries(active.value.summary).filter(([key,value])=>/^\d{6}$/.test(key)&&value&&typeof value==='object'))
const singleSymbol=computed(()=>symbolSummaries.value.length===1?symbolSummaries.value[0]:undefined)
const dataDate=computed(()=>singleSymbol.value?.[1]?.lastDate??active.value.provenance.dataAsOf??'未知')
const rows=computed(()=>data.value?.table??props.artifact.preview??[])
const fields=computed(()=>Array.from(new Set(rows.value.flatMap(row=>Object.keys(row)))).filter(k=>!k.startsWith('_')))
const sourceOpen=ref(false)
const labels:Record<string,string>={lastClose:'收盘价',priceReturn:'区间价格收益',annualizedVolatility:'年化波动率',maxPriceDrawdown:'价格最大回撤',events:'事件样本',rawHits:'原始触发',stocks:'扫描股票',matchedStocks:'命中股票',totalReturn:'策略收益',maxDrawdown:'最大回撤',completedTrades:'完整交易',winRate:'交易胜率',feesPaid:'交易费用',benchmarkReturn:'买入持有收益',observations:'日线数量',finalEquity:'期末权益',totalResultRows:'结果行数'}
const metrics=computed(()=>{
  const summary=active.value.summary
  const nested=singleSymbol.value?.[1]
  const values={...(nested??{}),...summary}
  return Object.entries(values).filter(([k,v])=>labels[k]&&typeof v==='number').slice(0,8).map(([key,value])=>({key,label:labels[key],value:value as number}))
})
const forward=computed(()=>active.value.summary.forward as Record<string,any>|undefined)
function format(value:unknown,key=''){
  if(value==null)return '—'
  if(typeof value==='number'){
    if(/Return|Drawdown|Volatility|Probability|winRate/.test(key))return `${(value*100).toFixed(2)}%`
    return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:4}).format(value)
  }
  return typeof value==='object'?JSON.stringify(value):String(value)
}
async function load(){
  if(loading.value)return
  loading.value=true;error.value=''
  try{
    data.value=await api<StockArtifact>(`/api/v1/stock/messages/${props.messageId}/artifacts/${props.artifact.datasetRef}`)
    emit('metadata',charts.value.map(({kind,title})=>({kind,title})))
    view.value=charts.value.length?'chart':rows.value.length||!hasSummary.value?'table':'summary'
    emit('rendered')
  }
  catch(e){error.value=e instanceof Error?e.message:'数据集加载失败'}finally{loading.value=false}
}
onMounted(load)
function reference(row?:StockRow){
  const date=String(row?.date??selectedDate.value??'')
  const fieldsText=row?fields.value.filter(k=>k!=='date'&&k!=='code'&&k!=='name').slice(0,5).map(k=>`${k}=${format(row[k])}`).join('，'):''
  emit('reference',`[data:${active.value.datasetRef}] ${row?.code??''} ${row?.name??''} ${date} ${fieldsText}`.trim())
}
async function download(){
  exporting.value=true;error.value=''
  try{await exportTable(props.messageId,active.value.datasetRef)}catch(e){error.value=e instanceof Error?e.message:'导出失败'}finally{exporting.value=false}
}
function image(){const url=plot.value?.exportImage();if(url)downloadFile(url,`${active.value.datasetRef}-${Number(selectedChart.value)+1}.png`)}
const queryText=computed(()=>JSON.stringify(active.value.provenance.query??{},null,2))
</script>
<template>
  <section class="stock-artifact" :id="artifact.datasetRef" :aria-label="artifact.title">
    <header class="stock-artifact-header"><div><span class="stock-dataset-tag"><Database :size="12"/> DATASET</span><h3>{{active.title}}</h3></div>
      <div class="stock-artifact-actions"><button title="引用数据" aria-label="引用数据" @click="reference()"><Quote :size="16"/></button><button v-if="charts.length&&view==='chart'" title="导出图表 PNG" aria-label="导出图表 PNG" @click="image"><ImageDown :size="16"/></button><button title="导出查询数据 CSV" aria-label="导出查询数据 CSV" :disabled="exporting||!active.rowCount" @click="download"><FileDown :size="16"/></button><button title="全屏分析" aria-label="全屏分析" @click="emit('analysis',active.datasetRef,Number(selectedChart))"><Maximize2 :size="16"/></button></div>
    </header>
    <div class="stock-source-line"><span>{{singleSymbol?.[0]}} {{singleSymbol?'数据截至':'库截至'}} {{dataDate}}</span><span v-if="symbolSummaries.length>1">{{symbolSummaries.length}} 个对象</span><span v-if="marketSeries">未复权 · 日线</span><button @click="sourceOpen=!sourceOpen">查询来源</button></div>
    <div v-if="metrics.length" class="stock-metrics"><div v-for="metric in metrics" :key="metric.key"><small>{{metric.label}}</small><strong :class="{positive:/Return/.test(metric.key)&&metric.value>0,negative:/Return/.test(metric.key)&&metric.value<0}">{{format(metric.value,metric.key)}}</strong></div></div>
    <div v-if="forward" class="stock-table-scroll"><table class="stock-table"><thead><tr><th>观察期</th><th>有效 n</th><th>上涨概率</th><th>均值</th><th>中位数</th><th>基准均值</th></tr></thead><tbody><tr v-for="(result,period) in forward" :key="period"><td>{{period}} 根</td><td>{{result.n}}</td><td>{{format(result.upProbability,'Probability')}}</td><td>{{format(result.mean,'Return')}}</td><td>{{format(result.median,'Return')}}</td><td>{{format(active.summary.baseline?.[period]?.mean,'Return')}}</td></tr></tbody></table></div>
    <div class="stock-views"><div role="tablist" aria-label="数据视图"><button v-if="charts.length" role="tab" :aria-selected="view==='chart'" @click="view='chart'"><ChartCandlestick :size="15"/>图表</button><button role="tab" :aria-selected="view==='table'" @click="view='table'"><Table2 :size="15"/>数据 <small>{{active.rowCount}}</small></button><button v-if="hasSummary" role="tab" :aria-selected="view==='summary'" @click="view='summary'"><Activity :size="15"/>统计</button></div>
      <select v-if="charts.length>1&&view==='chart'" v-model="selectedChart" aria-label="图表"><option v-for="(chart,index) in charts" :key="index" :value="index">{{chart.title}}</option></select>
    </div>
    <div v-if="loading" class="stock-loading" role="status">正在读取数据集</div>
    <div v-else-if="error" class="stock-load-error" role="alert">{{error}}<button title="重新读取" aria-label="重新读取" @click="load"><RefreshCw :size="16"/></button></div>
    <StockPlot v-else-if="view==='chart'&&charts[selectedChart]" ref="plot" :chart="charts[selectedChart]!" :annotations="active.annotations" @select="selectedDate=$event;reference()"/>
    <StockSummary v-else-if="view==='summary'" :summary="active.summary"/>
    <StockDataTable v-else :rows="rows" :total="active.rowCount" :schema="active.schema" @reference="reference"/>
    <div v-if="sourceOpen" class="stock-source"><dl><dt>数据集</dt><dd>{{active.datasetRef}}</dd><dt>读取时间</dt><dd>{{active.provenance.retrievedAt}}</dd><dt>查询校验</dt><dd>{{active.provenance.queryHash}}</dd></dl><pre>{{queryText}}</pre></div>
    <details v-if="active.warnings.length" class="stock-warnings"><summary>研究口径与限制 · {{active.warnings.length}}</summary><ul><li v-for="warning in active.warnings" :key="warning">{{warning}}</li></ul></details>
  </section>
</template>
