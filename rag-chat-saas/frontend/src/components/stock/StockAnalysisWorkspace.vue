<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { X, ImageDown, FileDown, RotateCcw, Quote, ChartCandlestick, Database, Activity, Info, RefreshCw, PanelLeft, ChevronRight, Search } from 'lucide-vue-next'
import { api } from '../../api/client'
import type { Message, StockArtifact, StockChartData, StockRow } from '../../types'
import StockPlot from './StockPlot.vue'
import StockDataTable from './StockDataTable.vue'
import StockSummary from './StockSummary.vue'
import { renderableChart } from './presentation'
import ThemeToggle from '../ThemeToggle.vue'
import { downloadFile, exportTable } from './files'
import { analysisCatalog } from './analysisCatalog'

const props=defineProps<{messages:Message[];selection:{datasetRef:string;index:number}}>()
const emit=defineEmits<{close:[];reference:[text:string]}>()
const loaded=ref<Record<string,StockArtifact>>({}), selected=ref(''), detail=ref('data'), error=ref(''), pending=ref(false), exporting=ref(false)
const plot=ref<InstanceType<typeof StockPlot>|null>(null), tabList=ref<HTMLElement|null>(null)
let revision=0
const catalog=computed(()=>analysisCatalog(props.messages))
const entries=computed(()=>catalog.value.entries)
const catalogOpen=ref(typeof matchMedia==='function'?!matchMedia('(max-width: 900px)').matches:true), catalogSearch=ref(''), closedGroups=ref<string[]>([])
const visibleGroups=computed(()=>catalog.value.groups.map(group=>({...group,entries:group.entries.filter(entry=>
  `${group.title} ${entry.title} ${entry.artifact.title}`.toLocaleLowerCase().includes(catalogSearch.value.trim().toLocaleLowerCase()))})).filter(group=>group.entries.length))
