<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch, defineAsyncComponent } from 'vue'
import { ArrowUp, Brain, Globe, Square, LoaderCircle, ChevronLeft, ChevronRight, LogOut, Menu, MessageSquarePlus, MoreHorizontal, Settings, Trash2, Pencil, Search, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import MessageBubble from '../components/chat/MessageBubble.vue'
import QuestionNavigator from '../components/chat/QuestionNavigator.vue'
import KnowledgeBasePicker from '../components/chat/KnowledgeBasePicker.vue'
import DocumentReader from '../components/evidence/DocumentReader.vue'
import FeedbackBubble from '../components/FeedbackBubble.vue'
import ImageComposer from '../components/chat/ImageComposer.vue'
import { useSmoothScroll } from '../components/chat/useSmoothScroll'
import ThemeToggle from '../components/ThemeToggle.vue'
import { useChatStore } from '../stores/chat'
import { useSessionStore } from '../stores/session'
import type { Citation } from '../types'

const chat = useChatStore()
const session = useSessionStore()
const router = useRouter()
const StockAnalysisWorkspace=defineAsyncComponent(()=>import('../components/stock/StockAnalysisWorkspace.vue'))
const analysisSelection=ref<{datasetRef:string;index:number}|null>(null)
const analysisFocus=ref<HTMLElement|null>(null)
function openAnalysis(datasetRef:string,index:number){
  if(!analysisSelection.value)analysisFocus.value=document.activeElement as HTMLElement
  analysisSelection.value={datasetRef,index};closeMenus()
  nextTick(()=>document.querySelector<HTMLButtonElement>('[aria-label="关闭全屏分析"]')?.focus())
}
function closeAnalysis(){analysisSelection.value=null;nextTick(()=>{
  const target=analysisFocus.value?.isConnected?analysisFocus.value:document.querySelector<HTMLElement>('.composer textarea')
  target?.focus({preventScroll:true})
})}
watch(()=>chat.activeConversation?.id,()=>{analysisSelection.value=null})
const input = ref('')
const images=ref<import('../types').ChatImage[]>([])
const imageComposer=ref<InstanceType<typeof ImageComposer>|null>(null)
const imagePreviewTarget=ref<HTMLElement|null>(null)
const uploadingImages=ref(false)
const historySearch=ref('')
const historyList = ref<HTMLElement | null>(null)
let historyResizeObserver: ResizeObserver | undefined
function updateHistoryEdges() {
  const list = historyList.value
  if (!list) return
  const remaining = list.scrollHeight - list.clientHeight - list.scrollTop
  list.style.setProperty('--history-fade-top', `${Math.min(18, Math.max(0, list.scrollTop))}px`)
  list.style.setProperty('--history-fade-bottom', `${Math.min(18, Math.max(0, remaining))}px`)
}
const visibleConversations=computed(()=>chat.conversations.filter(item=>item.title.toLocaleLowerCase().includes(historySearch.value.trim().toLocaleLowerCase())))
watch(visibleConversations, () => nextTick(updateHistoryEdges), { flush: 'post' })
onMounted(() => {
  updateHistoryEdges()
  if (typeof ResizeObserver !== 'undefined' && historyList.value) {
    historyResizeObserver = new ResizeObserver(updateHistoryEdges)
    historyResizeObserver.observe(historyList.value)
  }
})
onBeforeUnmount(() => historyResizeObserver?.disconnect())
const activeCitation = ref<Citation | null>(null)
const transcript = ref<HTMLElement | null>(null)
const transcriptMotion = useSmoothScroll(transcript)
const managingConversation = ref<import('../types').Conversation | null>(null)
const conversationTitle = ref('')
const managing = ref(false)
const userMenu = ref(false)
const renameTarget = ref<import('../types').Conversation | null>(null)
const deleteConfirm = ref(false)
const menuPosition = ref({left:'0px',top:'0px'})
const menuTrigger = ref<HTMLElement|null>(null)
const floatingMenu = ref<HTMLElement|null>(null)
let menuAbove = false
function closeMenus() { managingConversation.value=null;userMenu.value=false;deleteConfirm.value=false }
function outsideMenu(event:PointerEvent) { if(!(event.target as HTMLElement).closest('.floating-menu,.conversation-menu,.sidebar-user'))closeMenus() }
function positionMenu(event:MouseEvent,user=false) {
  menuTrigger.value=event.currentTarget as HTMLElement
  menuAbove=user
}
function updateMenuPosition() {
  if (!menuTrigger.value || !floatingMenu.value) return
  const anchor = menuAbove ? menuTrigger.value.querySelector('svg:last-child') || menuTrigger.value : menuTrigger.value
  const r=anchor.getBoundingClientRect()
  const {width,height}=floatingMenu.value.getBoundingClientRect()
  const above=r.top-height-6, below=r.bottom+6
  const top=menuAbove ? (above>=8?above:below) : (below+height<=window.innerHeight-8?below:above)
  menuPosition.value={left:`${Math.max(8,Math.min(r.right-width,window.innerWidth-width-8))}px`,top:`${Math.max(8,Math.min(top,window.innerHeight-height-8))}px`}
}
watch(deleteConfirm,()=>nextTick(updateMenuPosition))
function groupDate(value:string){const date=new Date(value);if(!Number.isFinite(date.getTime()))return '更早';const today=new Date();today.setHours(0,0,0,0);const days=Math.floor((today.getTime()-date.getTime())/86400000)+1;return days<=0?'今天':days===1?'昨天':days<7?'过去 7 天':days<30?'过去 30 天':`${date.getFullYear()} 年 ${date.getMonth()+1} 月`}
function editTitle(){renameTarget.value=managingConversation.value;closeMenus();nextTick(()=>document.querySelector<HTMLInputElement>('.conversation-rename input')?.focus())}
function focusMenu(){nextTick(()=>{updateMenuPosition();floatingMenu.value?.querySelector<HTMLButtonElement>('button')?.focus({preventScroll:true})})}
function openUserMenu(event:MouseEvent){const was=userMenu.value;closeMenus();if(!was){positionMenu(event,true);userMenu.value=true;focusMenu()}}
function menuKeys(event:KeyboardEvent){
 if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return
 event.preventDefault();const buttons=Array.from(document.querySelectorAll<HTMLButtonElement>('.floating-menu button:not(:disabled)'));const i=buttons.indexOf(document.activeElement as HTMLButtonElement)
 buttons[event.key==='Home'?0:event.key==='End'?buttons.length-1:(i+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus()
}
const mobileSidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const readerCollapsed = ref(false)
function openEvidence(citation: Citation) { activeCitation.value = citation; readerCollapsed.value = false }
const followAnswer = ref(true)
const lastQuestion = ref<HTMLElement | null>(null)
const replySpace = ref(0)
watch(() => chat.sessionRevision, () => {
  input.value = ''
  images.value=[];uploadingImages.value=false
  historySearch.value = ''
  activeCitation.value = null
  managingConversation.value = null
  conversationTitle.value = ''
  closeMenus();renameTarget.value=null
  replySpace.value = 0
}, { flush: 'sync' })
watch(() => chat.activeConversation?.id, () => {
  transcriptMotion.stop()
  images.value=[];uploadingImages.value=false
  activeCitation.value = null
  replySpace.value = 0
})
let lastTranscriptTop = 0
function trackTranscriptScroll() {
  const el = transcript.value
  if (!el) return
  if (!transcriptMotion.isMoving()) {
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight
    followAnswer.value = followAnswer.value ? remaining < 80 : remaining < 4 && el.scrollTop > lastTranscriptTop
  }
  lastTranscriptTop = el.scrollTop
}
function pauseTranscriptFollow() { transcriptMotion.stop(); followAnswer.value = false; lastTranscriptTop = transcript.value?.scrollTop ?? 0 }
function returnToLatest() { followAnswer.value = true; transcriptMotion.bottom() }

onMounted(() => {chat.load();document.addEventListener('pointerdown',outsideMenu);window.addEventListener('resize',closeMenus)})
onBeforeUnmount(() => {chat.leavePage();document.removeEventListener('pointerdown',outsideMenu);window.removeEventListener('resize',closeMenus)})
async function onAnswerRendered() {
  await nextTick()
  if (!followAnswer.value || !transcript.value) return
  const latest = transcript.value.querySelector('.message-row.assistant:last-child') as HTMLElement | null
  if (latest && latest.offsetHeight > replySpace.value) transcriptMotion.bottom()
}
async function send() {
  const value = input.value.trim() || (images.value.length?'请分析这些图片':'')
  if (!value || uploadingImages.value || chat.sending || chat.submitting || chat.loading || (chat.ragEnabled&&!chat.selectedKnowledgeBaseId)) return
  const imageIds=images.value.map(image=>image.id)
  input.value = ''
  followAnswer.value = true
  const accepted = await chat.send(value,{imageIds})
  if(accepted)images.value=[]
  if (!accepted && !input.value) input.value = value
}
function editFailedQuestion() { input.value = chat.failedQuestion; chat.error = '' }
function onComposerKey(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); void send() }
}
watch(() => chat.messages.filter(item => item.role === 'USER').length, async (count, previous) => {
  if (count <= previous || !chat.sending) return
  await nextTick()
  if (transcript.value) {
    const rows = transcript.value.querySelectorAll<HTMLElement>('.message-row.user')
    lastQuestion.value = rows.item(rows.length - 1)
    replySpace.value = Math.max(0, transcript.value.clientHeight - (lastQuestion.value?.offsetHeight ?? 60) - 100)
    await nextTick()
    if (lastQuestion.value) transcript.value.scrollTo({ top: lastQuestion.value.offsetTop - transcript.value.offsetTop - 24, behavior: 'auto' })
  }
})
async function logout() { await session.logout(); await router.replace('/login') }
function closeMobileSidebar() { mobileSidebarOpen.value = false }
function openMobileSidebar() { sidebarCollapsed.value = false; mobileSidebarOpen.value = true }
function startNewConversation() { chat.startNew(); closeMobileSidebar() }
function conversationRunning(conversation: import('../types').Conversation) {
  return !!conversation.activeRunId || (chat.activeConversation?.id === conversation.id && (chat.sending || chat.submitting))
}
watch(() => chat.conversations.filter(conversationRunning).map(c => c.id), ids => {
  if (managingConversation.value && ids.includes(managingConversation.value.id)) closeMenus()
  if (renameTarget.value && ids.includes(renameTarget.value.id)) renameTarget.value = null
})
async function openConversation(conversation: import('../types').Conversation) {
  followAnswer.value = true
  await chat.openConversation(conversation)
  await nextTick()
  if (chat.activeConversation?.id === conversation.id && transcript.value) {
    transcript.value.scrollTo({ top: transcript.value.scrollHeight, behavior: 'auto' })
    followAnswer.value = true
  }
  closeMobileSidebar()
}
async function openAdmin() { closeMobileSidebar(); await router.push('/admin') }
function openConversationManager(conversation: import('../types').Conversation, event:MouseEvent) {
  if (conversationRunning(conversation)) return
  closeMenus();positionMenu(event)
  managingConversation.value = conversation
  conversationTitle.value = conversation.title
  focusMenu()
}
async function renameConversation() {
  if (!renameTarget.value || managing.value || conversationRunning(renameTarget.value)) return
  if (!conversationTitle.value.trim() || conversationTitle.value.trim() === renameTarget.value.title) { renameTarget.value = null; return }
  managing.value = true
  try {
    await chat.renameConversation(renameTarget.value, conversationTitle.value.trim())
    renameTarget.value = null
  } catch(e) {chat.error=e instanceof Error?e.message:'重命名失败'
  } finally { managing.value = false }
}
async function deleteConversation() {
  if (!managingConversation.value || conversationRunning(managingConversation.value)) return
  if (!deleteConfirm.value) {deleteConfirm.value=true;return}
  managing.value = true
  try {
    await chat.deleteConversation(managingConversation.value)
    managingConversation.value = null
    activeCitation.value = null
  } catch(e) {chat.error=e instanceof Error?e.message:'删除失败'} finally { managing.value = false }
}
</script>

<template>
  <div class="chat-shell" :class="{ 'reader-open': activeCitation && !readerCollapsed, 'sidebar-collapsed': sidebarCollapsed, 'analysis-mode':!!analysisSelection }" @keydown.esc="analysisSelection?closeAnalysis():closeMobileSidebar()">
    <StockAnalysisWorkspace v-if="analysisSelection" :messages="chat.messages" :selection="analysisSelection" @close="closeAnalysis" @reference="input=(input?input+'\n':'')+$event"/>
    <button v-if="mobileSidebarOpen" class="mobile-sidebar-scrim" aria-label="关闭对话导航" @click="closeMobileSidebar"></button>
    <aside class="conversation-sidebar" :class="{ 'mobile-open': mobileSidebarOpen }">
      <header class="sidebar-header"><strong v-if="!sidebarCollapsed">股票研究工作台</strong><button class="icon-button" title="新建对话" aria-label="新建对话" @click="startNewConversation"><MessageSquarePlus :size="18" /></button></header>
      <div class="history-search-region">
        <div v-if="!sidebarCollapsed" class="history-search"><Search class="history-search-icon" :size="16" aria-hidden="true"/><input v-model="historySearch" type="search" aria-label="搜索对话标题" placeholder="搜索对话标题"/><button v-if="historySearch" class="icon-button" aria-label="清除搜索" @click="historySearch='' "><X :size="14"/></button></div>
      </div>
      <nav ref="historyList" class="conversation-list" aria-label="对话列表" @scroll.passive="updateHistoryEdges">
        <template v-for="(conversation,index) in visibleConversations" :key="conversation.id">
        <div v-if="index===0||groupDate(visibleConversations[index-1].updatedAt)!==groupDate(conversation.updatedAt)" class="history-group">{{groupDate(conversation.updatedAt)}}</div>
        <div v-if="renameTarget?.id===conversation.id" class="conversation-rename"><input v-model="conversationTitle" aria-label="对话标题" maxlength="200" :readonly="managing" @keydown.enter.prevent="!$event.isComposing && renameConversation()" @keydown.esc.prevent="renameTarget=null" @blur="renameConversation"/></div>
        <div v-else class="conversation-item"
             :class="{ active: chat.activeConversation?.id === conversation.id }">
          <button class="conversation-open" :title="conversation.title" @click="openConversation(conversation)"><span>{{ conversation.title }}</span><i v-if="conversation.unread && !conversationRunning(conversation)" class="conversation-unread" aria-label="有新回复" /></button>
          <span v-if="conversationRunning(conversation)" class="conversation-run-status" role="status" aria-label="正在回复"><LoaderCircle class="conversation-spinner" :size="14" aria-hidden="true" /></span>
          <button v-else class="conversation-menu" aria-haspopup="menu" :aria-expanded="managingConversation?.id===conversation.id" :title="`管理 ${conversation.title}`" @click="openConversationManager(conversation,$event)"><MoreHorizontal :size="16" /></button>
        </div>
        </template>
        <div v-if="!visibleConversations.length && !chat.loading" class="list-empty">{{historySearch?'没有匹配的对话':'暂无对话'}}</div>
      </nav>
      <footer class="sidebar-footer">
        <button class="sidebar-user" :title="session.user?.username" aria-label="用户菜单" aria-haspopup="menu" :aria-expanded="userMenu" @click="openUserMenu"><span class="user-avatar">{{ session.user?.username?.slice(0, 1).toUpperCase() || 'U' }}</span><span v-if="!sidebarCollapsed" class="user-name">{{ session.user?.username }}</span><MoreHorizontal v-if="!sidebarCollapsed" :size="16" /></button>
      </footer>
    </aside>

    <main class="conversation-workspace">
      <button class="panel-grip history-grip" :aria-label="sidebarCollapsed ? '展开历史侧栏' : '收起历史侧栏'" :aria-expanded="!sidebarCollapsed" @click="sidebarCollapsed = !sidebarCollapsed"><ChevronRight v-if="sidebarCollapsed" :size="12" /><ChevronLeft v-else :size="12" /></button>
      <button v-if="activeCitation" class="panel-grip reader-grip" :aria-label="readerCollapsed ? '展开原文阅读器' : '收起原文阅读器'" :aria-expanded="!readerCollapsed" @click="readerCollapsed = !readerCollapsed"><ChevronLeft v-if="readerCollapsed" :size="12" /><ChevronRight v-else :size="12" /></button>
      <header class="conversation-header"><button class="icon-button mobile-menu-button" aria-label="打开对话导航" title="对话导航" @click="openMobileSidebar"><Menu :size="18" /></button><strong>{{ chat.activeConversation?.title || '股票研究' }}</strong><span class="stock-market-status"><i class="stock-status-dot" :class="{offline:!chat.marketOnline}"/>{{chat.marketAsOf?'日线截至 '+chat.marketAsOf:'行情未连接'}}</span><ThemeToggle/></header>
      <section ref="transcript" class="message-transcript" :style="{ '--reply-space': `${replySpace}px` }" @scroll="trackTranscriptScroll" @wheel.passive="pauseTranscriptFollow" @touchstart.passive="pauseTranscriptFollow">
        <div v-if="!chat.messages.length" class="chat-empty"><h1>股票研究</h1><div class="stock-quick-queries"><button @click="input='分析平安银行最近300个交易日，绘制日线、MA5和MA20'">平安银行 · 趋势</button><button @click="input='在100只创业板股票样本中，筛选最新交易日MA5上穿MA20的股票，剔除ST'">均线金叉 · 选股</button><button @click="input='统计平安银行收盘上穿MA20后1、3、5、10根日线的收益分布，冷却期10根'">事件 · 收益分布</button></div></div>
        <MessageBubble v-for="message in chat.messages" :key="message.id" :message="message" :analysis-mode="!!analysisSelection" :busy="chat.sending || chat.submitting || chat.loading" :show-diagnostics="session.isAdmin" @open-evidence="openEvidence" @rendered="onAnswerRendered" @edit="chat.send($event, { editMessageId: message.id })" @regenerate="chat.send('', { regenerateMessageId: message.id })" @vote="chat.vote(message, $event)" @reference="input=(input?input+'\n':'')+$event" @analysis="openAnalysis" />
      </section>
      <QuestionNavigator :messages="chat.messages" :container="transcript" @navigate="pauseTranscriptFollow" />
      <div v-if="chat.error" class="chat-error" role="alert"><span>{{ chat.error }}</span><div class="chat-error-actions">
        <button v-if="chat.failedQuestion" :disabled="chat.sending" @click="chat.send(chat.failedQuestion)">重试本轮</button>
        <button v-if="chat.failedQuestion" :disabled="chat.sending" @click="editFailedQuestion">重新编辑问题</button>
        <button v-if="!chat.failedQuestion" :disabled="chat.loading" @click="chat.load()">重新加载</button>
        <button aria-label="关闭提示" @click="chat.error = ''"><X :size="14" /></button>
      </div></div>
      <footer class="composer-footer">
      <button v-if="chat.sending || chat.submitting" class="latest-reply-button" type="button" aria-label="回到最新回复" title="回到底部并跟随回复" @click="returnToLatest"><MoreHorizontal :size="19" aria-hidden="true"/></button>
      <div v-if="chat.ragEnabled" class="stock-knowledge-row"><KnowledgeBasePicker v-model="chat.selectedKnowledgeBaseId" :options="chat.knowledgeBases" :disabled="!!chat.activeConversation" /></div>
      <form class="composer" @submit.prevent="send" @paste="imageComposer?.paste($event)">
        <div ref="imagePreviewTarget" class="composer-image-preview"></div>
        <textarea v-model="input" rows="2" maxlength="8192" placeholder="查询股票、筛选条件或研究策略…" aria-label="问题"
                  @keydown="onComposerKey" />
        <div class="composer-tools">
          <ImageComposer :key="chat.sessionRevision+':'+(chat.activeConversation?.id||'new')" ref="imageComposer" v-model="images" :preview-target="imagePreviewTarget" :disabled="chat.sending||chat.submitting" @busy="uploadingImages=$event"/>
          <label v-if="chat.webAvailable" class="thinking-control" :class="{selected:chat.webEnabled}" title="联网搜索与网页浏览">
            <input v-model="chat.webEnabled" type="checkbox" aria-label="联网搜索与浏览" :disabled="chat.sending||chat.submitting"/>
            <Globe :size="16" aria-hidden="true"/><span class="thinking-label">联网</span>
          </label>
          <label class="thinking-control" :class="{ selected: chat.reasoningEnabled, unavailable: !chat.reasoningAvailable }" :title="chat.reasoningAvailable ? '控制本轮回答是否启用深度思考' : '当前没有支持思考切换的可用模型'">
            <input v-model="chat.reasoningEnabled" type="checkbox" aria-label="深度思考" :disabled="chat.sending || !chat.reasoningAvailable" />
            <Brain :size="16" aria-hidden="true" /><span class="thinking-label">深度思考</span>
          </label>
          <button v-if="chat.sending" class="send-button" type="button" title="停止回复" aria-label="停止回复" @click="chat.stop()"><Square :size="15" fill="currentColor" /></button>
          <button v-else class="send-button" type="submit" :disabled="uploadingImages || chat.submitting || chat.loading || (!input.trim()&&!images.length) || (chat.ragEnabled&&!chat.selectedKnowledgeBaseId)" title="发送" aria-label="发送"><ArrowUp :size="21" /></button>
        </div>
      </form>
      <p class="composer-disclaimer">研究分析不构成投资建议 · 数据非实时 · 历史表现不代表未来收益</p>
      </footer>
      <FeedbackBubble :draft="input" />
    </main>

    <Transition name="reader">
      <DocumentReader v-if="activeCitation" v-show="!readerCollapsed" :citation="activeCitation" @close="activeCitation = null" />
    </Transition>

    <Teleport to="body"><div v-if="managingConversation||userMenu" ref="floatingMenu" class="floating-menu" role="menu" :style="menuPosition" @keydown="menuKeys" @keydown.esc="closeMenus();menuTrigger?.focus()">
      <template v-if="managingConversation"><button role="menuitem" @click="editTitle"><Pencil :size="16"/>重命名</button><button role="menuitem" class="destructive" :disabled="managing||!!managingConversation.activeRunId" @click="deleteConversation"><Trash2 :size="16"/>{{deleteConfirm?'确认删除此对话':'删除'}}</button><button v-if="deleteConfirm" role="menuitem" @click="closeMenus">取消</button></template>
      <template v-else><button v-if="session.isAdmin" role="menuitem" @click="closeMenus();openAdmin()"><Settings :size="16"/>系统管理</button><button role="menuitem" @click="closeMenus();logout()"><LogOut :size="16"/>退出登录</button></template>
    </div></Teleport>
  </div>
</template>
