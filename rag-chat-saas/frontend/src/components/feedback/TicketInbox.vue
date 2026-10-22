<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { Search, RefreshCw, Inbox } from 'lucide-vue-next'
import { api } from '../../api/client'
import TicketThread from './TicketThread.vue'
import { type Ticket, date, statusLabels } from './types'
const props=withDefaults(defineProps<{admin?:boolean;ticketId?:string;active?:boolean}>(),{active:true})
const emit=defineEmits<{updated:[]}>()
const items=ref<Ticket[]>([]),total=ref(0),page=ref(1),q=ref(''),status=ref(''),unread=ref(false),selected=ref(''),loading=ref(false),error=ref('')
const stats=ref({total:0,new:0,reviewing:0,closed:0,unread:0})
let seq=0;const controller=new AbortController()
async function load(){
 if(props.active===false)return
 const version=++seq;loading.value=true;error.value=''
 try{const result=await api<{items:Ticket[];total:number}>(`/api/v1/${props.admin?'admin/':''}feedback?${new URLSearchParams({page:String(page.value),q:q.value,status:status.value,unread:String(unread.value)})}`,{signal:controller.signal});if(version!==seq)return;items.value=result.items;total.value=result.total
  if(props.admin){const value=await api<typeof stats.value>('/api/v1/admin/feedback/stats',{signal:controller.signal});if(version===seq)stats.value=value}
 }catch(e){if(version===seq&&!controller.signal.aborted)error.value=e instanceof Error?e.message:'加载失败'}finally{if(version===seq)loading.value=false}
}
function filter(){page.value=1;void load()}
function back(){selected.value='';void load()}
function updated(){emit('updated')}
watch(()=>props.ticketId,id=>{selected.value=id||'';if(!id)void load()},{immediate:true})
watch(()=>props.active,value=>{if(value&&!selected.value)void load()})
onUnmounted(()=>{seq++;controller.abort()})
</script>
<template>
 <TicketThread v-if="selected" :key="selected" :id="selected" :admin="admin" :active="active" @back="back" @updated="updated"/>
 <section v-else class="ticket-inbox">
  <div v-if="admin" class="ticket-metrics"><div><span>全部工单</span><strong>{{stats.total}}</strong></div><div><span>待处理</span><strong>{{stats.new}}</strong></div><div><span>处理中</span><strong>{{stats.reviewing}}</strong></div><div><span>已关闭</span><strong>{{stats.closed}}</strong></div><div><span>未读</span><strong>{{stats.unread}}</strong></div></div>
  <form class="ticket-filters" @submit.prevent="filter"><label class="center-search"><Search :size="16"/><input v-model="q" aria-label="搜索工单" placeholder="搜索工单号、内容或用户" maxlength="200"/></label><select v-model="status" aria-label="工单状态" @change="filter"><option value="">全部状态</option><option v-for="(label,key) in statusLabels" :key="key" :value="key">{{label}}</option></select><label class="unread-filter"><input v-model="unread" type="checkbox" @change="filter"/>只看未读</label><button class="secondary-button" type="submit">搜索</button><button class="icon-button" type="button" aria-label="刷新工单列表" :disabled="loading" @click="load"><RefreshCw :size="16"/></button></form>
  <p v-if="error" class="form-error" role="alert">{{error}}</p>
  <div class="ticket-list-scroll" :aria-busy="loading">
   <table v-if="admin" class="data-table ticket-table"><thead><tr><th>工单</th><th>反馈内容</th><th>用户</th><th>状态</th><th>最近更新</th><th>操作</th></tr></thead><tbody><tr v-for="row in items" :key="row.id"><td><span v-if="row.unread" class="notification-dot inline" aria-label="未读"/>{{row.ticketNumber}}</td><td :title="row.comment">{{row.comment}}</td><td>{{row.username}}</td><td><span class="ticket-status" :data-status="row.status">{{statusLabels[row.status]}}</span></td><td>{{date(row.updatedAt||row.createdAt)}}</td><td><button class="text-button" :data-ticket="row.id" @click="selected=row.id">处理</button></td></tr></tbody></table>
   <template v-else><button v-for="row in items" :key="row.id" class="ticket-list-row" :data-ticket="row.id" @click="selected=row.id"><span class="ticket-list-heading"><strong :title="row.comment">{{row.comment}}</strong><span v-if="row.unread" class="notification-dot inline" aria-label="未读"/><span class="ticket-status" :data-status="row.status">{{statusLabels[row.status]}}</span></span><span class="ticket-preview">{{row.latestPreview||row.comment}}</span><span class="ticket-list-meta"><span>{{row.ticketNumber}}</span><time>{{date(row.updatedAt||row.createdAt)}}</time></span></button></template>
   <div v-if="!items.length" class="center-empty"><Inbox :size="30"/><p>{{loading?'正在加载工单…':q||status||unread?'没有符合条件的工单':'还没有反馈工单'}}</p></div>
  </div>
  <footer class="center-pagination"><span>共 {{total}} 条 · 第 {{page}} 页</span><button class="secondary-button" :disabled="page<=1||loading" @click="page--;load()">上一页</button><button class="secondary-button" :disabled="page*20>=total||loading" @click="page++;load()">下一页</button></footer>
 </section>
</template>
