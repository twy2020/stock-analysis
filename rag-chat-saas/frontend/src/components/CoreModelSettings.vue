<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Cpu, RefreshCw, Save, ExternalLink } from 'lucide-vue-next'
import { api } from '../api/client'
type Model = {id:string;name:string;model:string;providerType:string;tools:boolean}
type Settings = {backend:string;defaultModelProfile:string;models:Model[];revision:string;writable:boolean}
const settings=ref<Settings|null>(null),selected=ref(''),busy=ref(false),error=ref(''),saved=ref(false)
const current=computed(()=>settings.value?.models?.find(m=>m.id===settings.value?.defaultModelProfile))
const coreAdmin=`${window.location.protocol}//${window.location.hostname}:18210/admin#models`
async function load(){
  busy.value=true;error.value='';saved.value=false
  try {
    const value=await api<Settings>('/api/v1/admin/settings/model')
    if(value.backend!=='local'&&(value.backend!=='core'||!Array.isArray(value.models)))throw new Error('Core 模型设置返回异常')
    settings.value=value;selected.value=value.defaultModelProfile
  }
  catch(e){error.value=e instanceof Error?e.message:'模型设置加载失败'}
  finally{busy.value=false}
}
async function save(){
  if(!settings.value)return
  busy.value=true;error.value='';saved.value=false
  try { settings.value=await api<Settings>('/api/v1/admin/settings/model',{method:'PUT',body:JSON.stringify({revision:settings.value.revision,modelProfile:selected.value})});selected.value=settings.value.defaultModelProfile;saved.value=true }
  catch(e){error.value=e instanceof Error?e.message:'模型设置保存失败'}
  finally{busy.value=false}
}
onMounted(load)
</script>
<template>
  <form v-if="settings?.backend!=='local'" class="core-model-settings" @submit.prevent="save">
    <header><h2><Cpu :size="18"/>聊天模型</h2><button type="button" class="icon-button" title="刷新 Core 模型" aria-label="刷新 Core 模型" :disabled="busy" @click="load"><RefreshCw :size="16"/></button></header>
    <div v-if="settings" class="model-fields">
      <div class="active-model"><span>当前模型</span><strong>{{current?.model||'不可用'}}</strong><small>{{current?.providerType}} · {{settings.defaultModelProfile}}</small></div>
      <label>Core 授权模型<select v-model="selected" :disabled="busy||!settings.writable||!settings.models.length" @change="saved=false"><option v-if="!settings.models.length" value="">暂无可用的授权模型</option><option v-for="model in settings.models" :key="model.id" :value="model.id" :disabled="!model.tools">{{model.name}} · {{model.model}} · {{model.providerType}}{{!model.tools?' · 不支持工具调用':''}}</option></select></label>
      <p v-if="!settings.writable" role="status">Core 配置为只读，暂时无法保存模型选择。</p>
      <div class="model-actions"><button class="compact-button" :disabled="busy||!settings.writable||selected===settings.defaultModelProfile"><Save :size="16"/>保存模型</button><a :href="coreAdmin" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15"/>Core 模型与服务授权</a></div>
      <span v-if="saved" role="status">已同步至 Core，下一轮对话使用该模型</span>
    </div>
    <span v-else-if="busy" role="status">正在读取 Core…</span>
    <p v-if="error" role="alert">{{error}}</p>
  </form>
</template>
<style scoped>
.core-model-settings{width:100%;max-width:760px;padding:24px 0;color:var(--ink);border-bottom:1px solid var(--separator)}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}h2{display:flex;align-items:center;gap:8px;font-size:18px;margin:0}
.model-fields{display:grid;gap:18px;min-width:0}.active-model{display:grid;gap:7px}.active-model span,small,[role=status]{color:var(--ink-secondary);font-size:13px}strong{font-size:14px;overflow-wrap:anywhere}
label{display:grid;gap:8px;font-size:13px}select{width:100%;max-width:100%;min-width:0}.model-actions{display:flex;align-items:center;gap:20px;flex-wrap:wrap}a{display:inline-flex;align-items:center;gap:6px;color:var(--accent);font-size:13px;text-decoration:none}[role=alert]{color:var(--danger);font-size:13px}
</style>
