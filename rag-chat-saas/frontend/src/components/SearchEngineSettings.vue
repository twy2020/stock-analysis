<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowDown, ArrowUp, Cable, ExternalLink, RefreshCw, Save, Trash2 } from 'lucide-vue-next'
import { api } from '../api/client'
import WebProxySettings from './WebProxySettings.vue'
type Provider={id:string;name:string;enabled:boolean;priority:number;timeoutSeconds:number;configured:boolean;supported:boolean;transport:string;endpoint:string;docs:string;reason?:string;toolName:string;apiKey?:string;clearKey?:boolean;health:{status:string;code?:string;elapsedMs?:number}}
type Settings={engines:string[];providers:Provider[]}
type Result={ok:boolean;code?:string;message?:string;toolName?:string;sources?:{url:string;title:string}[];searches?:{engine:string;status:string;error?:string}[]}
const value=ref<Settings>({engines:[],providers:[]}),loaded=ref(false),busy=ref(''),error=ref(''),notice=ref('')
const results=ref<Record<string,Result>>({}),dirty=ref(false)
const engineOptions=[['duckduckgo','DuckDuckGo'],['bing','Bing'],['baidu','百度'],['so360','360'],['sogou','搜狗'],['google','Google'],['yandex','Yandex']]
const labels:Record<string,string>={WEB_TIMEOUT:'请求超时',WEB_SEARCH_RATE_LIMITED:'搜索引擎限流',WEB_SEARCH_UNAVAILABLE:'搜索服务不可用',WEB_RESEARCH_UNAVAILABLE:'连接或协议失败',WEB_PROVIDER_AUTH_FAILED:'API Key 无效或账户无权限',WEB_MCP_TOOL_FAILED:'MCP 工具调用失败',WEB_MCP_TOOL_SELECTION_REQUIRED:'请填写明确的搜索工具名称',WEB_MCP_SCHEMA_UNSUPPORTED:'此工具的查询参数暂不兼容',WEB_SEARCH_NO_SOURCES:'没有返回可引用的来源链接',WEB_PROVIDER_NOT_CONFIGURED:'请先保存 API Key',WEB_PROXY_UNAVAILABLE:'代理连接失败',WEB_SOURCE_UNAVAILABLE:'来源不可用'}
function apply(data:Settings){value.value={...data,providers:data.providers.sort((a,b)=>a.priority-b.priority)};dirty.value=false}
async function load(){busy.value='load';error.value='';try{apply(await api<Settings>('/api/v1/admin/settings/search-engines'));loaded.value=true}catch(e){error.value=e instanceof Error?e.message:'加载失败'}finally{busy.value=''}}
onMounted(load)
function move(index:number,offset:number){const rows=value.value.providers;[rows[index],rows[index+offset]]=[rows[index+offset]!,rows[index]!];rows.forEach((p,i)=>p.priority=i+1);dirty.value=true}
async function save(){busy.value='save';error.value='';notice.value='';try{apply(await api<Settings>('/api/v1/admin/settings/search-engines',{method:'PUT',body:JSON.stringify({engines:value.value.engines,providers:value.value.providers.map(p=>({id:p.id,enabled:p.enabled,priority:p.priority,timeoutSeconds:p.timeoutSeconds,toolName:p.toolName,...(p.apiKey?{apiKey:p.apiKey}:{}),...(p.clearKey?{clearKey:true}:{})}))})}));notice.value='已保存，后续搜索立即使用此配置'}catch(e){error.value=e instanceof Error?e.message:'保存失败'}finally{busy.value=''}}
async function test(p:Provider){busy.value=p.id;error.value='';try{results.value[p.id]=await api<Result>(`/api/v1/admin/settings/search-engines/${p.id}/test`,{method:'POST',body:'{}'})}catch(e){error.value=e instanceof Error?e.message:'测试失败'}finally{busy.value=''}}
</script>

