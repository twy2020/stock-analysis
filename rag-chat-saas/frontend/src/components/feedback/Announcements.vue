<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { Bell, ArrowLeft, Plus, RefreshCw } from 'lucide-vue-next'
import { api } from '../../api/client'
import { date } from './types'
type Notice={id:string;title:string;content:string;username:string;createdAt:string;active:boolean;unread:boolean}
const props=withDefaults(defineProps<{admin?:boolean;active?:boolean}>(),{active:true}),emit=defineEmits<{updated:[]}>()
const items=ref<Notice[]>([]),total=ref(0),page=ref(1),selected=ref<Notice|null>(null),creating=ref(false),title=ref(''),content=ref(''),error=ref(''),loading=ref(false),saving=ref(false)
let version=0;const controller=new AbortController()
async function load(){const seq=++version;loading.value=true;error.value='';try{const value=await api<{items:Notice[];total:number}>(`/api/v1/${props.admin?'admin/':''}announcements?page=${page.value}`,{signal:controller.signal});if(seq===version){items.value=value.items;total.value=value.total}}catch(e){if(seq===version&&!controller.signal.aborted)error.value=e instanceof Error?e.message:'加载失败'}finally{if(seq===version)loading.value=false}}
async function open(item:Notice){selected.value=item;if(!props.admin&&item.unread){try{await api(`/api/v1/announcements/${item.id}/read`,{method:'POST',signal:controller.signal});item.unread=false;emit('updated')}catch(e){if(!controller.signal.aborted)error.value=e instanceof Error?e.message:'未能更新已读状态'}}}
async function publish(){if(saving.value||!title.value.trim()||!content.value.trim())return;saving.value=true;error.value='';try{await api('/api/v1/admin/announcements',{method:'POST',body:JSON.stringify({title:title.value,content:content.value}),signal:controller.signal});creating.value=false;title.value='';content.value='';page.value=1;await load();emit('updated')}catch(e){if(!controller.signal.aborted)error.value=e instanceof Error?e.message:'发布失败'}finally{saving.value=false}}
async function withdraw(item:Notice){saving.value=true;error.value='';try{const updated=await api<Notice>(`/api/v1/admin/announcements/${item.id}`,{method:'PATCH',body:JSON.stringify({active:false}),signal:controller.signal});Object.assign(item,updated);emit('updated')}catch(e){if(!controller.signal.aborted)error.value=e instanceof Error?e.message:'撤回失败'}finally{saving.value=false}}
watch(()=>props.active,value=>{if(value!==false)void load()},{immediate:true})
onUnmounted(()=>{version++;controller.abort()})
</script>
<template>
 <section class="announcements-panel">
  <header class="ticket-toolbar"><button v-if="selected||creating" class="icon-button" aria-label="返回系统消息" :disabled="saving" @click="selected=null;creating=false"><ArrowLeft :size="18"/></button><h3>{{creating?'发布系统消息':selected?'消息详情':'系统消息'}}</h3><button v-if="admin&&!creating&&!selected" class="primary-button" @click="creating=true"><Plus :size="16"/>发布消息</button><button v-if="!selected&&!creating" class="icon-button" aria-label="刷新系统消息" :disabled="loading" @click="load"><RefreshCw :size="16"/></button></header>
  <p v-if="error" class="form-error ticket-error" role="alert">{{error}}</p>
  <form v-if="creating" class="announcement-form" @submit.prevent="publish"><label>标题<input v-model="title" maxlength="120" placeholder="例如：系统维护通知" :disabled="saving" required/></label><label>消息内容<textarea v-model="content" rows="9" maxlength="5000" placeholder="填写需要告知用户的具体事项" :disabled="saving" required/></label><p class="center-muted">发布后，本组织的用户会在消息中心收到提醒。</p><footer><button class="primary-button" :disabled="saving||!title.trim()||!content.trim()">{{saving?'正在发布…':'发布消息'}}</button></footer></form>
  <article v-else-if="selected" class="announcement-detail"><h2>{{selected.title}}</h2><div class="ticket-list-meta"><span>{{selected.username}}</span><time>{{date(selected.createdAt)}}</time><span v-if="!selected.active">已撤回</span></div><p>{{selected.content}}</p><button v-if="admin&&selected.active" class="secondary-button" :disabled="saving" @click="withdraw(selected)">撤回消息</button></article>
  <template v-else><div class="ticket-list-scroll"><button v-for="item in items" :key="item.id" class="ticket-list-row" @click="open(item)"><span class="ticket-list-heading"><Bell :size="17"/><strong>{{item.title}}</strong><span v-if="!admin&&item.unread" class="notification-dot inline" aria-label="未读"/><span v-if="!item.active" class="ticket-status">已撤回</span></span><span class="ticket-preview">{{item.content}}</span><span class="ticket-list-meta">{{date(item.createdAt)}}<span v-if="admin">{{item.username}}</span></span></button><div v-if="!items.length" class="center-empty"><Bell :size="30"/><p>{{loading?'正在加载消息…':'暂无系统消息'}}</p></div></div><footer class="center-pagination"><span>共 {{total}} 条 · 第 {{page}} 页</span><button class="secondary-button" :disabled="page<=1||loading" @click="page--;load()">上一页</button><button class="secondary-button" :disabled="page*20>=total||loading" @click="page++;load()">下一页</button></footer></template>
 </section>
</template>
