<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ArrowLeft, Plus, RefreshCw, X, LayoutDashboard, Cable, Cpu, Users, Activity, MessageSquare, Search, Bell, Settings } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import AdminFeedback from '../components/AdminFeedback.vue'
import AdminAudit from '../components/AdminAudit.vue'
import RegistrationSettings from '../components/RegistrationSettings.vue'
import ImageSettings from '../components/ImageSettings.vue'
import FeatureSettings from '../components/FeatureSettings.vue'
import CoreModelSettings from '../components/CoreModelSettings.vue'
import SearchEngineSettings from '../components/SearchEngineSettings.vue'
import AccountNumberField from '../components/AccountNumberField.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import Announcements from '../components/feedback/Announcements.vue'

type RagSettings = { baseUrl: string; apiKeyConfigured: boolean; timeoutSeconds: number }
type Price = { currency: 'USD' | 'CNY'; inputPerMillion: number; outputPerMillion: number; source: 'manual' | 'LiteLLM reference' }
type CatalogModel = { id: string; price: Price | null }
type Account = { id: string; name: string; baseUrl: string; model: string; price: Price | null; concurrencyLimit: number; weight: number; status: string; apiKeyConfigured: boolean }
type Provider = { id: string; providerType: string; name: string; baseUrl: string; status: string; accounts: Account[] }
type UserRow = { id: string; username: string; role: string; status: string; passwordChangeRequired: boolean; lastLoginAt: string | null }
type Health = { rag: { status: string; latencyMs: number | null }; providers: Array<{ id: string; name: string; accounts: Array<{ id: string; name: string; status: string; latencyMs: number }> }> }
type Stats = { ragRequests: number; providerRequests: number; providerFailures: number; tokens: number; averageProviderLatencyMs: number; activeUsers: number }

