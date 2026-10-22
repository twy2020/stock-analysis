import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import { progressLabel } from '../components/chat/progress'
import { failureMessage } from '../components/chat/failure'
import { api, streamApi, ApiError } from '../api/client'
import type { Conversation, KnowledgeBase, Message } from '../types'

type Run = { id: string; conversationId: string; userMessageId: string; assistantMessageId: string; status: string }
const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16)); bytes[6] = (bytes[6]! & 15) | 64; bytes[8] = (bytes[8]! & 63) | 128
  const h = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`
}
export const useChatStore = defineStore('chat', {
  state: () => ({
    knowledgeBases: [] as KnowledgeBase[], conversations: [] as Conversation[],
    activeConversation: null as Conversation | null, messages: [] as Message[],
    selectedKnowledgeBaseId: '', ragEnabled:false, ragAvailable:false, marketAsOf:'', marketOnline:false, loading: false, sending: false, submitting: false, error: '',
    reasoningEnabled: false, reasoningAvailable: false, sessionRevision: 0, viewRevision: 0,
    webEnabled: false, webAvailable: false,
    streamController: null as AbortController | null, failedQuestion: '',
    pollTimer: null as ReturnType<typeof setInterval> | null, polling: false,
  }),
  actions: {
    detach() { this.streamController?.abort(); this.streamController = null },
    leavePage() { this.detach(); if (this.pollTimer) clearInterval(this.pollTimer); this.pollTimer = null },
    resetForSession() { const revision = this.sessionRevision + 1; this.leavePage(); this.$reset(); this.sessionRevision = revision },
    async stop() {
      const c = this.activeConversation
      if (!c?.activeRunId) return
      try { await api(`/api/v1/conversations/${c.id}/runs/${c.activeRunId}/cancel`, { method: 'POST' }) }
      catch (e) { this.error = e instanceof Error ? e.message : '停止失败' }
    },
    async load() {
      const revision = this.sessionRevision
      this.loading = true; this.error = ''
      try {
        const [bases, conversations, capabilities] = await Promise.all([
          api<KnowledgeBase[]>('/api/v1/knowledge-bases'), api<Conversation[]>('/api/v1/conversations'),
          api<{ reasoningToggle: boolean; ragAvailable?:boolean; webAvailable?:boolean }>('/api/v1/conversations/capabilities'),
        ])
        if (revision !== this.sessionRevision) return
        this.knowledgeBases = bases; this.conversations = conversations
        this.reasoningAvailable = capabilities.reasoningToggle
        this.webAvailable = capabilities.webAvailable === true
        if (!this.webAvailable) this.webEnabled = false
        this.ragAvailable=capabilities.ragAvailable??true
        this.ragEnabled=this.ragAvailable
        void api<{last_date?:string}>('/api/v1/stock/health').then(health=>{if(revision===this.sessionRevision){this.marketAsOf=health.last_date??'';this.marketOnline=!!health.last_date}}).catch(()=>{if(revision===this.sessionRevision)this.marketOnline=false})
        if (!this.reasoningAvailable) this.reasoningEnabled = false
        if (!this.selectedKnowledgeBaseId && bases.length) this.selectedKnowledgeBaseId = bases[0]!.id
        if (this.activeConversation) await this.openConversation(this.activeConversation)
      } catch (e) { if (revision === this.sessionRevision) this.error = e instanceof Error ? e.message : '加载失败' }
      finally { if (revision === this.sessionRevision) {
        this.loading = false
        if (!this.pollTimer) this.pollTimer = setInterval(() => void this.refreshConversations(), 3000)
      } }
    },
    async acknowledge(c: Conversation) {
      if (document.visibilityState !== 'visible' || !c.unread || !c.completedRunId) return
      const revision = this.sessionRevision
      const result = await api<Conversation>(`/api/v1/conversations/${c.id}/read`, { method: 'POST', body: JSON.stringify({ runId: c.completedRunId }) })
      if (revision !== this.sessionRevision) return
      const row = this.conversations.find(v => v.id === result.id)
      if (row) row.unread = result.unread
    },
    async refreshConversations() {
      if (this.polling) return
      const revision = this.sessionRevision
      this.polling = true
      try {
        const rows = await api<Conversation[]>('/api/v1/conversations')
        if (revision !== this.sessionRevision) return
        this.conversations = rows
        const c = rows.find(v => v.id === this.activeConversation?.id)
        if (c && !this.submitting && !this.loading) {
          const changed = c.completedRunId !== this.activeConversation?.completedRunId
          this.activeConversation = c; this.sending = !!c.activeRunId
          if (!this.streamController && (c.activeRunId || changed)) await this.openConversation(c)
          else if (!this.streamController && !changed) await this.acknowledge(c)
        }
      } catch { /* Observer disconnection never changes the persisted job status. */ }
      finally { if (revision === this.sessionRevision) this.polling = false }
    },
    async openConversation(conversation: Conversation) {
      const sameConversation = this.activeConversation?.id === conversation.id
      this.detach(); this.error = ''; this.failedQuestion = ''
      const revision = this.sessionRevision, view = ++this.viewRevision
      this.activeConversation = conversation
      // Polling a completed run must not unmount the transcript and reset its scroll height.
      if (!sameConversation) this.messages = []
      this.loading = true; this.sending = !!conversation.activeRunId
      this.selectedKnowledgeBaseId = conversation.knowledgeBaseId ?? this.selectedKnowledgeBaseId
      this.ragEnabled=this.ragAvailable&&!!conversation.knowledgeBaseId
      try {
        const c = await api<Conversation>(`/api/v1/conversations/${conversation.id}`)
        if (revision !== this.sessionRevision || view !== this.viewRevision) return
        const messages = await api<Message[]>(`/api/v1/conversations/${conversation.id}/messages`)
        if (revision !== this.sessionRevision || view !== this.viewRevision) return
        this.activeConversation = c; this.messages = messages; this.sending = !!c.activeRunId
        if (c.activeRunId) {
          const run = await api<Run>(`/api/v1/conversations/${c.id}/runs/${c.activeRunId}`)
          if (revision !== this.sessionRevision || view !== this.viewRevision) return
          void this.observe(run)
        } else await this.acknowledge(c)
      } catch (e) { if (revision === this.sessionRevision && view === this.viewRevision) this.error = e instanceof Error ? e.message : '加载失败' }
      finally { if (revision === this.sessionRevision && view === this.viewRevision) this.loading = false }
    },
    startNew() {
      this.detach(); this.viewRevision++; this.activeConversation = null; this.messages = []
      this.ragEnabled=this.ragAvailable
      this.error = ''; this.failedQuestion = ''; this.sending = false; this.loading = false
    },
    async observe(run: Run) {
      this.detach()
      const controller = markRaw(new AbortController())
      this.streamController = controller
      const revision = this.sessionRevision, view = this.viewRevision
      const assistant = this.messages.find(m => m.id === run.assistantMessageId)
      if (!assistant) { this.streamController = null; return }
      Object.assign(assistant, { content: '', citations: [], stockArtifacts:[], reasoningContent: '', processEvents: [], status: 'STREAMING', errorCode:undefined })
      let cursor = 0, finished = false, attempts = 0
      const current = () => revision === this.sessionRevision && view === this.viewRevision && !controller.signal.aborted
      while (current() && !finished) {
        try {
          await streamApi(`/api/v1/conversations/${run.conversationId}/runs/${run.id}/events?after=${cursor}`, null, (name, p) => {
            if (!current() || (p.eventId && p.eventId <= cursor)) return
            cursor = p.eventId ?? cursor; attempts = 0
            if (name === 'progress') {
              if (typeof p.stage !== 'string') return
              const events = assistant.processEvents ??= []
              events.push({ ...p, stage: p.stage })
              assistant.statusText = progressLabel({ ...p, stage: p.stage })
            } else if (name === 'answer_reset') { assistant.content = '' }
            else if (name === 'model') { assistant.model = p.model; assistant.reasoningEnabled = p.reasoningEnabled }
            else if (name === 'delta') { assistant.content += p.content ?? ''; assistant.statusText = '正在回复' }
            else if (name === 'reasoning') { assistant.reasoningContent = (assistant.reasoningContent ?? '') + (p.content ?? ''); assistant.reasoningEnabled = true }
            else if (name === 'retrieval') { assistant.citations = p.citations ?? []; assistant.retrieval = p.retrieval }
            else if(name==='stock_artifact'){
              const artifacts=assistant.stockArtifacts??=[]
              if(p.artifact&&!artifacts.some(a=>a.datasetRef===p.artifact.datasetRef))artifacts.push(p.artifact)
            }
            else if (name === 'complete') {
              Object.assign(assistant, { status: 'COMPLETED', statusText: '', content: p.content, model: p.model, citations: p.citations ?? [], retrieval: p.retrieval,stockArtifacts:p.stockArtifacts??assistant.stockArtifacts??[] })
              finished = true
            } else if (name === 'error') {
              assistant.status = 'FAILED'; assistant.statusText = ''; finished = true
              assistant.errorCode = p.code
              this.error = failureMessage(p.code)
            }
          }, controller.signal, 'GET')
        } catch (e) {
          if (!current()) break
          if (e instanceof ApiError && e.status === 401) {
            this.error = '登录已过期，请重新登录'
            this.sending = false
            break
          }
          assistant.statusText = '连接恢复中，后台仍在处理'
          await pause(Math.min(1000 * ++attempts, 5000))
        }
      }
      if (this.streamController === controller) {
        this.streamController = null
        if (finished) {
          this.sending = false
          if (this.activeConversation?.id === run.conversationId) this.activeConversation.activeRunId = null
          void this.refreshConversations()
        }
      }
    },
    async send(content: string, options: { editMessageId?: string; regenerateMessageId?: string; imageIds?: string[] } = {}) {
      if (this.sending || this.submitting || (!content.trim() && !options.regenerateMessageId) || (this.ragEnabled&&!this.selectedKnowledgeBaseId)) return false
      const revision = this.sessionRevision, view = this.viewRevision
      this.submitting = true; this.error = ''; this.failedQuestion = ''
      try {
        let c = this.activeConversation
        if (!c) {
          c = await api<Conversation>('/api/v1/conversations', { method: 'POST', body: JSON.stringify({ title: content.trim().slice(0,32), knowledgeBaseId: this.ragEnabled?this.selectedKnowledgeBaseId:null }) })
          if (revision !== this.sessionRevision || view !== this.viewRevision) return false
          this.activeConversation = c; this.conversations.unshift(c)
        }
        const run = await api<Run>(`/api/v1/conversations/${c.id}/runs`, { method: 'POST', body: JSON.stringify({ content, ...options, reasoningEnabled: this.reasoningEnabled, webEnabled:this.webAvailable&&this.webEnabled, requestId: requestId() }) })
        if (revision !== this.sessionRevision || view !== this.viewRevision) return true
        this.activeConversation!.activeRunId = run.id; this.sending = true
        const messages = await api<Message[]>(`/api/v1/conversations/${c.id}/messages`)
        if (revision !== this.sessionRevision || view !== this.viewRevision) return true
        this.messages = messages; void this.observe(run)
        return true
      } catch (e) {
        if (revision === this.sessionRevision && view === this.viewRevision) { this.failedQuestion = content; this.error = e instanceof Error ? e.message : '发送失败' }
        return false
      } finally { if (revision === this.sessionRevision) this.submitting = false }
    },
    async vote(message: Message, vote: number) {
      const c = this.activeConversation, revision = this.sessionRevision
      if (!c) return
      try {
        const result = await api<{ vote: number }>(`/api/v1/conversations/${c.id}/messages/${message.id}/vote`, { method: 'POST', body: JSON.stringify({ vote: message.vote === vote ? 0 : vote }) })
        if (revision === this.sessionRevision) message.vote = result.vote
      } catch (e) { this.error = e instanceof Error ? e.message : '保存失败' }
    },
    async renameConversation(c: Conversation, title: string) {
      const revision = this.sessionRevision
      const updated = await api<Conversation>(`/api/v1/conversations/${c.id}`, { method: 'PATCH', body: JSON.stringify({ title }) })
      if (revision !== this.sessionRevision) return
      const index = this.conversations.findIndex(v => v.id === updated.id)
      if (index >= 0) this.conversations[index] = updated
      if (this.activeConversation?.id === updated.id) this.activeConversation = updated
    },
    async deleteConversation(c: Conversation) {
      const revision = this.sessionRevision
      await api(`/api/v1/conversations/${c.id}`, { method: 'DELETE' })
      if (revision !== this.sessionRevision) return
      this.conversations = this.conversations.filter(v => v.id !== c.id)
      if (this.activeConversation?.id === c.id) this.startNew()
    },
  },
})
