<script setup lang="ts">
import { computed, ref, nextTick, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { FileText, X, Copy, Check, Pencil, ThumbsUp, ThumbsDown, RotateCcw } from 'lucide-vue-next'
import type { Citation, Message } from '../../types'
import { renderMarkdown } from './renderMarkdown'
import WorkProcess from './WorkProcess.vue'
import MarkdownAnswer from './MarkdownAnswer'
import ImageAttachments from './ImageAttachments.vue'
import { useStreamingText } from './useStreamingText'
import { failureMessage } from './failure'
const StockArtifactView = defineAsyncComponent(()=>import('../stock/StockArtifact.vue'))

const props = defineProps<{ message: Message; showDiagnostics?: boolean; busy?: boolean; analysisMode?:boolean }>()
const emit = defineEmits<{ openEvidence: [citation: Citation]; rendered: []; edit: [content: string]; regenerate: []; vote: [value: number]; reference: [text:string]; analysis:[datasetRef:string,index:number] }>()
const editing = ref(false)
const editContent = ref('')
const userBubble = ref<HTMLElement | null>(null)
const editInput = ref<HTMLTextAreaElement | null>(null)
const editWidth = ref(0)
function resizeEdit() {
  if (!editInput.value) return
  editInput.value.style.height = 'auto'
  editInput.value.style.height = `${editInput.value.scrollHeight}px`
}
const copied = ref(false)
const copyError = ref('')
let copyTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(copyTimer))
async function startEdit() {
  editWidth.value = userBubble.value?.getBoundingClientRect().width || 0
  editContent.value = props.message.content
  editing.value = true
  await nextTick()
  resizeEdit()
  editInput.value?.focus({ preventScroll: true })
  editInput.value?.setSelectionRange(editContent.value.length, editContent.value.length)
}
function saveEdit() { if (editContent.value.trim()) { emit('edit', editContent.value.trim()); editing.value = false } }
async function copyMessage() {
  copyError.value = ''
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(props.message.content)
    else {
      const el = document.createElement('textarea'); el.value = props.message.content
      el.style.cssText = 'position:fixed;left:-9999px;top:0'; document.body.append(el); el.select()
      try { if (!document.execCommand('copy')) throw new Error('copy') } finally { el.remove() }
    }
    copied.value = true; clearTimeout(copyTimer); copyTimer = setTimeout(() => copied.value = false, 1600)
  } catch { copyError.value = '复制失败，请长按文字复制' }
}
const animateAnswer = props.message.status === 'STREAMING'
const displayedContent = useStreamingText(() => props.message.content, () => props.message.status === 'STREAMING')
watch(displayedContent, () => emit('rendered'), { flush: 'post' })
const showAllResults = ref(false)
const resultsDialog = ref<HTMLDialogElement | null>(null)
watch(showAllResults, async (open) => {
  await nextTick()
  if (open && resultsDialog.value && !resultsDialog.value.open) resultsDialog.value.showModal?.()
})
const sourcesExpanded = ref(false)
const visibleCitations = computed(() => props.message.citations.slice(0, 3))
const answerHtml = computed(() => renderMarkdown(displayedContent.value, props.message.citations.map(item => Number(item.label)),
  Object.fromEntries(props.message.citations.map(item => [item.label, `${item.title || item.fileName}，${pageLabel(item)}`])),
  Object.fromEntries((props.message.stockArtifacts??[]).map(item=>[item.datasetRef,item.title]))))
const sourcePreview = ref<{ citation: Citation; left: number; top: number; above: boolean } | null>(null)
function pageLabel(citation: Citation) {
  if (!citation.pageStart) return '页码未提供'
  return citation.pageEnd && citation.pageEnd !== citation.pageStart
    ? `第 ${citation.pageStart}–${citation.pageEnd} 页` : `第 ${citation.pageStart} 页`
}
function previewSource(event: Event) {
  if ((event as PointerEvent).pointerType === 'touch') return
  const button = (event.target as HTMLElement).closest<HTMLElement>('[data-citation-rank]')
  const citation = props.message.citations.find(item => item.label === Number(button?.dataset.citationRank))
  if (!button || !citation) { sourcePreview.value = null; return }
  const bounds = button.getBoundingClientRect()
  const above = bounds.top > 110
  sourcePreview.value = { citation, left: Math.max(12, Math.min(bounds.left - 12, window.innerWidth - 292)),
    top: above ? bounds.top - 8 : bounds.bottom + 8, above }
}
function hideSourcePreview() { sourcePreview.value = null }
onMounted(() => { window.addEventListener('scroll', hideSourcePreview, true); window.addEventListener('resize', hideSourcePreview) })
onBeforeUnmount(() => { window.removeEventListener('scroll', hideSourcePreview, true); window.removeEventListener('resize', hideSourcePreview) })