const current=computed(()=>entries.value.find(e=>e.key===selected.value)??entries.value[0])
const currentTabs=computed(()=>entries.value.filter(e=>e.groupId===current.value?.groupId&&e.artifact.datasetRef===current.value?.artifact.datasetRef))
const currentGroup=computed(()=>catalog.value.groups.find(g=>g.id===current.value?.groupId))
function toggleGroup(id:string){closedGroups.value=closedGroups.value.includes(id)?closedGroups.value.filter(v=>v!==id):[...closedGroups.value,id]}
onMounted(()=>document.querySelector<HTMLButtonElement>('[aria-label="关闭全屏分析"]')?.focus({preventScroll:true}))
const data=computed(()=>current.value?loaded.value[current.value.artifact.datasetRef]:undefined)
const chart=computed(()=>{
  const value=data.value?.charts[current.value?.index??0]
  return current.value?.kind!=='table'&&value&&renderableChart(value)?value as StockChartData:undefined
})
const tablePrimary=computed(()=>current.value?.kind==='table'||!!data.value&&!chart.value)
const actualDataAsOf=computed(()=>{
  const summary=data.value?.summary??current.value?.artifact.summary??{}
  const code=current.value?.groupId.startsWith('stock:')?current.value.groupId.slice(6):''
  return chart.value?.rows?.at(-1)?.date??summary.coverage?.ranges?.[code]?.last??summary[code]?.lastDate??data.value?.provenance.dataAsOf??current.value?.artifact.provenance.dataAsOf??'未知'
})
const rows=computed(()=>data.value?.table??[])
const labels:Record<string,string>={lastClose:'收盘价',priceReturn:'区间收益',annualizedVolatility:'年化波动率',maxPriceDrawdown:'价格最大回撤',events:'事件样本',completedTrades:'完整交易',totalReturn:'策略收益',maxDrawdown:'最大回撤',winRate:'交易胜率',benchmarkReturn:'买入持有',finalEquity:'期末权益',observations:'交易日',matchedStocks:'命中股票'}
function format(value:unknown,key=''){
  if(value==null)return '--'
  if(typeof value==='number')return /Return|Drawdown|Volatility|Probability|winRate|^return\d+$/.test(key)?`${(value*100).toFixed(2)}%`:new Intl.NumberFormat('zh-CN',{maximumFractionDigits:4}).format(value)
  return typeof value==='object'?JSON.stringify(value):String(value)
}
const metrics=computed(()=>{
  const summary=data.value?.summary??current.value?.artifact.summary??{}
  const code=current.value?.groupId.startsWith('stock:')?current.value.groupId.slice(6):''
  const stock=code?summary[code]:Object.entries(summary).find(([k,v])=>/^\d{6}$/.test(k)&&v&&typeof v==='object')?.[1]
  return Object.entries({...stock,...summary}).filter(([k,v])=>labels[k]&&typeof v==='number').slice(0,6)
})
const indicators=computed(()=>{
  const last=chart.value?.rows?.at(-1)
  return (chart.value?.fields??[]).map(field=>({field,value:last?.[field]}))
})
async function load(){
  const entry=current.value;if(!entry)return
  const request=++revision;error.value=''
  if(loaded.value[entry.artifact.datasetRef]){pending.value=false;return}
  pending.value=true
  try{
    const value=await api<StockArtifact>(`/api/v1/stock/messages/${entry.messageId}/artifacts/${entry.artifact.datasetRef}`)
    loaded.value[entry.artifact.datasetRef]=value
  }catch(e){if(request===revision)error.value=e instanceof Error?e.message:'数据读取失败'}
  finally{if(request===revision)pending.value=false}
}
watch(()=>props.selection,selection=>{selected.value=`${selection.datasetRef}:${selection.index}`},{immediate:true})
watch(()=>current.value?.artifact.datasetRef,()=>void load(),{immediate:true})
function select(key:string){selected.value=key;if(typeof matchMedia==='function'&&matchMedia('(max-width: 900px)').matches)catalogOpen.value=false;nextTick(()=>tabList.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'}))}
watch(()=>current.value?.groupId,id=>{if(id)closedGroups.value=closedGroups.value.filter(v=>v!==id)})
watch(tablePrimary,value=>{detail.value=value?'indicators':'data'},{immediate:true})
function tabKeys(event:KeyboardEvent){
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return
  event.preventDefault()
  const index=currentTabs.value.findIndex(e=>e.key===selected.value),count=currentTabs.value.length
  const next=event.key==='Home'?0:event.key==='End'?count-1:(index+(event.key==='ArrowRight'?1:-1)+count)%count
  const entry=currentTabs.value[next];if(entry){select(entry.key);nextTick(()=>tabList.value?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus())}
}
async function saveTable(){
  if(!current.value||exporting.value)return
  exporting.value=true;error.value=''
  try{await exportTable(current.value.messageId,current.value.artifact.datasetRef)}
  catch(e){error.value=e instanceof Error?e.message:'表格导出失败'}finally{exporting.value=false}
}
function saveImage(){
  const url=plot.value?.exportImage()
  if(url&&current.value)downloadFile(url,`${current.value.artifact.datasetRef}-${current.value.index+1}.png`)
}
function reference(date?:string){if(current.value)emit('reference',`[data:${current.value.artifact.datasetRef}]${date?' '+date:''}`)}
function referenceRow(row:StockRow){if(current.value)emit('reference',`[data:${current.value.artifact.datasetRef}] ${Object.entries(row).filter(([key])=>!key.startsWith('_')).slice(0,8).map(([key,value])=>`${key}=${format(value,key)}`).join('，')}`)}
</script>
<template>
  <section class="stock-analysis-workspace" :class="{'catalog-collapsed':!catalogOpen}" aria-label="全屏图表分析">
    <header class="analysis-heading"><div class="analysis-identity"><button class="analysis-icon" title="图表目录" aria-label="切换图表目录" :aria-expanded="catalogOpen" @click="catalogOpen=!catalogOpen"><PanelLeft :size="17"/></button><ChartCandlestick :size="19"/><strong>股票分析</strong><span>RESEARCH DESK</span></div><div class="analysis-actions"><ThemeToggle/><button class="analysis-icon" aria-label="关闭全屏分析" title="退出全屏分析" @click="emit('close')"><X :size="19"/></button></div></header>
    <aside v-if="catalogOpen" class="analysis-catalog" aria-label="当前对话图表目录">
      <div class="analysis-catalog-heading"><strong>对话图表</strong><small>{{entries.length}}</small></div>
      <label class="analysis-catalog-search"><Search :size="13"/><input v-model="catalogSearch" type="search" aria-label="搜索图表" placeholder="搜索股票或图表"/></label>
      <div class="analysis-catalog-scroll">
        <section v-for="group in visibleGroups" :key="group.id" class="analysis-catalog-group">
          <button class="analysis-group-toggle" :aria-expanded="!closedGroups.includes(group.id)" @click="toggleGroup(group.id)"><ChevronRight :size="13" :class="{expanded:!closedGroups.includes(group.id)}"/><span>{{group.title}}</span><small>{{group.entries.length}}</small></button>
          <div v-if="!closedGroups.includes(group.id)||catalogSearch" class="analysis-group-entries">
            <template v-for="(entry,index) in group.entries" :key="entry.key">
              <div v-if="!index||group.entries[index-1].artifact.datasetRef!==entry.artifact.datasetRef" class="analysis-query-label">第 {{entry.round}} 轮 · {{entry.artifact.title}}</div>
              <button class="analysis-catalog-entry" :aria-current="current?.key===entry.key?'true':undefined" :title="entry.title" @click="select(entry.key)"><Database v-if="entry.kind==='table'" :size="13"/><ChartCandlestick v-else :size="13"/><span>{{entry.label}}</span></button>
            </template>
          </div>
        </section>
        <p v-if="!visibleGroups.length" class="analysis-catalog-empty">没有匹配的图表</p>
      </div>
    </aside>
    <div class="analysis-main">
    <div class="analysis-current-group">{{currentGroup?.title}}<span>第 {{current?.round}} 轮 · {{current?.artifact.title}}</span></div>
    <nav ref="tabList" class="analysis-chart-tabs" role="tablist" aria-label="生成的图表" @keydown="tabKeys">
      <button v-for="entry in currentTabs" :key="entry.key" role="tab" :aria-selected="current?.key===entry.key" :tabindex="current?.key===entry.key?0:-1" :title="entry.title+' · '+entry.artifact.title" @click="select(entry.key)">{{entry.label}}</button>
    </nav>
    <div class="analysis-chart-heading"><div><h2>{{current?.title??'数据分析'}}</h2><span>截至 {{actualDataAsOf}}<template v-if="!tablePrimary"> · 未复权</template></span></div>
      <div class="analysis-actions"><button v-if="chart" class="analysis-icon" title="重置图表缩放" aria-label="重置图表缩放" @click="plot?.resetZoom()"><RotateCcw :size="16"/></button><button class="analysis-icon" title="引用当前数据集" aria-label="引用当前数据集" @click="reference()"><Quote :size="16"/></button><button v-if="chart" class="analysis-icon" title="导出图表 PNG" aria-label="导出图表 PNG" :disabled="pending" @click="saveImage"><ImageDown :size="17"/></button><button class="analysis-icon" title="导出查询数据 CSV" aria-label="导出查询数据 CSV" :disabled="exporting||!current" @click="saveTable"><FileDown :size="17"/></button></div>
    </div>
    <div class="analysis-metrics"><div v-for="[key,value] in metrics" :key="key"><small>{{labels[key]}}</small><strong :class="{positive:/Return/.test(key)&&Number(value)>0,negative:/Return/.test(key)&&Number(value)<0}">{{format(value,key)}}</strong></div></div>
    <div class="analysis-plot-area" :class="{'analysis-table-primary':tablePrimary}"><div v-if="pending" class="analysis-state" role="status">正在读取数据集</div><StockPlot v-else-if="chart" ref="plot" :chart="chart" :annotations="data?.annotations" @select="reference($event)"/><StockDataTable v-else-if="data" :rows="rows" :total="data.rowCount" :schema="data.schema" @reference="referenceRow"/></div>
    <div v-if="error" class="analysis-error" role="alert">{{error}}<button class="analysis-icon" title="重新读取" aria-label="重新读取" @click="load"><RefreshCw :size="15"/></button></div>
    <section class="analysis-details"><header><div role="tablist" aria-label="分析详情"><button v-if="!tablePrimary" role="tab" :aria-selected="detail==='data'" @click="detail='data'"><Database :size="14"/>数据 <span>{{data?.rowCount??current?.artifact.rowCount}}</span></button><button role="tab" :aria-selected="detail==='indicators'" @click="detail='indicators'"><Activity :size="14"/>指标与统计</button><button role="tab" :aria-selected="detail==='source'" @click="detail='source'"><Info :size="14"/>来源</button></div><small v-if="detail==='data'">{{rows.length}} / {{data?.rowCount??0}} 行</small></header>
      <div class="analysis-detail-body" tabindex="0">
        <StockDataTable v-if="detail==='data'" :rows="rows" :total="data?.rowCount" :schema="data?.schema" @reference="referenceRow"/>
        <div v-else-if="detail==='indicators'" class="analysis-indicator-detail"><div v-if="indicators.length" class="analysis-indicator-values"><div v-for="item in indicators" :key="item.field"><small>{{item.field}}</small><strong>{{format(item.value)}}</strong></div></div><StockSummary :summary="data?.summary??{}"/></div>
        <div v-else class="analysis-provenance"><p>行情数据引擎 · {{data?.provenance.retrievedAt}}</p><code>{{current?.artifact.datasetRef}}</code><pre>{{JSON.stringify(data?.provenance.query??{},null,2)}}</pre><p v-for="warning in data?.warnings??[]" :key="warning">{{warning}}</p></div>
      </div>
    </section>
    </div>
  </section>
</template>