const router = useRouter()
const tab = ref<'overview'|'rag'|'providers'|'search'|'users'|'feedback'|'audit'|'announcements'|'settings'>('overview')
const feedbackTarget=ref('')
const visitedAudit=ref(false),visitedFeedback=ref(false)
watch(tab,value=>{if(value==='audit')visitedAudit.value=true;if(value==='feedback')visitedFeedback.value=true})
const navigation = [{id:'overview',label:'概览',icon:LayoutDashboard},{id:'rag',label:'RAG 连接',icon:Cable},{id:'providers',label:'模型供应商',icon:Cpu},{id:'search',label:'AI 搜索引擎',icon:Search},{id:'users',label:'用户',icon:Users},{id:'audit',label:'调用与动态审计',icon:Activity},{id:'feedback',label:'反馈工单',icon:MessageSquare},{id:'announcements',label:'系统消息',icon:Bell},{id:'settings',label:'系统设置',icon:Settings}] as const
const ticketStats=ref({total:0,new:0,reviewing:0,closed:0,unread:0})
const ticketStatsError=ref('')
const ticketController=new AbortController()
let ticketChecking=false
async function refreshTickets(){if(ticketChecking||document.visibilityState==='hidden')return;ticketChecking=true;try{const value=await api<typeof ticketStats.value>('/api/v1/admin/feedback/stats',{signal:ticketController.signal});if(!ticketController.signal.aborted){ticketStats.value={total:value.total||0,new:value.new||0,reviewing:value.reviewing||0,closed:value.closed||0,unread:value.unread||0};ticketStatsError.value=''}}catch{if(!ticketController.signal.aborted)ticketStatsError.value='工单统计暂时不可用'}finally{ticketChecking=false}}
const ticketTimer=setInterval(refreshTickets,15000)
onMounted(()=>void refreshTickets())
onUnmounted(()=>{ticketController.abort();clearInterval(ticketTimer)})
type Resource = 'rag'|'providers'|'users'|'health'|'stats'
const modelBackend=ref('loading')
onMounted(async()=>{try{modelBackend.value=(await api<{backend:string}>('/api/v1/admin/settings/model')).backend}catch{modelBackend.value='unavailable'}})
const pending = reactive<Partial<Record<Resource, boolean>>>({})
const ready = reactive<Partial<Record<Resource, boolean>>>({})
const resourceErrors = reactive<Partial<Record<Resource, string>>>({})
const resources = computed<Resource[]>(() => tab.value==='providers'&&modelBackend.value!=='local'?[]:tab.value === 'overview' ? ['stats'] : ['rag','providers','users'].includes(tab.value) ? [tab.value as Resource] : [])
const loading = computed(() => resources.value.some(key => pending[key] && !ready[key]))
const refreshing = computed(() => resources.value.some(key => pending[key]))
const pageTitle = computed(() => navigation.find(item => item.id === tab.value)?.label)
const search = ref('')
const stateFilter = ref('')
const userRole = ref('')
const userPage = ref(1)
const userPageSize = 20
const rowSaving = reactive<Record<string, boolean>>({})
const saving = ref(false)
const error = ref('')
const notice = ref('')
const weightHelp = '权重为 1–100 的整数，默认 1；按每轮回答加权轮换。权重 2:1 表示长期约分配 2/3 和 1/3 的回答；同一轮工具调用使用同一账号。停用、冷却或达到并发上限的账号会跳过。'
const modal = ref<'provider'|'account'|'account-edit'|'user'|null>(null)
watch(modal,()=>{error.value='';notice.value=''})
const rag = reactive<RagSettings & { apiKey: string }>({ baseUrl: '', apiKeyConfigured: false, timeoutSeconds: 30, apiKey: '' })
const providers = ref<Provider[]>([])
const users = ref<UserRow[]>([])
const filteredProviders = computed(() => providers.value.flatMap(provider => {
  const query=search.value.trim().toLowerCase()
  const accounts=provider.accounts.filter(account => (!stateFilter.value || account.status === stateFilter.value)
    && `${provider.name} ${account.name} ${account.model} ${account.baseUrl}`.toLowerCase().includes(query))
  const emptyMatch=!provider.accounts.length && !stateFilter.value && `${provider.name} ${provider.baseUrl}`.toLowerCase().includes(query)
  return accounts.length || emptyMatch ? [{...provider,accounts}] : []
}))
const filteredUsers = computed(() => users.value.filter(user => (!stateFilter.value || user.status === stateFilter.value) && (!userRole.value || user.role===userRole.value) && user.username.toLowerCase().includes(search.value.trim().toLowerCase())))
const userPages = computed(()=>Math.max(1,Math.ceil(filteredUsers.value.length/userPageSize)))
const pagedUsers = computed(()=>filteredUsers.value.slice((userPage.value-1)*userPageSize,userPage.value*userPageSize))
watch([search,stateFilter,userRole],()=>{userPage.value=1})
watch(userPages,pages=>{userPage.value=Math.min(userPage.value,pages)})
const accountCount = computed(() => providers.value.reduce((count,provider) => count+provider.accounts.length,0))
const labels: Record<string,string> = {ACTIVE:'启用',DISABLED:'停用',UP:'正常',DOWN:'异常',NOT_CONFIGURED:'未配置',ERROR:'异常'}
const health = ref<Health>({ rag: { status: 'NOT_CONFIGURED', latencyMs: null }, providers: [] })
const stats = ref<Stats>({ ragRequests: 0, providerRequests: 0, providerFailures: 0, tokens: 0, averageProviderLatencyMs: 0, activeUsers: 0 })
const providerForm = reactive({ providerType: 'SILICONFLOW', name: '', baseUrl: 'https://api.siliconflow.cn/v1', accountName: '', apiKey: '', model: '', price: null as Price | null, concurrencyLimit: 2, weight: 1 })
const accountForm = reactive({ accountId: '', providerId: '', name: '', baseUrl: '', apiKey: '', model: '', price: null as Price | null, concurrencyLimit: 2, weight: 1 })
const catalog = ref<CatalogModel[]>([])
const modelFilter = ref('')
const discovering = ref(false)
const catalogError = ref('')
const visibleModels = computed(() => catalog.value.filter(item => item.id.toLowerCase().includes(modelFilter.value.toLowerCase())).slice(0, 100))
const activeForm = computed(() => modal.value === 'provider' ? providerForm : accountForm)
const priceDraft = reactive({ currency: 'USD' as 'USD' | 'CNY', inputPerMillion: 0, outputPerMillion: 0 })
const priceSource = ref('')
const providerDefaults: Record<string, { name: string; url: string }> = {
  SILICONFLOW: { name: 'SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
  DEEPSEEK: { name: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  OPENAI: { name: 'OpenAI', url: 'https://api.openai.com/v1' },
  OPENAI_COMPATIBLE: { name: '', url: '' },
}
watch(() => providerForm.providerType, type => {
  const defaults = providerDefaults[type]
  providerForm.name = defaults.name; providerForm.baseUrl = defaults.url
  providerForm.model = ''; providerForm.price = null; resetCatalog()
})

function resetCatalog() { catalog.value = []; modelFilter.value = ''; catalogError.value = ''; priceSource.value = '' }
function setPrice(price: Price | null) {
  activeForm.value.price = price
  priceSource.value = price?.source ?? ''
  priceDraft.currency = price?.currency ?? 'USD'
  priceDraft.inputPerMillion = price?.inputPerMillion ?? 0
  priceDraft.outputPerMillion = price?.outputPerMillion ?? 0
}
function saveManualPrice() {
  setPrice({ currency: priceDraft.currency, inputPerMillion: priceDraft.inputPerMillion,
    outputPerMillion: priceDraft.outputPerMillion, source: 'manual' })
}
function chooseModel(item: CatalogModel) { activeForm.value.model = item.id; setPrice(item.price) }
async function fetchCatalog() {
  discovering.value = true; catalogError.value = ''; catalog.value = []
  try {
    const body = modal.value === 'provider'
      ? { providerType: providerForm.providerType, baseUrl: providerForm.baseUrl, apiKey: providerForm.apiKey }
      : modal.value === 'account-edit' && !accountForm.apiKey
        ? { accountId: accountForm.accountId, baseUrl: accountForm.baseUrl }
        : { providerType: providers.value.find(item => item.id === accountForm.providerId)?.providerType,
          baseUrl: accountForm.baseUrl, apiKey: accountForm.apiKey }
    const result = await api<{ models: CatalogModel[] }>('/api/v1/admin/models/discover', { method: 'POST', body: JSON.stringify(body) })
    catalog.value = result.models
  } catch (cause) { catalogError.value = cause instanceof Error ? cause.message : '模型列表获取失败' }
  finally { discovering.value = false }
}
function openProviderModal() {
  resetCatalog()
  Object.assign(providerForm, { providerType: 'SILICONFLOW', name: 'SiliconFlow',
    baseUrl: providerDefaults.SILICONFLOW.url, accountName: '', apiKey: '', model: '', price: null,
    concurrencyLimit: 2, weight: 1 })
  setPrice(null)
  modal.value = 'provider'
}
function changeAccountProvider() {
  accountForm.baseUrl = providers.value.find(item => item.id === accountForm.providerId)?.baseUrl ?? ''
  accountForm.model = ''
  setPrice(null)
  resetCatalog()
}
const userForm = reactive({ username: '', password: '', role: 'USER' })
const failureRate = computed(() => stats.value.providerRequests ? Math.round(stats.value.providerFailures / stats.value.providerRequests * 100) : 0)

async function loadResource(key: Resource, force = false) {
  if (pending[key] || (ready[key] && !force)) return
  pending[key] = true; resourceErrors[key] = ''
  try {
    if(key==='rag') Object.assign(rag, await api<RagSettings>('/api/v1/admin/settings/rag'))
    if(key==='providers') providers.value = await api<Provider[]>('/api/v1/admin/providers')
    if(key==='users') users.value = await api<UserRow[]>('/api/v1/admin/users')
    if(key==='health') health.value = await api<Health>('/api/v1/admin/health')
    if(key==='stats') stats.value = await api<Stats>('/api/v1/admin/stats')
    ready[key] = true
  } catch (cause) { resourceErrors[key] = cause instanceof Error ? cause.message : '数据加载失败' }
  finally { pending[key] = false }
}
function load(force = false) { return Promise.all(resources.value.map(key=>loadResource(key,force))) }
watch(tab, () => { search.value='';stateFilter.value='';notice.value='';error.value='';void load() })
async function saveRag() {
  saving.value = true; error.value = ''
  try {
    const body: Record<string, unknown> = { baseUrl: rag.baseUrl, timeoutSeconds: rag.timeoutSeconds }
    if (rag.apiKey) body.apiKey = rag.apiKey
    Object.assign(rag, await api<RagSettings>('/api/v1/admin/settings/rag', { method: 'PUT', body: JSON.stringify(body) }))
    rag.apiKey = ''; notice.value = 'RAG 连接已保存'
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { saving.value = false }
}
async function createProvider() {
  if(saving.value)return
  saving.value = true;error.value='';notice.value=''
  try {
    await api('/api/v1/admin/providers', { method: 'POST', body: JSON.stringify({
      providerType: providerForm.providerType, name: providerForm.name, baseUrl: providerForm.baseUrl,
      accounts: [{ name: providerForm.accountName, apiKey: providerForm.apiKey, model: providerForm.model, price: providerForm.price,
        concurrencyLimit: providerForm.concurrencyLimit, weight: providerForm.weight }],
    }) })
    modal.value = null; await loadResource('providers',true); notice.value = '模型供应商已添加'
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '添加失败' }
  finally { saving.value = false }
}
function openAccountModal() {
  resetCatalog(); setPrice(null)
  accountForm.accountId = ''
  accountForm.providerId = providers.value[0]?.id ?? ''
  accountForm.baseUrl = providers.value[0]?.baseUrl ?? ''
  accountForm.name = ''; accountForm.apiKey = ''; accountForm.model = ''
  accountForm.concurrencyLimit = 2; accountForm.weight = 1
  modal.value = 'account'
}
function openAccountEditor(provider: Provider, account: Account) {
  resetCatalog()
  Object.assign(accountForm, { accountId: account.id, providerId: provider.id, name: account.name,
    baseUrl: account.baseUrl, apiKey: '', model: account.model, price: account.price,
    concurrencyLimit: account.concurrencyLimit, weight: account.weight })
  priceDraft.currency = account.price?.currency ?? 'USD'
  priceDraft.inputPerMillion = account.price?.inputPerMillion ?? 0
  priceDraft.outputPerMillion = account.price?.outputPerMillion ?? 0
  priceSource.value = account.price?.source ?? ''
  modal.value = 'account-edit'
}
async function createAccount() {
  if(saving.value)return
  saving.value = true;error.value='';notice.value=''
  try {
    await api(`/api/v1/admin/providers/${accountForm.providerId}/accounts`, { method: 'POST', body: JSON.stringify(accountForm) })
    modal.value = null; await loadResource('providers',true); notice.value = '模型账号已添加'
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '添加失败' }
  finally { saving.value = false }
}
async function saveAccount() {
  if(saving.value)return
  saving.value = true;error.value='';notice.value=''
  try {
    const body: Record<string, unknown> = { name: accountForm.name, baseUrl: accountForm.baseUrl,
      model: accountForm.model, price: accountForm.price, concurrencyLimit: accountForm.concurrencyLimit, weight: accountForm.weight }
    if (accountForm.apiKey) body.apiKey = accountForm.apiKey
    await api(`/api/v1/admin/accounts/${accountForm.accountId}`, { method: 'PATCH', body: JSON.stringify(body) })
    modal.value = null; await loadResource('providers',true); notice.value = '模型账号已更新'
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { saving.value = false }
}
async function updateAccount(account: Account, patch: Record<string, unknown>) {
  while(rowSaving[account.id]) await new Promise(resolve=>setTimeout(resolve,50))
  rowSaving[account.id]=true;error.value=''
  try { const saved = await api<Provider>(`/api/v1/admin/accounts/${account.id}`, { method: 'PATCH', body: JSON.stringify(patch) });const updated=saved.accounts.find(item=>item.id===account.id);if(!updated)throw new Error('未返回已保存的账号');Object.assign(account,updated);notice.value='模型账号已更新' }
  catch(cause) { error.value=cause instanceof Error?cause.message:'保存失败';throw cause }
  finally {rowSaving[account.id]=false}
}
async function createUser() {
  if(saving.value)return
  saving.value = true;error.value='';notice.value=''
  try {
    await api('/api/v1/admin/users', { method: 'POST', body: JSON.stringify(userForm) })
    modal.value = null; await loadResource('users',true); notice.value = '用户已创建，可直接登录'
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '创建失败' }
  finally { saving.value = false }
}
async function toggleUser(user: UserRow) {
  if(rowSaving[user.id]) return
  rowSaving[user.id]=true;error.value=''
  const status=user.status==='ACTIVE'?'DISABLED':'ACTIVE'
  try { await api(`/api/v1/admin/users/${user.id}`, { method: 'PATCH', body: JSON.stringify({status}) });user.status=status;notice.value='用户状态已更新' }
  catch(cause) {error.value=cause instanceof Error?cause.message:'保存失败'}
  finally {rowSaving[user.id]=false}
}
onMounted(()=>{void load();void loadResource('health')})
</script>

<template>
  <main class="admin-shell console-layout">
    <header class="admin-header">
      <button class="icon-button" title="返回对话" @click="router.push('/')"><ArrowLeft :size="19" /></button>
      <div class="console-heading"><span>管理控制台</span><strong>{{ pageTitle }}</strong></div>
      <ThemeToggle/>
      <button v-if="resources.length" class="icon-button" title="刷新当前视图" :disabled="refreshing" @click="load(true)"><RefreshCw :size="17" :class="{'console-spinning':refreshing}" /></button>
    </header>
    <nav class="admin-tabs" aria-label="管理视图">
      <button v-for="item in navigation"
              :key="item.id" :class="{ active: tab === item.id }" :aria-current="tab===item.id?'page':undefined" @click="feedbackTarget='';tab = item.id"><component :is="item.icon" :size="17"/>{{ item.label }}<span v-if="item.id==='feedback'&&ticketStats.unread" class="notification-dot inline" aria-label="有未读工单"/></button>
    </nav>
    <div class="console-notices"><div v-if="error" class="admin-message error" role="alert">{{ error }}</div>
    <div v-else-if="notice" class="admin-message success" role="status">{{ notice }}</div>
    <div v-for="key in resources.filter(key=>resourceErrors[key])" :key="key" class="admin-message error" role="alert">{{ resourceErrors[key] }} <button class="text-button" @click="loadResource(key,true)">重试</button></div></div>
    <section class="admin-content" :class="{'center-workspace':tab==='feedback'||tab==='announcements'}">
      <div v-show="tab==='feedback'" class="admin-feedback-pane"><AdminFeedback v-if="visitedFeedback" :feedback-id="feedbackTarget" :active="tab==='feedback'" @updated="refreshTickets"/></div>
      <div v-if="tab==='announcements'" class="admin-announcements"><Announcements admin/></div>
      <div v-show="tab==='audit'"><AdminAudit v-if="visitedAudit" :active="tab==='audit'" @feedback="feedbackTarget=$event;tab='feedback'"/></div>
      <div v-if="loading" class="console-skeleton" role="status" aria-label="正在加载当前视图"><div v-for="i in 6" :key="i"></div></div>
      <template v-else-if="tab === 'overview'">
        <div class="admin-service-strip"><div><strong>反馈处理</strong><span v-if="ticketStatsError">{{ticketStatsError}}</span><span v-else>{{ticketStats.new}} 待处理 · {{ticketStats.reviewing}} 处理中 · {{ticketStats.unread}} 未读</span></div><button class="secondary-button" @click="tab='feedback'">查看工单</button><button class="secondary-button" @click="tab='announcements'">管理系统消息</button></div>
        <div class="metric-strip">
          <div><span>RAG 请求</span><strong>{{ stats.ragRequests }}</strong></div>
          <div><span>模型请求</span><strong>{{ stats.providerRequests }}</strong></div>
          <div><span>失败率</span><strong>{{ failureRate }}%</strong></div>
          <div><span>Token</span><strong>{{ stats.tokens }}</strong></div>
          <div><span>平均模型耗时</span><strong>{{ stats.averageProviderLatencyMs }} ms</strong></div>
          <div><span>活跃用户</span><strong>{{ stats.activeUsers }}</strong></div>
        </div>
        <div class="section-heading"><h2>服务状态</h2><button class="compact-button" :disabled="pending.health" @click="loadResource('health',true)"><RefreshCw :size="15" :class="{'console-spinning':pending.health}"/>{{pending.health?'正在检查':'检查连接'}}</button></div>
        <p v-if="resourceErrors.health" class="form-error" role="alert">{{resourceErrors.health}}</p>
        <p v-if="!ready.health" class="console-health-status" role="status">{{pending.health?'正在检查服务连接，其他管理功能可正常使用。':'尚无连接检查结果'}}</p>
        <div v-if="ready.health" class="data-table-wrap"><table class="data-table"><thead><tr><th>服务</th><th>类型</th><th>账号</th><th>状态</th><th>延迟</th></tr></thead><tbody>
          <tr><td>RAG Consumer API</td><td>知识检索</td><td>{{ '—' }}</td><td><span class="status" :class="health.rag.status.toLowerCase()">{{ labels[health.rag.status] || health.rag.status }}</span></td><td>{{ health.rag.latencyMs ?? '-' }} ms</td></tr>
          <template v-for="provider in health.providers" :key="provider.id"><tr v-for="account in provider.accounts" :key="account.id"><td>{{ provider.name }}</td><td>生成模型</td><td>{{ account.name }}</td><td><span class="status" :class="account.status.toLowerCase()">{{ labels[account.status] || account.status }}</span></td><td>{{ account.latencyMs == null ? '—' : `${account.latencyMs} ms` }}</td></tr></template>
        </tbody></table></div>
      </template>
      <FeatureSettings v-else-if="tab === 'settings'" />
      <SearchEngineSettings v-else-if="tab === 'search'" />
      <template v-else-if="tab === 'rag'">
        <div class="section-heading"><div><h2>RAG 连接</h2><p>用于读取已发布知识库、执行检索和访问证据原文。</p></div><button class="compact-button" :disabled="pending.health||saving" @click="loadResource('health',true)"><RefreshCw :size="15" :class="{'console-spinning':pending.health}"/>检查已保存连接</button></div>
        <div class="connection-summary"><span>凭据：{{rag.apiKeyConfigured?'已配置':'未配置'}}</span><span v-if="ready.health">上次检查：{{labels[health.rag.status]||health.rag.status}}</span><span v-if="pending.health" role="status">正在检查连接…</span></div>
        <p v-if="resourceErrors.health" class="form-error" role="alert">{{resourceErrors.health}}</p>
        <form class="aligned-form" @submit.prevent="saveRag">
          <label>服务地址<input v-model.trim="rag.baseUrl" type="url" required placeholder="https://rag.example.com" /></label>
          <label>API Key<input v-model="rag.apiKey" type="password" :placeholder="rag.apiKeyConfigured ? '已配置，留空保持不变' : '输入 Consumer API Key'" /></label>
          <label>超时（秒）<input v-model.number="rag.timeoutSeconds" type="number" min="1" max="120" required /></label>
          <div class="form-actions"><button class="primary-button" :disabled="saving">保存</button></div>
        </form>
      </template>
      <CoreModelSettings v-else-if="tab === 'providers' && modelBackend !== 'local'" />
      <template v-else-if="tab === 'providers'">
        <ImageSettings :providers="providers"/>
        <div class="section-heading"><h2>模型供应商</h2><div class="section-actions"><button class="compact-button" :disabled="!providers.length" @click="openAccountModal"><Plus :size="15" />添加账号</button><button class="compact-button" @click="openProviderModal"><Plus :size="15" />添加供应商</button></div></div>
        <div class="console-filters"><label><Search :size="16"/><input v-model="search" aria-label="搜索模型账号" placeholder="供应商、账号、模型或端点"/></label><select v-model="stateFilter" aria-label="账号状态"><option value="">全部状态</option><option value="ACTIVE">启用</option><option value="DISABLED">停用</option></select><span>{{providers.length}} 个供应商 · {{accountCount}} 个账号</span></div>
        <div class="data-table-wrap"><table class="data-table provider-table"><thead><tr><th>供应商</th><th>账号</th><th>端点</th><th>模型</th><th>参考价 / 百万 Token</th><th>并发</th><th>权重 <span tabindex="0" :title="weightHelp" :aria-label="weightHelp">ⓘ</span></th><th>状态</th><th>操作</th></tr></thead><tbody>
          <template v-for="provider in filteredProviders" :key="provider.id"><tr v-for="account in provider.accounts" :key="account.id" :aria-busy="!!rowSaving[account.id]"><td><strong>{{ provider.name }}</strong><small>{{ provider.providerType === 'OPENAI_COMPATIBLE' ? 'OpenAI 兼容' : provider.providerType }}</small></td><td>{{ account.name }}</td><td class="truncate-cell" :title="account.baseUrl">{{ account.baseUrl }}</td><td class="truncate-cell" :title="account.model">{{ account.model }}</td><td :title="account.price?.source ?? '暂无报价'">{{ account.price ? `${account.price.currency} ${account.price.inputPerMillion} / ${account.price.outputPerMillion}` : '暂无报价' }}</td><td><AccountNumberField :value="account.concurrencyLimit" label="并发上限（1–100）" :save="value=>updateAccount(account,{concurrencyLimit:value})" /></td><td><AccountNumberField :value="account.weight" label="调度权重（1–100）" :save="value=>updateAccount(account,{weight:value})" /></td><td><span class="status" :class="account.status.toLowerCase()">{{ labels[account.status] || account.status }}</span></td><td><div class="row-actions"><button class="text-button" :disabled="rowSaving[account.id]" @click="openAccountEditor(provider,account)">编辑</button><button class="text-button" :disabled="rowSaving[account.id]" @click="updateAccount(account,{status:account.status==='ACTIVE'?'DISABLED':'ACTIVE'}).catch(()=>{})">{{ account.status === 'ACTIVE' ? '停用' : '启用' }}</button></div></td></tr></template>
          <tr v-for="provider in filteredProviders.filter(p=>!p.accounts.length)" :key="`empty-${provider.id}`"><td><strong>{{provider.name}}</strong><small>{{provider.providerType}}</small></td><td colspan="7" class="table-empty">尚未添加模型账号</td><td><button class="text-button" @click="openAccountModal(); accountForm.providerId=provider.id; accountForm.baseUrl=provider.baseUrl">添加账号</button></td></tr>
          <tr v-if="!filteredProviders.length"><td colspan="9" class="table-empty">{{providers.length?'没有符合筛选条件的账号':'尚未配置模型供应商'}}</td></tr>
        </tbody></table></div>
      </template>
      <template v-else-if="tab === 'users'">
        <RegistrationSettings />
        <div class="section-heading"><h2>用户</h2><button class="compact-button" @click="modal = 'user'"><Plus :size="15" />创建用户</button></div>
        <div class="console-filters"><label><Search :size="16"/><input v-model="search" aria-label="搜索用户" placeholder="搜索账号"/></label><select v-model="stateFilter" aria-label="用户状态"><option value="">全部状态</option><option value="ACTIVE">启用</option><option value="DISABLED">停用</option></select><select v-model="userRole" aria-label="用户角色"><option value="">全部角色</option><option value="ADMIN">管理员</option><option value="USER">用户</option></select><span>{{filteredUsers.length}} 个用户</span></div>
        <div class="data-table-wrap"><table class="data-table"><thead><tr><th>账号</th><th>角色</th><th>状态</th><th>首次改密</th><th>最近登录</th><th>操作</th></tr></thead><tbody>
          <tr v-for="user in pagedUsers" :key="user.id"><td><strong>{{ user.username }}</strong></td><td>{{ user.role === 'ADMIN' ? '管理员' : '用户' }}</td><td><span class="status" :class="user.status.toLowerCase()">{{ labels[user.status] || user.status }}</span></td><td>{{ user.passwordChangeRequired ? '需要' : '不需要' }}</td><td>{{ user.lastLoginAt ? new Date(user.lastLoginAt).toLocaleString() : '从未登录' }}</td><td><button class="text-button" :disabled="rowSaving[user.id]" @click="toggleUser(user)">{{ user.status === 'ACTIVE' ? '停用' : '启用' }}</button></td></tr>
          <tr v-if="!filteredUsers.length"><td colspan="6" class="table-empty">{{search||stateFilter||userRole?'没有符合筛选条件的用户':'尚未创建用户'}}</td></tr>
        </tbody></table></div>
      </template>
      <footer v-if="tab==='users' && ready.users" class="console-pagination"><span>第 {{userPage}} / {{userPages}} 页 · 每页 {{userPageSize}} 条</span><button class="compact-button" :disabled="userPage<=1" @click="userPage--">上一页</button><button class="compact-button" :disabled="userPage>=userPages" @click="userPage++">下一页</button></footer>
    </section>

    <div v-if="modal" class="modal-scrim" role="presentation">
      <section class="admin-modal" role="dialog" aria-modal="true" :aria-labelledby="`${modal}-title`">
        <header><h2 :id="`${modal}-title`">{{ modal === 'provider' ? '添加模型供应商' : modal === 'account' ? '添加模型账号' : modal === 'account-edit' ? '编辑模型账号' : '创建用户' }}</h2><button class="icon-button" title="关闭" :disabled="saving" @click="modal = null"><X :size="18" /></button></header>
        <p v-if="error" class="modal-save-error" role="alert">{{error}}</p>
        <form v-if="modal === 'provider'" class="modal-form" @submit.prevent="createProvider">
          <label>供应商<select v-model="providerForm.providerType" data-testid="provider-type"><option value="SILICONFLOW">SiliconFlow</option><option value="DEEPSEEK">DeepSeek</option><option value="OPENAI">OpenAI</option><option value="OPENAI_COMPATIBLE">自定义 OpenAI 兼容</option></select></label>
          <label>显示名称<input v-model.trim="providerForm.name" required /></label><label>Base URL<input v-model.trim="providerForm.baseUrl" data-testid="provider-url" type="url" required placeholder="https://provider.example/v1" /></label>
          <div class="form-grid"><label>账号名称<input v-model.trim="providerForm.accountName" required /></label><label>API Key<input v-model="providerForm.apiKey" data-testid="provider-key" type="password" required /></label></div>
          <div class="catalog-field"><label>对话模型<input v-model.trim="providerForm.model" data-testid="provider-model" required placeholder="选择或填写模型 ID" @input="setPrice(null)" /></label><button type="button" class="secondary-button" data-testid="discover-models" :disabled="discovering || !providerForm.baseUrl || !providerForm.apiKey" @click="fetchCatalog"><RefreshCw :size="15" />{{ discovering ? '正在获取' : '拉取模型与价格' }}</button></div>
          <div v-if="catalogError" class="catalog-error" role="alert">{{ catalogError }}</div>
          <div v-if="catalog.length" data-testid="model-catalog" class="catalog-panel"><input v-model.trim="modelFilter" aria-label="筛选模型" placeholder="筛选对话模型" /><div class="catalog-list"><button v-for="item in visibleModels" :key="item.id" type="button" :data-testid="`model-choice-${item.id}`" :class="{ selected: providerForm.model === item.id }" @click="chooseModel(item)"><span :title="item.id">{{ item.id }}</span><small>{{ item.price ? `${item.price.currency} ${item.price.inputPerMillion} / ${item.price.outputPerMillion}` : '暂无报价' }}</small></button><div v-if="!visibleModels.length" class="catalog-empty">没有匹配的对话模型</div></div></div>
          <div class="price-fields" data-testid="manual-price"><div class="price-heading">输入 / 输出价格 <small>每百万 Token · {{ priceSource === 'LiteLLM reference' ? 'LiteLLM 第三方参考价' : priceSource === 'SiliconFlow official' ? 'SiliconFlow 官网' : priceSource === 'manual' ? '手填' : '暂无报价' }}</small></div><div class="form-grid price-grid"><label>币种<select v-model="priceDraft.currency" @change="saveManualPrice"><option value="USD">USD</option><option value="CNY">CNY</option></select></label><label>输入<input v-model.number="priceDraft.inputPerMillion" type="number" min="0" step="any" @input="saveManualPrice" /></label><label>输出<input v-model.number="priceDraft.outputPerMillion" type="number" min="0" step="any" @input="saveManualPrice" /></label></div></div>
          <div class="form-grid"><label>并发上限<input v-model.number="providerForm.concurrencyLimit" type="number" min="1" max="100" /></label><label><span>调度权重 <span tabindex="0" :title="weightHelp" :aria-label="weightHelp">ⓘ</span></span><input v-model.number="providerForm.weight" type="number" min="1" max="100" /></label></div>
          <div class="modal-actions"><button type="button" class="secondary-button" :disabled="saving" @click="modal = null">取消</button><button class="primary-button" :disabled="saving">添加</button></div>
        </form>
        <form v-else-if="modal === 'account' || modal === 'account-edit'" class="modal-form" @submit.prevent="modal === 'account' ? createAccount() : saveAccount()">
          <label>供应商<select v-model="accountForm.providerId" :disabled="modal === 'account-edit'" required @change="changeAccountProvider"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name }}</option></select></label>
          <label>账号名称<input v-model.trim="accountForm.name" required /></label><label>Base URL<input v-model.trim="accountForm.baseUrl" type="url" required /></label><label>API Key<input v-model="accountForm.apiKey" type="password" :required="modal === 'account'" :placeholder="modal === 'account-edit' ? '留空保持当前密钥' : ''" /></label>
          <div class="catalog-field"><label>对话模型<input v-model.trim="accountForm.model" required placeholder="选择或填写模型 ID" @input="setPrice(null)" /></label><button type="button" class="secondary-button" :disabled="discovering || !accountForm.baseUrl || (modal === 'account' && !accountForm.apiKey)" @click="fetchCatalog"><RefreshCw :size="15" />{{ discovering ? '正在获取' : '拉取模型与价格' }}</button></div>
          <div v-if="catalogError" class="catalog-error" role="alert">{{ catalogError }}</div>
          <div v-if="catalog.length" class="catalog-panel"><input v-model.trim="modelFilter" aria-label="筛选模型" placeholder="筛选对话模型" /><div class="catalog-list"><button v-for="item in visibleModels" :key="item.id" type="button" :class="{ selected: accountForm.model === item.id }" @click="chooseModel(item)"><span :title="item.id">{{ item.id }}</span><small>{{ item.price ? `${item.price.currency} ${item.price.inputPerMillion} / ${item.price.outputPerMillion}` : '暂无报价' }}</small></button><div v-if="!visibleModels.length" class="catalog-empty">没有匹配的对话模型</div></div></div>
          <div class="price-fields"><div class="price-heading">输入 / 输出价格 <small>每百万 Token · {{ priceSource === 'LiteLLM reference' ? 'LiteLLM 第三方参考价' : priceSource === 'SiliconFlow official' ? 'SiliconFlow 官网' : priceSource === 'manual' ? '手填' : '暂无报价' }}</small></div><div class="form-grid price-grid"><label>币种<select v-model="priceDraft.currency" @change="saveManualPrice"><option value="USD">USD</option><option value="CNY">CNY</option></select></label><label>输入<input v-model.number="priceDraft.inputPerMillion" type="number" min="0" step="any" @input="saveManualPrice" /></label><label>输出<input v-model.number="priceDraft.outputPerMillion" type="number" min="0" step="any" @input="saveManualPrice" /></label></div></div>
          <div class="form-grid"><label>并发上限<input v-model.number="accountForm.concurrencyLimit" type="number" min="1" max="100" /></label><label><span>调度权重 <span tabindex="0" :title="weightHelp" :aria-label="weightHelp">ⓘ</span></span><input v-model.number="accountForm.weight" type="number" min="1" max="100" /></label></div><div class="modal-actions"><button type="button" class="secondary-button" :disabled="saving" @click="modal = null">取消</button><button class="primary-button" :disabled="saving">{{ modal === 'account' ? '添加' : '保存' }}</button></div>
        </form>
        <form v-else class="modal-form" @submit.prevent="createUser"><label>账号<input v-model.trim="userForm.username" required /></label><label>初始密码<input v-model="userForm.password" type="password" minlength="12" required /></label><label>角色<select v-model="userForm.role"><option value="USER">用户</option><option value="ADMIN">管理员</option></select></label><div class="modal-actions"><button type="button" class="secondary-button" :disabled="saving" @click="modal = null">取消</button><button class="primary-button" :disabled="saving">创建</button></div></form>
      </section>
    </div>
  </main>
</template>

<style scoped>
.console-layout { grid-template-columns: 208px minmax(0,1fr); grid-template-rows: 64px auto minmax(0,1fr); background: #fff; }
.admin-header { grid-column: 1 / -1; grid-row: 1; display: flex; gap: 16px; padding: 0 20px; background: #fff; border-bottom: 1px solid var(--separator); }
.console-heading { display: flex; align-items: center; gap: 20px; flex: 1; }
.console-heading > span { color: var(--ink-secondary); font-size: 13px; }
.console-heading strong { font-size: 17px; }
.admin-tabs { grid-column: 1; grid-row: 2 / 4; display: flex; flex-direction: column; align-items: stretch; gap: 5px; padding: 18px 12px; border: 0; border-right: 1px solid var(--separator); background: #f7f8fa; }
.admin-tabs button { display: flex; align-items: center; gap: 10px; height: 42px; padding: 0 12px; border: 0; border-radius: 9px; text-align: left; font-size: 13px; }
.admin-tabs button.active { background: #e9effa; color: #215fc4; }
.admin-tabs button:hover { background: #eaecef; }
.console-notices { grid-column: 2; grid-row: 2; padding-inline:max(24px,calc((100% - 1320px) / 2)); }
.admin-message { margin: 12px 0 0; }
.admin-content { grid-column: 2; grid-row: 3; padding: 20px max(24px,calc((100% - 1320px) / 2)); min-width: 0; background: #fff; }
.admin-content.center-workspace { display:flex;flex-direction:column;overflow:hidden;min-height:0; }
.admin-feedback-pane,.admin-announcements { flex:1;min-height:0;overflow:hidden; }
.console-layout :deep(.feedback-admin),.admin-content .admin-announcements { height:100%;min-height:0; }
.section-heading { margin-top: 0; }
.section-heading h2 { font-size: 16px; }
.console-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 16px 0; font-size: 13px; }
.console-filters label { display: flex; align-items: center; gap: 8px; width: min(320px,100%); padding: 0 10px; height: 36px; border: 1px solid var(--separator); border-radius: 8px; color: var(--ink-secondary); }
.console-filters input { border: 0; background: transparent; width: 100%; min-width: 0; font: inherit; color: var(--ink); }
.console-filters select { height: 36px; max-width: 180px; padding: 0 10px; border: 1px solid var(--separator); border-radius: 8px; background: #fff; font: inherit; }
.console-filters > span { margin-left: auto; color: var(--ink-secondary); }
.console-health-status { font-size: 13px; padding: 14px 0; color: var(--ink-secondary); }
.console-skeleton { display: grid; gap: 12px; }
.console-skeleton > div { height: 42px; border-radius: 6px; background: #f1f3f6; }
.console-skeleton > div:first-child { height: 84px; margin-bottom: 12px; }
.console-spinning { animation: console-spin 1s linear infinite; }
@keyframes console-spin { to { transform: rotate(360deg); } }
.console-layout :deep(.data-table-wrap) { max-height: calc(100dvh - 245px); border-radius: 10px; scrollbar-width: thin; }
.console-layout :deep(.data-table th) { position: sticky; top: 0; z-index: 1; background: #f7f8fa; }
.console-layout :deep(.data-table td) { height: 52px; }
.console-layout :deep(.data-table tbody tr:hover) { background: #f9fafc; }
.console-layout :deep(.provider-table) { min-width: 1120px; }
.console-layout :deep(.provider-table th:nth-child(1)) { width: 115px; }
.console-layout :deep(.provider-table th:nth-child(2)) { width: 100px; }
.console-layout :deep(.provider-table th:nth-child(3)) { width: 160px; }
.console-layout :deep(.provider-table th:nth-child(4)) { width: 180px; }
.console-layout :deep(.provider-table th:nth-child(5)) { width: 150px; }
.console-layout :deep(.provider-table th:nth-child(6)), .console-layout :deep(.provider-table th:nth-child(7)) { width: 75px; }
.console-layout :deep(.provider-table th:nth-child(8)) { width: 80px; }
.console-layout :deep(.provider-table th:nth-child(9)) { width: 115px; }
.console-layout :deep(.provider-table td:last-child:not([colspan])) { position: sticky; right: 0; background: #fff; box-shadow: -1px 0 0 var(--separator); }
.console-layout :deep(.provider-table th:last-child) { right: 0; z-index: 2; }
.console-layout :deep(.provider-table .table-number) { width: 52px; }
.console-layout :deep(.metric-strip) { margin-bottom: 24px; border-radius: 10px; }
.console-layout :deep(.aligned-form) { max-width: 700px; }
.console-layout :deep(.admin-modal) { max-height: calc(100dvh - 48px); }
.modal-save-error { margin: 16px 20px 0; padding: 12px; border-radius: 9px; background: #fff1f2; color: #b52e3b; font-size: 13px; line-height: 1.6; }
.console-pagination { display:flex; align-items:center; gap:10px; padding-top:14px; font-size:13px; color:var(--ink-secondary); }
.console-pagination > span { margin-right:auto; }
.connection-summary { display:flex; flex-wrap:wrap; gap:16px; padding:12px 14px; margin:16px 0 24px; background:#f4f7fb; border-radius:10px; font-size:13px; color:var(--ink-secondary); }
.console-layout :deep(.audit-filters) { display:flex; align-items:flex-end; gap:10px; padding:16px; border:1px solid var(--separator); border-radius:12px; background:#fafbfd; }
.console-layout :deep(.audit-filters label:has(input[type=datetime-local])) { display:grid; gap:6px; font-size:12px; }
.console-layout :deep(.audit-summary) { padding:14px 0; }
.console-layout :deep(.audit-kinds) { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:16px; }
.console-layout :deep(.audit-kinds button) { border:0; padding:9px 13px; border-radius:8px; background:transparent; color:var(--ink-secondary); }
.console-layout :deep(.audit-kinds button.active) { background:#eaf0fc; color:#215fc4; }
.console-layout :deep(.audit-pagination),.console-layout :deep(.feedback-pagination) { flex-wrap:wrap; gap:10px; font-size:13px; }
.console-layout :deep(.audit-table td:last-child:not([colspan])),.console-layout :deep(.feedback-table td:last-child:not([colspan])) { position:sticky; right:0; background:#fff; box-shadow:-1px 0 0 var(--separator); }
.console-layout :deep(.audit-table th:last-child),.console-layout :deep(.feedback-table th:last-child) { right:0; z-index:2; }
.console-layout :deep(.audit-detail dl) { grid-template-columns:120px minmax(0,1fr); padding:16px; border:1px solid var(--separator); border-radius:10px; background:#fafbfd; }
.console-layout :deep(.feedback-detail-meta) { display:flex; flex-wrap:wrap; gap:12px; font-size:13px; color:var(--ink-secondary); }
.console-layout :deep(.feedback-admin h2) { font-size:16px; }
@media(max-width:840px) {
 .console-layout { grid-template-columns: minmax(0,1fr); grid-template-rows: 58px auto auto minmax(0,1fr); }
 .admin-tabs { grid-column: 1; grid-row: 2; flex-direction: row; padding: 8px 12px; border-right: 0; border-bottom: 1px solid var(--separator); overflow-x: auto; }
 .admin-tabs button { height: 36px; min-height: 36px; }
 .console-notices { grid-column: 1; grid-row: 3; padding-inline:14px; }
 .admin-content { grid-column: 1; grid-row: 4; padding: 14px; }
 .admin-header { padding: 0 12px; }
 .console-heading { gap: 10px; }
 .console-heading > span { display: none; }
 .console-filters > span { margin-left: 0; }
 .console-layout :deep(.table-empty) { text-align:left; padding:20px 14px; }
 .console-layout :deep(.audit-detail dl) { grid-template-columns:90px minmax(0,1fr); gap:10px; }
}
@media(prefers-reduced-motion:reduce) { .console-spinning { animation: none; } }
</style>
