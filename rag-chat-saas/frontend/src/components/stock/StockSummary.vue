<script setup lang="ts">
import { computed } from 'vue'
import { fieldLabel, formatValue } from './presentation'
import StockDataTable from './StockDataTable.vue'
import type { StockRow } from '../../types'
const props=defineProps<{summary:Record<string,unknown>}>()
const groups=computed(()=>Object.entries(props.summary).map(([key,value])=>({key,value})))
function entries(value:unknown,prefix=''):Array<{key:string;value:unknown}>{
  if(value&&typeof value==='object'&&!Array.isArray(value))return Object.entries(value).flatMap(([key,item])=>entries(item,prefix?`${prefix}.${key}`:key))
  return [{key:prefix,value}]
}
function tabular(value:unknown):value is StockRow[]{
  return Array.isArray(value)&&value.length>0&&value.every(row=>row&&typeof row==='object'&&!Array.isArray(row)&&Object.values(row).every(item=>item==null||typeof item==='string'||typeof item==='number'))
}
</script>
<template><section class="stock-summary-view" aria-label="结构化统计"><template v-for="group in groups" :key="group.key"><details v-if="tabular(group.value)" open><summary>{{fieldLabel(group.key)}}</summary><StockDataTable :rows="group.value" :total="group.value.length" :reference-enabled="false"/></details><details v-else-if="group.value&&typeof group.value==='object'&&!Array.isArray(group.value)" open><summary>{{fieldLabel(group.key)}}</summary><dl><template v-for="item in entries(group.value)" :key="item.key"><dt :title="item.key">{{item.key.split('.').map(fieldLabel).join(' · ')}}</dt><dd>{{formatValue(item.value,item.key)}}</dd></template></dl></details><dl v-else><dt>{{fieldLabel(group.key)}}</dt><dd>{{formatValue(group.value,group.key)}}</dd></dl></template><p v-if="!groups.length">没有统计摘要</p></section></template>
<style scoped>
.stock-summary-view{font-size:12px;color:var(--ink);padding:8px 0;overflow:auto;max-height:420px}.stock-summary-view details{border-bottom:1px solid var(--separator);padding:8px 0}.stock-summary-view summary{cursor:pointer;font-weight:500;overflow-wrap:anywhere}.stock-summary-view dl{display:grid;grid-template-columns:minmax(100px,1fr) minmax(0,2fr);gap:8px 16px;margin:10px 0}.stock-summary-view dt{color:var(--ink-secondary);overflow-wrap:anywhere}.stock-summary-view dd{margin:0;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.stock-summary-view p{color:var(--ink-secondary)}
</style>
