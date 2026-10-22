<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Bell, MessageCircle, History, X } from 'lucide-vue-next'
import { api } from '../api/client'
import { useChatStore } from '../stores/chat'
import FeedbackForm from './feedback/FeedbackForm.vue'
import TicketInbox from './feedback/TicketInbox.vue'
import Announcements from './feedback/Announcements.vue'
import '../styles/message-center.css'
defineProps<{draft:string}>()
const chat=useChatStore(),dialog=ref<HTMLDialogElement|null>(null),trigger=ref<HTMLButtonElement|null>(null)
const opened=ref(false),pending=ref(false),section=ref<'system'|'feedback'|'history'>('feedback'),ticket=ref(''),notice=ref('')
const counts=ref({system:0,feedback:0})
let polling=false,refreshAgain=false,controller=new AbortController()
async function refresh(){
 if(document.visibilityState==='hidden')return
 if(polling){refreshAgain=true;return}
 polling=true;const revision=chat.sessionRevision,signal=controller.signal
 try{const result=await api<typeof counts.value>('/api/v1/message-center/unread',{signal});if(revision===chat.sessionRevision&&!signal.aborted)counts.value=result}
 catch{/* Content panels expose errors and retry; background checks stay quiet. */}finally{polling=false;if(refreshAgain&&!signal.aborted){refreshAgain=false;void refresh()}}
}
async function open(){opened.value=true;await nextTick();dialog.value?.showModal();void refresh()}
function close(){if(pending.value)return;dialog.value?.close();opened.value=false;notice.value='';trigger.value?.focus()}
function submitted(id:string){ticket.value=id;section.value='history';notice.value='反馈已提交，已生成工单';void refresh()}
function choose(value:'system'|'feedback'|'history'){section.value=value;ticket.value='';notice.value=''}
function visibility(){if(document.visibilityState==='visible')void refresh()}
const timer=setInterval(refresh,15000)
onMounted(()=>{void refresh();document.addEventListener('visibilitychange',visibility)})
watch(()=>chat.sessionRevision,()=>{controller.abort();controller=new AbortController();dialog.value?.close();opened.value=false;pending.value=false;section.value='feedback';ticket.value='';notice.value='';counts.value={system:0,feedback:0};polling=false})
onUnmounted(()=>{controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visibility)})
</script>
<template>
 <button ref="trigger" class="feedback-bubble" type="button" aria-label="消息中心" :title="counts.system+counts.feedback?'消息中心 · 有未读消息':'消息中心与反馈'" @click="open"><MessageCircle :size="21"/><span v-if="counts.system+counts.feedback>0" class="notification-dot" aria-label="有未读消息"/></button>
 <dialog ref="dialog" class="message-center-dialog" aria-labelledby="message-center-title" @cancel.prevent="close">
  <header class="center-header"><h2 id="message-center-title">消息中心</h2><button class="icon-button" type="button" aria-label="关闭消息中心" :disabled="pending" @click="close"><X :size="18"/></button></header>
  <div v-if="opened" class="message-center-body">
   <nav class="center-nav" aria-label="消息分类"><button data-section="system" :class="{active:section==='system'}" :aria-current="section==='system'?'page':undefined" :disabled="pending" @click="choose('system')"><Bell :size="18"/><span>系统消息</span><i v-if="counts.system" class="notification-dot inline"/></button><button data-section="feedback" :class="{active:section==='feedback'}" :aria-current="section==='feedback'?'page':undefined" :disabled="pending" @click="choose('feedback')"><MessageCircle :size="18"/><span>反馈</span></button><button data-section="history" :class="{active:section==='history'}" :aria-current="section==='history'?'page':undefined" :disabled="pending" @click="choose('history')"><History :size="18"/><span>历史反馈</span><i v-if="counts.feedback" class="notification-dot inline"/></button></nav>
   <div class="center-main"><p v-if="notice" class="center-notice" role="status">{{notice}}</p><FeedbackForm v-show="section==='feedback'" :draft="draft" @submitted="submitted" @busy="pending=$event"/><Announcements v-if="section==='system'" @updated="refresh"/><TicketInbox v-if="section==='history'" :ticket-id="ticket" @updated="refresh"/></div>
  </div>
 </dialog>
</template>
