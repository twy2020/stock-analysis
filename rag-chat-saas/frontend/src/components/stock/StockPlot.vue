<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { init, use, type EChartsType } from 'echarts/core'
import { CandlestickChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkPointComponent, MarkAreaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { StockChartData, StockAnnotation } from '../../types'
import { stockOption } from './chart'
import { theme } from '../../theme'
import { PanelTopOpen, PanelTopClose } from 'lucide-vue-next'
use([CandlestickChart,LineChart,BarChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,MarkPointComponent,MarkAreaComponent,CanvasRenderer])
const props=withDefaults(defineProps<{chart:StockChartData;annotations?:StockAnnotation[];dark?:boolean}>(),{dark:undefined})
const isDark=computed(()=>props.dark??theme.value==='dark')
const emit=defineEmits<{select:[date:string]}>()
const host=ref<HTMLElement|null>(null)
const pinned=ref(false)
let plot:EChartsType|undefined,observer:ResizeObserver|undefined
function render(preserveZoom=false){
  const zoom=preserveZoom?plot?.getOption().dataZoom as Array<{start:number;end:number}>|undefined:undefined
  plot?.setOption(stockOption(props.chart,props.annotations,isDark.value,pinned.value),{notMerge:true})
  zoom?.forEach((range,index)=>plot?.dispatchAction({type:'dataZoom',dataZoomIndex:index,start:range.start,end:range.end}))
  if(pinned.value&&props.chart.rows.length)plot?.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:props.chart.rows.length-1})
}
function togglePanel(){pinned.value=!pinned.value;plot?.dispatchAction({type:'hideTip'});render(true)}
watch(()=>[props.chart,props.annotations],()=>render(),{deep:true})
watch(isDark,()=>render(true))
defineExpose({exportImage:()=>plot?.getDataURL({type:'png',pixelRatio:2,backgroundColor:isDark.value?'#202328':'#ffffff'}),resetZoom:()=>plot?.dispatchAction({type:'dataZoom',start:0,end:100})})
onMounted(()=>{
  if(!host.value)return
  plot=init(host.value)
  plot.on('click',(event:any)=>{const row=props.chart.rows[event.dataIndex];if(row?.date)emit('select',String(row.date))})
  observer=new ResizeObserver(()=>plot?.resize());observer.observe(host.value);render()
})
onBeforeUnmount(()=>{observer?.disconnect();plot?.dispose()})
</script>
<template><div class="stock-plot" :class="{'plot-dark':isDark}"><div ref="host" class="stock-plot-canvas" role="img" :aria-label="chart.title"/><button class="stock-panel-toggle" :title="pinned?'恢复鼠标数据看板':'展开固定数据看板'" :aria-label="pinned?'恢复鼠标数据看板':'展开固定数据看板'" :aria-pressed="pinned" @click="togglePanel"><PanelTopClose v-if="pinned" :size="15"/><PanelTopOpen v-else :size="15"/></button></div></template>
<style scoped>
.stock-plot{position:relative;width:100%;height:320px;min-width:0}.stock-plot-canvas{width:100%;height:100%}
.stock-panel-toggle{position:absolute;top:2px;left:8px;display:grid;place-items:center;box-sizing:border-box;width:28px;min-width:28px;max-width:28px;height:28px;min-height:28px;max-height:28px;aspect-ratio:1;padding:0;border:1px solid rgba(100,120,130,.16);border-radius:3px;background:rgba(255,255,255,.32);color:#5d6570;backdrop-filter:blur(8px);cursor:pointer;transition:background .15s}
.stock-panel-toggle:hover,.stock-panel-toggle[aria-pressed=true]{background:rgba(225,237,240,.5);color:#167d91}.stock-panel-toggle:focus-visible{outline:2px solid #167d91;outline-offset:2px}
.plot-dark .stock-panel-toggle{background:rgba(32,41,43,.32);color:#c6d5d4}.plot-dark .stock-panel-toggle:hover,.plot-dark .stock-panel-toggle[aria-pressed=true]{background:rgba(55,80,82,.5);color:#69c9c0}
@media(max-width:600px){.stock-plot{height:270px}}
</style>
