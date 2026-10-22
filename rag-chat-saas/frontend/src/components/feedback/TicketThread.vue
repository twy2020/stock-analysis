<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue'
import { ArrowLeft, RefreshCw, Send, LockKeyhole, RotateCcw } from 'lucide-vue-next'
import { api } from '../../api/client'
import { type TicketDetail, statusLabels, date } from './types'
import ImageViewer from '../ImageViewer.vue'
const imageIndex=ref<number|null>(null)
const props=withDefaults(defineProps<{id:string;admin?:boolean;active?:boolean}>(),{active:true})
const emit=defineEmits<{back:[];updated:[]}>()
const detail=ref<TicketDetail|null>(null),error=ref(''),reply=ref(''),loading=ref(false),saving=ref(false),timeline=ref<HTMLElement|null>(null)
let version=0,controller=new AbortController()
const path=()=>`/api/v1/${props.admin?'admin/':''}feedback/${props.id}`
const isActive=()=>props.active!==false
async function acknowledge(value:TicketDetail){
 await api(`${path()}/read`,{method:'POST',body:JSON.stringify({through:value.latestReplyId||0}),signal:controller.signal});emit('updated')
}
async function load(quiet=false){
 if(saving.value||!isActive())return
 const seq=++version,endpoint=path();if(!quiet)loading.value=true;error.value=''
 try{const value=await api<TicketDetail>(endpoint,{signal:controller.signal});if(seq!==version||!isActive())return;const changed=detail.value?.latestReplyId!==value.latestReplyId;detail.value=value;await nextTick();if(seq!==version||!isActive())return;if(changed&&timeline.value)timeline.value.scrollTop=timeline.value.scrollHeight;if(value.unread)await acknowledge(value)}
 catch(e){if(seq===version&&!controller.signal.aborted)error.value=e instanceof Error?e.message:'读取失败'}
 finally{if(seq===version)loading.value=false}
}
async function mutate(options:RequestInit,suffix=''){
 if(saving.value||!detail.value)return
 const seq=++version;saving.value=true;error.value=''
 try{const value=await api<TicketDetail>(path()+suffix,{...options,signal:controller.signal});if(seq!==version)return
  if(suffix){detail.value=value;reply.value=''}else detail.value={...detail.value,...value}
  emit('updated');await nextTick();if(timeline.value)timeline.value.scrollTop=timeline.value.scrollHeight
 }catch(e){if(seq===version&&!controller.signal.aborted)error.value=e instanceof Error?e.message:'保存失败'}
 finally{if(seq===version){saving.value=false;loading.value=false}}
}
async function send(){if(!reply.value.trim())return;await mutate({method:'POST',body:JSON.stringify({body:reply.value.trim()})},'/replies')}
async function status(value:string){await mutate({method:'PATCH',body:JSON.stringify({status:value})});await load(true)}
watch(()=>props.id,()=>{controller.abort();controller=new AbortController();version++;detail.value=null;reply.value='';saving.value=false;void load()},{immediate:true})
watch(()=>props.active,value=>{if(value)void load(true);else imageIndex.value=null})
let checking=false
async function checkUpdates(){
 if(checking||saving.value||loading.value||!detail.value||props.active===false||document.visibilityState!=='visible')return
 checking=true;const seq=version
 try{const value=await api<TicketDetail>(path()+'?summary=true',{signal:controller.signal});if(seq===version&&(value.latestReplyId!==detail.value?.latestReplyId||value.status!==detail.value?.status))await load(true)}catch{/* Keep the current thread readable; manual refresh exposes errors. */}finally{checking=false}
}
const timer=setInterval(checkUpdates,15000)
onUnmounted(()=>{version++;controller.abort();clearInterval(timer)})
</script>
<template>
 <section class="ticket-thread">
  <header class="ticket-toolbar"><button class="icon-button" aria-label="返回工单列表" :disabled="saving" @click="emit('back')"><ArrowLeft :size="18"/></button><div class="ticket-title"><strong>{{detail?.ticketNumber||'工单详情'}}</strong><small v-if="detail">{{detail.username}} · {{date(detail.createdAt)}}</small></div><span v-if="detail" class="ticket-status" :data-status="detail.status">{{statusLabels[detail.status]}}</span><button class="icon-button" aria-label="刷新工单" :disabled="loading||saving" @click="load()"><RefreshCw :size="16"/></button></header>
  <p v-if="error" class="form-error ticket-error" role="alert">{{error}}</p>
  <div v-if="loading&&!detail" class="center-empty" role="status">正在加载工单…</div>
  <template v-if="detail">
   <div ref="timeline" class="ticket-timeline">
    <article class="ticket-entry"><header><strong>{{detail.username}}</strong><time>{{date(detail.createdAt)}}</time><span>提交反馈</span></header><p class="feedback-text">{{detail.comment}}</p><div v-if="detail.images.length" class="feedback-attachments"><button v-for="(image,index) in detail.images" :key="image.id" type="button" class="attachment-preview" :aria-label="`查看图片：${image.name}`" @click="imageIndex=index"><img :src="image.url" :alt="image.name" loading="lazy"/></button></div>
     <details class="ticket-snapshot"><summary>提交时的对话 · {{detail.conversationTitle}}</summary><p v-if="detail.snapshot?.knowledgeBase">{{detail.snapshot.knowledgeBase}}</p><p v-if="detail.snapshot?.error" class="form-error">{{detail.snapshot.error}}</p><p v-if="detail.snapshot?.truncated">仅保存了最近部分消息。</p><div class="feedback-transcript"><article v-for="(message,index) in detail.snapshot?.messages||[]" :key="index"><header>{{message.role==='USER'?'用户':'助手'}}</header><p>{{message.content||'（尚未输出）'}}</p></article><p v-if="!detail.snapshot?.messages?.length">当时没有对话内容</p></div><p v-if="detail.snapshot?.draft">草稿：{{detail.snapshot.draft}}</p></details>
    </article>
    <article v-for="item in detail.replies||[]" :key="item.id" class="ticket-entry" :class="{staff:item.role==='ADMIN',event:item.kind==='STATUS'}"><header><strong>{{item.role==='ADMIN'?'管理员':item.username}}</strong><time>{{date(item.createdAt)}}</time></header><p>{{item.body}}</p></article>
   </div>
   <div v-if="detail.status==='RESOLVED'" class="ticket-closed"><LockKeyhole :size="15"/><span>工单已关闭，记录仍可查看。</span><button v-if="admin" class="text-button" :disabled="saving" @click="status('NEW')"><RotateCcw :size="14"/>重新开启</button></div>
   <form v-else class="ticket-reply-form" @submit.prevent="send"><textarea v-model="reply" :aria-label="admin?'回复用户':'补充反馈'" :placeholder="admin?'回复用户的反馈…':'继续补充问题或说明…'" rows="3" maxlength="5000" :disabled="saving" required/><footer><span class="field-count">{{reply.length}} / 5000</span><div class="ticket-reply-actions"><button v-if="admin" type="button" class="secondary-button" :disabled="saving" @click="status('RESOLVED')">关闭工单</button><button class="primary-button" :disabled="saving||!reply.trim()"><Send :size="15"/>{{saving?'正在保存…':'发送回复'}}</button></div></footer></form>
  </template>
 <ImageViewer v-if="imageIndex!==null&&detail" :images="detail.images" :index="imageIndex" @close="imageIndex=null"/>
 </section>
</template>