<template>
  <section class="search-settings" :aria-busy="!!busy">
    <header><div><h2>AI 搜索引擎</h2><p>按优先级切换备用服务 · 总搜索预算 40 秒 · Dhole 负责网页读取</p></div><button class="icon-button" title="刷新搜索配置" aria-label="刷新搜索配置" :disabled="!!busy" @click="load"><RefreshCw :size="17"/></button></header>
    <p v-if="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <form v-if="loaded" @submit.prevent="save" @input="dirty=true" @change="dirty=true">
      <fieldset :disabled="!!busy"><legend>本地并发引擎</legend><div class="engine-options"><label v-for="[id,name] in engineOptions" :key="id"><input v-model="value.engines" type="checkbox" :value="id" :disabled="!value.engines.includes(id!)&&value.engines.length>=3"/>{{name}}</label></div><small>最多 3 个；全部取消时按代理配置自动选择。</small></fieldset>
      <article v-for="(p,index) in value.providers" :key="p.id" class="provider-row">
        <div class="provider-heading"><div class="order"><button type="button" class="icon-button" title="提高优先级" :aria-label="`${p.name}提高优先级`" :disabled="!!busy||index===0" @click="move(index,-1)"><ArrowUp :size="14"/></button><span>{{index+1}}</span><button type="button" class="icon-button" title="降低优先级" :aria-label="`${p.name}降低优先级`" :disabled="!!busy||index===value.providers.length-1" @click="move(index,1)"><ArrowDown :size="14"/></button></div><strong>{{p.name}}</strong><span class="provider-state">{{!p.supported?'暂不支持':p.configured?'已配置':'待配置'}}</span><label class="enabled"><input v-model="p.enabled" type="checkbox" :aria-label="`启用${p.name}`" :disabled="!!busy||!p.supported"/>启用</label></div>
        <small v-if="p.reason" class="reason">{{p.reason}}</small>
        <div v-else class="provider-fields">
          <label>超时（秒）<input v-model.number="p.timeoutSeconds" type="number" min="5" max="25" required :disabled="!!busy"/></label>
          <template v-if="p.id!=='native'"><label>API Key<input v-model="p.apiKey" type="password" autocomplete="new-password" :placeholder="p.configured?'留空保留已保存凭据':'尚未配置'" :disabled="!!busy"/></label><label>MCP 搜索工具<input v-model="p.toolName" :disabled="!!busy" placeholder="留空自动发现" maxlength="100"/></label><button type="button" class="icon-button" title="清除凭据（保存后生效）" :aria-label="`清除${p.name}凭据`" :disabled="!!busy||!p.configured" @click="p.clearKey=true;p.apiKey='';p.enabled=false;dirty=true"><Trash2 :size="16"/></button><small v-if="p.clearKey">凭据将在保存时清除</small></template>
        </div>
        <footer><a :href="p.docs" target="_blank" rel="noopener noreferrer">官方/项目文档<ExternalLink :size="13"/></a><span>{{p.transport}}</span><button v-if="p.supported" type="button" class="compact-button" :disabled="!!busy||dirty||!p.configured" @click="test(p)"><Cable :size="15"/>{{busy===p.id?'测试中…':'测试已保存配置'}}</button><span v-if="!results[p.id]&&p.health.status!=='untested'">{{p.health.status==='succeeded'?'最近成功':'最近失败'}} · {{p.health.elapsedMs}} ms</span></footer>
        <div v-if="results[p.id]" class="test-result" role="status"><strong>{{results[p.id]!.ok?'搜索成功':results[p.id]!.message||labels[results[p.id]!.code||'']||'搜索测试失败'}}</strong><span v-if="results[p.id]!.toolName">{{results[p.id]!.toolName}}</span><a v-for="source in results[p.id]!.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{source.title}}</a><small v-for="engine in results[p.id]!.searches" :key="engine.engine">{{engine.engine}}：{{engine.status==='succeeded'?'成功':labels[engine.error||'']||'失败'}}</small></div>
      </article>
      <div class="save-row"><button class="compact-button" :disabled="!!busy"><Save :size="16"/>保存搜索配置</button><small v-if="dirty">有未保存的更改</small></div>
      <p class="billing">千帆、知乎需各自平台凭据与权限；额度及计费以账户控制台为准。连接测试会发起一次真实搜索。</p>
    </form>
    <WebProxySettings/>
  </section>
</template>

<style scoped>
.search-settings{max-width:1000px;color:var(--ink);width:100%}header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-bottom:16px;border-bottom:1px solid var(--separator)}h2{font-size:18px;margin:0}p,small{color:var(--ink-secondary);font-size:13px;line-height:1.6}fieldset{border:0;border-bottom:1px solid var(--separator);padding:20px 0;margin:0}legend{padding-top:18px;font-size:14px;font-weight:600}.engine-options{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:8px}.engine-options label,.enabled{display:flex;align-items:center;gap:7px;font-size:13px}input[type=checkbox]{width:16px;height:16px;min-height:16px;accent-color:var(--accent);margin:0}.provider-row{padding:20px 0;border-bottom:1px solid var(--separator)}.provider-heading{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.provider-heading strong{font-size:14px}.order{display:flex;align-items:center;gap:4px;font-size:12px}.order .icon-button{width:26px;height:26px}.enabled{margin-left:auto}.provider-state{font-size:12px;color:var(--ink-secondary)}.provider-fields{display:flex;align-items:end;flex-wrap:wrap;gap:12px;margin-top:16px}.provider-fields label{display:grid;gap:6px;flex:1 1 200px;font-size:12px}.provider-fields label:first-child{flex:0 1 110px}input:not([type=checkbox]){box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--separator);border-radius:6px;padding:9px;background:var(--surface);color:var(--ink);font:inherit}.reason{display:block;margin-top:12px}footer{display:flex;align-items:center;flex-wrap:wrap;gap:14px;margin-top:14px;font-size:12px;color:var(--ink-secondary)}a{color:var(--accent);text-decoration:none;display:inline-flex;align-items:center;gap:5px;overflow-wrap:anywhere}a:hover{text-decoration:underline}.test-result{display:grid;gap:7px;margin-top:12px;padding:12px;border-left:2px solid var(--accent);font-size:13px;overflow-wrap:anywhere}.save-row{display:flex;gap:12px;align-items:center;margin-top:20px}.billing{margin-bottom:0}[role=alert]{color:var(--danger)}@media(max-width:600px){.provider-heading{gap:8px}.provider-fields label,.provider-fields label:first-child{flex:1 1 100%}.enabled{margin-left:0}header p{max-width:260px}}
</style>
