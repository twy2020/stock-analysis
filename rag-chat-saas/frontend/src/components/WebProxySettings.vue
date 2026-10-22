<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Cable, Save, Trash2 } from 'lucide-vue-next'
import { api } from '../api/client'
type Settings = { enabled:boolean; configured:boolean; endpoint:string; mode:'all'|'selected'; domains:string[] }
const value=ref<Settings>({enabled:false,configured:false,endpoint:'',mode:'selected',domains:[]})
const address=ref(''), domains=ref(''), loaded=ref(false), busy=ref(false), error=ref(''), status=ref('')
function apply(data:Settings){value.value=data;domains.value=data.domains.join('\n');address.value=''}
onMounted(async()=>{
  try {apply(await api<Settings>('/api/v1/admin/settings/web-proxy'));loaded.value=true}
  catch(e){error.value=e instanceof Error?e.message:'代理设置加载失败'}
})
async function save(clear=false){
  busy.value=true;error.value='';status.value=''
  try {
    apply(await api<Settings>('/api/v1/admin/settings/web-proxy',{method:'PUT',body:JSON.stringify({enabled:value.value.enabled,mode:value.value.mode,
      domains:domains.value.split(/[\s,，]+/).filter(Boolean),...(address.value?{url:address.value.trim()}:{}),...(clear?{clear:true}:{})})}))
    status.value=clear?'代理已清除':'代理设置已保存'
  }catch(e){error.value=e instanceof Error?e.message:'代理保存失败'}finally{busy.value=false}
}
async function test(){
  busy.value=true;error.value='';status.value=''
  try{
    const result=await api<{ok:boolean;elapsedMs:number;status?:number}>('/api/v1/admin/settings/web-proxy/test',{method:'POST',body:'{}'})
    if(result.ok)status.value=`代理连通 · ${result.elapsedMs} ms`
    else error.value=result.status?`代理目标返回 HTTP ${result.status}`:'代理连接失败'
  }catch(e){error.value=e instanceof Error?e.message:'代理连接失败'}finally{busy.value=false}
}
</script>

<template>
  <form class="web-proxy-settings" @submit.prevent="save()">
    <header><h2>联网代理</h2></header>
    <label class="proxy-toggle"><span>启用代理</span><input v-model="value.enabled" type="checkbox" :disabled="busy||!loaded"/></label>
    <label>代理地址<input v-model="address" type="password" autocomplete="new-password" :disabled="busy||!loaded" :placeholder="value.configured?'留空保留已保存地址':'http://host.docker.internal:7890'"/></label>
    <small v-if="value.configured">已配置：{{value.endpoint}}</small>
    <small>HTTP/混合端口：http://host.docker.internal:7890；SOCKS5：socks5://host.docker.internal:10808。宿主机代理需允许局域网连接。</small>
    <label>代理范围<select v-model="value.mode" :disabled="busy||!loaded"><option value="selected">指定域名及其子域名</option><option value="all">全部搜索与网页浏览</option></select></label>
    <label v-if="value.mode==='selected'">代理域名<textarea v-model="domains" rows="5" :disabled="busy||!loaded" placeholder="bing.com&#10;duckduckgo.com&#10;yahoo.com"/></label>
    <footer>
      <button class="compact-button" :disabled="busy||!loaded"><Save :size="16"/>保存代理</button>
      <button type="button" class="compact-button" :disabled="busy||!value.configured" @click="test"><Cable :size="16"/>测试已保存代理</button>
      <button type="button" class="icon-button" title="清除代理" aria-label="清除代理" :disabled="busy||!value.configured" @click="save(true)"><Trash2 :size="16"/></button>
      <span v-if="error" role="alert">{{error}}</span><span v-else-if="status" role="status">{{status}}</span>
    </footer>
  </form>
</template>

<style scoped>
.web-proxy-settings{width:100%;max-width:760px;padding-top:28px;color:var(--ink);display:grid;gap:14px}
header{padding-bottom:16px;border-bottom:1px solid var(--separator)}h2{margin:0;font-size:18px}
label{display:grid;gap:8px;font-size:14px}.proxy-toggle{display:flex;justify-content:space-between;align-items:center}
input:not([type=checkbox]),select,textarea{width:100%;box-sizing:border-box;min-width:0;border:1px solid var(--separator);border-radius:6px;padding:10px;background:var(--surface);color:var(--ink);font:inherit}
input[type=checkbox]{width:18px;height:18px;accent-color:var(--accent)}textarea{resize:vertical;line-height:1.5}
small{color:var(--ink-secondary);line-height:1.6;overflow-wrap:anywhere}
footer{display:flex;flex-wrap:wrap;align-items:center;gap:12px;font-size:13px}[role=alert]{color:var(--danger)}[role=status]{color:var(--ink-secondary)}
</style>