function openInlineCitation(event: MouseEvent) {
  const dataset=(event.target as HTMLElement).closest<HTMLElement>('[data-dataset-ref]')
  if(dataset){
    const ref=dataset.dataset.datasetRef??''
    if(props.analysisMode)emit('analysis',ref,0)
    else document.getElementById(ref)?.scrollIntoView({behavior:'smooth',block:'nearest'})
    return
  }
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-citation-rank]')
  if (!target) return
  const citation = props.message.citations.find(item => Number(item.label) === Number(target.dataset.citationRank))
  if (citation) openEvidence(citation)
}

function openEvidence(citation: Citation) {
  hideSourcePreview()
  showAllResults.value = false
  emit('openEvidence', citation)
}
function score(value: number | null) {
  return value == null ? '-' : value.toFixed(3)
}
</script>

<template>
  <article class="message-row" :class="message.role.toLowerCase()" :data-message-id="message.id">
    <div class="message-content">
      <ImageAttachments v-if="message.images?.length" :images="message.images"/>
      <WorkProcess v-if="message.role === 'ASSISTANT' && (message.status === 'STREAMING' || message.processEvents?.length || message.reasoningContent)"
        :message="message" :diagnostics="showDiagnostics" @rendered="emit('rendered')" />
      <form v-if="editing" class="message-edit" :style="{ width: `${editWidth}px` }" @submit.prevent="saveEdit">
        <textarea ref="editInput" v-model="editContent" aria-label="编辑问题" maxlength="8192" rows="1" @input="resizeEdit" @keydown.esc="editing = false" />
        <div><button type="button" @click="editing = false">取消</button><button type="submit" :disabled="busy || !editContent.trim()">发送修改</button></div>
      </form>
      <p v-else-if="message.content && message.role === 'USER'" ref="userBubble">{{ message.content }}</p>
      <MarkdownAnswer v-else-if="displayedContent" :html="answerHtml" :animate="animateAnswer" @click="openInlineCitation"
        @pointerover="previewSource" @pointerleave="hideSourcePreview" @focusin="previewSource" @focusout="hideSourcePreview" @keydown.esc="hideSourcePreview" />
      <p v-if="message.status === 'FAILED'" class="message-failed">{{failureMessage(message.errorCode??message.retrieval?.errorCode)}}</p>
      <template v-if="analysisMode"><button v-for="artifact in message.stockArtifacts??[]" :key="artifact.datasetRef" class="analysis-chat-result" @click="emit('analysis',artifact.datasetRef,0)"><FileText :size="14"/>{{artifact.title}}<span>{{artifact.rowCount}} 行</span></button></template>
      <template v-else><StockArtifactView v-for="artifact in message.stockArtifacts??[]" :key="artifact.datasetRef" :artifact="artifact" :message-id="message.id" @metadata="artifact.charts=$event" @reference="emit('reference',$event)" @rendered="emit('rendered')" @analysis="(ref,index)=>emit('analysis',ref,index)"/></template>
      <button v-if="message.citations.length && message.content" class="sources-toggle" :aria-expanded="sourcesExpanded" @click="sourcesExpanded = !sourcesExpanded">来源 {{ message.citations.length }} {{ sourcesExpanded ? '收起' : '展开' }}</button>
      <div v-if="sourcesExpanded && message.citations.length" class="citation-list" aria-label="证据来源">
        <button v-for="source in visibleCitations" :key="source.citationId" class="citation-link"
                @click="openEvidence(source)">
          <FileText :size="14" aria-hidden="true" />
          <span>来源 {{ source.label }} · {{ source.title }}</span>
          <small v-if="source.pageStart">第 {{ source.pageStart }} 页</small>
        </button>
        <button v-if="message.citations.length > 3" class="show-all-results" @click="showAllResults = true">
          查看全部 {{ message.citations.length }} 条结果
        </button>
      </div>
      <div class="message-actions" v-if="!editing && (message.role === 'USER' || message.content || message.status === 'FAILED')">
        <button type="button" :aria-label="copied ? '已复制' : '复制'" :title="copied ? '已复制' : '复制'" :disabled="!message.content" @click="copyMessage"><Check v-if="copied" :size="15" /><Copy v-else :size="15" /></button>
        <button v-if="message.role === 'USER'" type="button" aria-label="编辑问题" title="编辑问题" :disabled="busy" @click="startEdit"><Pencil :size="15" /></button>
        <template v-else>
          <button type="button" aria-label="点赞" title="点赞" :aria-pressed="message.vote === 1" :disabled="message.status === 'STREAMING'" @click="emit('vote', 1)"><ThumbsUp :size="15" /></button>
          <button type="button" aria-label="点踩" title="点踩" :aria-pressed="message.vote === -1" :disabled="message.status === 'STREAMING'" @click="emit('vote', -1)"><ThumbsDown :size="15" /></button>
          <button type="button" aria-label="重新回答" title="重新回答" :disabled="busy || message.status === 'STREAMING'" @click="emit('regenerate')"><RotateCcw :size="15" /></button>
        </template>
        <span v-if="copyError" role="status">{{ copyError }}</span>
      </div>
      <details v-if="showDiagnostics && message.retrieval?.queryId && message.content" class="retrieval-meta">
        <summary>检索信息</summary>
        <dl>
          <div><dt>模式</dt><dd>{{ message.retrieval.mode || 'hybrid' }}</dd></div>
          <div><dt>耗时</dt><dd>{{ message.retrieval.durationMs }} ms</dd></div>
          <div><dt>嵌入模型</dt><dd>{{ message.retrieval.embeddingModel || '未返回' }}</dd></div>
          <div><dt>重排模型</dt><dd>{{ message.retrieval.rerankModel || '未启用' }}</dd></div>
        </dl>
      </details>
    </div>

      <dialog v-if="showAllResults" ref="resultsDialog" class="retrieval-results-modal" :class="{ 'reader-sources-only': !showDiagnostics }" aria-label="全部检索结果" @cancel.prevent="showAllResults = false">
        <header>
          <div><strong>全部检索结果</strong><span>{{ message.citations.length }} 条</span></div>
          <button class="icon-button" title="关闭" @click="showAllResults = false"><X :size="18" /></button>
        </header>
        <div class="retrieval-results-list">
        <div v-if="showDiagnostics" class="retrieval-results-head" aria-hidden="true">
          <span>名次</span><span>来源与内容</span><span>模式</span><span>召回分数</span><span>重排分数</span>
        </div>
          <button v-for="source in message.citations" :key="source.citationId" class="retrieval-result-row"
                  @click="openEvidence(source)">
            <strong>#{{ source.label }}</strong>
            <span class="result-source"><b>{{ source.title || source.fileName }}</b><small>{{ pageLabel(source) }}</small><span class="result-passage">{{ source.passage || '未提供文字摘要，点击查看原文。' }}</span></span>
            <span v-if="showDiagnostics">{{ source.retrievalMode }}</span>
            <span v-if="showDiagnostics">{{ score(source.retrievalScore) }}</span>
            <span v-if="showDiagnostics">{{ score(source.rerankScore) }}</span>
          </button>
        </div>
      </dialog>
  </article>
  <Teleport to="body">
    <div v-if="sourcePreview" class="source-preview" role="tooltip"
      :style="{ left: `${sourcePreview.left}px`, top: `${sourcePreview.top}px`, transform: sourcePreview.above ? 'translateY(-100%)' : undefined }">
      <FileText :size="17" aria-hidden="true" /><div><strong>{{ sourcePreview.citation.title || sourcePreview.citation.fileName }}</strong><span>{{ pageLabel(sourcePreview.citation) }}</span></div>
    </div>
  </Teleport>
</template>
