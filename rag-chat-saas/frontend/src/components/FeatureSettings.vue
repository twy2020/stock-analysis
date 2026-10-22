<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import { Save } from 'lucide-vue-next'
import WebProxySettings from './WebProxySettings.vue'
import CoreModelSettings from './CoreModelSettings.vue'
const enabled=ref(false), loaded=ref(false), busy=ref(false), error=ref(''), saved=ref(false)
const webEnabled=ref(false)
onMounted(async()=>{
  try { const value=await api<{ragEnabled:boolean;webEnabled:boolean}>('/api/v1/admin/settings/features'); enabled.value=value.ragEnabled; webEnabled.value=value.webEnabled; loaded.value=true }
  catch(e) { error.value=e instanceof Error?e.message:'设置加载失败' }
})
async function save(){
  busy.value=true; error.value=''; saved.value=false
  try { await api('/api/v1/admin/settings/features',{method:'PUT',body:JSON.stringify({ragEnabled:enabled.value,webEnabled:webEnabled.value})}); saved.value=true }
  catch(e) { error.value=e instanceof Error?e.message:'保存失败' }
  finally { busy.value=false }
}
</script>
<template>
  <CoreModelSettings />
  <form class="feature-settings" @submit.prevent="save">
    <header><h2>功能开放</h2><span v-if="!loaded&&!error" role="status">正在加载…</span></header>
    <label class="feature-toggle">
      <span class="feature-copy"><strong>知识库检索（RAG）</strong><small>允许对话使用已配置的知识库。</small></span>
      <input v-model="enabled" type="checkbox" aria-label="开放知识库检索（RAG）" :disabled="busy||!loaded" @change="saved=false"/>
    </label>
    <label class="feature-toggle">
      <span class="feature-copy"><strong>联网搜索与网页浏览</strong><small>开放后，用户可在聊天栏选择是否联网。</small></span>
      <input v-model="webEnabled" type="checkbox" aria-label="开放联网搜索与网页浏览" :disabled="busy||!loaded" @change="saved=false"/>
    </label>
    <footer>
      <button class="compact-button" :disabled="busy||!loaded"><Save :size="16"/>{{busy?'正在保存…':'保存设置'}}</button>
      <span v-if="error" role="alert">{{error}}</span><span v-else-if="saved" role="status">设置已保存，重新进入对话后生效</span>
    </footer>
  </form>
  <WebProxySettings />
</template>
<style scoped>
.feature-settings{width:100%;max-width:760px;padding-top:8px;color:var(--ink)}
.feature-settings header{display:flex;align-items:center;gap:16px;padding-bottom:20px;border-bottom:1px solid var(--separator)}
.feature-settings h2{margin:0;font-size:18px}
.feature-toggle{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 0;border-bottom:1px solid var(--separator);cursor:pointer}
.feature-copy{display:grid;gap:7px;min-width:0}.feature-copy strong{font-size:14px;font-weight:600}.feature-copy small{font-size:13px;color:var(--ink-secondary);line-height:1.6}
.feature-toggle input{flex:0 0 18px;width:18px;height:18px;min-height:18px;margin:0;accent-color:var(--accent);cursor:pointer}
.feature-settings footer{display:flex;align-items:center;flex-wrap:wrap;gap:14px;padding-top:22px;font-size:13px}
.feature-settings [role=status]{color:var(--ink-secondary)}.feature-settings [role=alert]{color:var(--danger)}
</style>
