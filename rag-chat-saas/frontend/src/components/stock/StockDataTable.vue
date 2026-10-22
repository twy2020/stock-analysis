<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowUp, ArrowDown, ChevronLeft, ChevronRight, Quote, Search, Table2, List } from 'lucide-vue-next'
import type { StockRow } from '../../types'
import { fieldLabel, formatValue } from './presentation'

const props=withDefaults(defineProps<{rows:StockRow[];total?:number;schema?:Record<string,string>;referenceEnabled?:boolean}>(),{total:0,referenceEnabled:true})
const emit=defineEmits<{reference:[row:StockRow]}>()
const search=ref(''),sort=ref(''),descending=ref(false),page=ref(0),pageSize=ref(20),mode=ref('table')
const fields=computed(()=>Array.from(new Set(props.rows.flatMap(row=>Object.keys(row)))).filter(key=>!key.startsWith('_')))
const matching=computed(()=>{
  const text=search.value.trim().toLocaleLowerCase()
  const rows=props.rows.filter(row=>!text||fields.value.some(field=>String(row[field]??'').toLocaleLowerCase().includes(text)))
  if(!sort.value)return rows
  return [...rows].sort((a,b)=>{
    const left=a[sort.value],right=b[sort.value]
    if(left==null)return right==null?0:1
    if(right==null)return -1
    const result=typeof left==='number'&&typeof right==='number'?left-right:String(left).localeCompare(String(right),'zh-CN',{numeric:true})
    return descending.value?-result:result
  })
})
const pages=computed(()=>Math.max(1,Math.ceil(matching.value.length/pageSize.value)))
const visible=computed(()=>matching.value.slice(page.value*pageSize.value,(page.value+1)*pageSize.value))
watch([search,pageSize,()=>props.rows],()=>{page.value=0})
function order(field:string){if(sort.value===field)descending.value=!descending.value;else{sort.value=field;descending.value=false}page.value=0}
</script>
<template>
  <section class="stock-data-view" aria-label="数据表格">
    <div class="data-toolbar">
      <label class="data-search"><Search :size="14"/><input v-model="search" type="search" aria-label="筛选已加载数据" placeholder="筛选已加载数据"/></label>
      <div class="data-modes" role="group" aria-label="数据呈现方式"><button title="表格" aria-label="表格模式" :aria-pressed="mode==='table'" @click="mode='table'"><Table2 :size="15"/></button><button title="记录详情" aria-label="记录详情模式" :aria-pressed="mode==='records'" @click="mode='records'"><List :size="15"/></button></div>
      <select v-model="pageSize" aria-label="每页行数"><option :value="20">20 行</option><option :value="50">50 行</option><option :value="100">100 行</option></select>
    </div>
    <div class="data-content" tabindex="0">
      <table v-if="mode==='table'&&visible.length" class="data-table"><thead><tr><th v-for="field in fields" :key="field" :aria-sort="sort===field?(descending?'descending':'ascending'):'none'"><button :title="field+(schema?.[field]?' · '+schema[field]:'')" @click="order(field)">{{fieldLabel(field)}}<ArrowDown v-if="sort===field&&descending" :size="12"/><ArrowUp v-else-if="sort===field" :size="12"/></button></th><th v-if="referenceEnabled">引用</th></tr></thead><tbody><tr v-for="(row,index) in visible" :key="index"><td v-for="field in fields" :key="field" :class="{numeric:typeof row[field]==='number'}">{{formatValue(row[field],field)}}</td><td v-if="referenceEnabled"><button class="data-icon" title="引用此行" aria-label="引用此行" @click="emit('reference',row)"><Quote :size="14"/></button></td></tr></tbody></table>
      <div v-else-if="visible.length" class="data-records"><article v-for="(row,index) in visible" :key="index"><header><strong>{{row.name??row.code??row.date??`记录 ${page*pageSize+index+1}`}}</strong><button v-if="referenceEnabled" class="data-icon" title="引用此行" aria-label="引用此行" @click="emit('reference',row)"><Quote :size="14"/></button></header><dl><template v-for="field in fields" :key="field"><dt :title="field">{{fieldLabel(field)}}</dt><dd>{{formatValue(row[field],field)}}</dd></template></dl></article></div>
      <p v-else class="data-empty" role="status">{{rows.length?'没有匹配的记录':total?'当前响应没有表格行':'没有符合条件的数据'}}</p>
    </div>
    <footer class="data-pagination"><span>已加载 {{rows.length}} / {{total||rows.length}} 行<span v-if="search"> · 匹配 {{matching.length}} 行</span></span><div><button class="data-icon" title="上一页" aria-label="上一页" :disabled="page===0" @click="page--"><ChevronLeft :size="16"/></button><span>{{page+1}} / {{pages}}</span><button class="data-icon" title="下一页" aria-label="下一页" :disabled="page+1>=pages" @click="page++"><ChevronRight :size="16"/></button></div></footer>
  </section>
</template>
<style scoped>
.stock-data-view{display:flex;flex-direction:column;min-width:0;min-height:0;height:100%;color:var(--ink);font-size:12px}.data-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 0;flex-shrink:0}.data-search{display:flex;align-items:center;gap:6px;flex:1;min-width:120px;color:var(--ink-secondary)}.data-search input{width:100%;min-width:0;border:1px solid var(--separator);border-radius:4px;background:var(--surface-secondary);color:var(--ink);font:inherit;padding:5px 8px}.data-modes{display:flex;gap:2px}.data-modes button,.data-icon{display:inline-grid;place-items:center;width:28px;height:28px;min-height:28px;padding:0;border:0;border-radius:4px;background:transparent;color:var(--ink-secondary)}.data-modes button[aria-pressed=true]{background:var(--accent-tint);color:var(--stock-accent)}.data-icon:hover{background:var(--surface-secondary)}.data-icon:disabled{opacity:.35}.data-toolbar select{min-height:28px;max-width:80px;font:inherit;background:var(--surface);color:var(--ink);border:1px solid var(--separator);border-radius:4px}.data-content{overflow:auto;min-height:0;max-height:420px;flex:1;scrollbar-width:thin}.data-table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}.data-table th{position:sticky;top:0;z-index:1;background:var(--surface);text-align:left;border-bottom:1px solid var(--separator)}.data-table th button{display:flex;align-items:center;gap:5px;min-height:32px;padding:5px 10px;border:0;background:transparent;color:var(--ink-secondary);font:inherit;white-space:nowrap}.data-table td{padding:6px 10px;border-bottom:1px solid var(--separator);white-space:nowrap;max-width:400px;overflow-wrap:anywhere}.data-table td.numeric{text-align:right}.data-table tr:hover td{background:var(--surface-secondary)}.data-empty{padding:28px 0;text-align:center;color:var(--ink-secondary)}.data-pagination{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-shrink:0;padding:8px 0;font-size:11px;color:var(--ink-secondary)}.data-pagination>div{display:flex;align-items:center;gap:4px;white-space:nowrap}.data-records article{border-bottom:1px solid var(--separator);padding:10px 0}.data-records header{display:flex;align-items:center;justify-content:space-between}.data-records dl{display:grid;grid-template-columns:minmax(80px,1fr) minmax(0,2fr);gap:6px 12px;margin:8px 0}.data-records dt{color:var(--ink-secondary);overflow-wrap:anywhere}.data-records dd{margin:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
</style>
