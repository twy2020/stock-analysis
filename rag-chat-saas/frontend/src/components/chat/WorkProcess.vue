<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Check, ChevronRight, CircleAlert, Clock3, FileSearch, Sparkles, Wrench } from 'lucide-vue-next'
import type { Message } from '../../types'
import { duration, workRows } from './workProcess'
import { useSmoothScroll } from './useSmoothScroll'
import WebSourceIcons from './WebSourceIcons.vue'

const props = defineProps<{ message: Message; diagnostics?: boolean }>()
const emit = defineEmits<{ rendered: [] }>()
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined
watch(() => props.message.status, status => {
  clearInterval(timer)
  if (status === 'STREAMING') timer = setInterval(() => now.value = Date.now(), 1000)
}, { immediate: true })
onBeforeUnmount(() => clearInterval(timer))
const streaming = computed(() => props.message.status === 'STREAMING')
const events = computed(() => props.message.processEvents ?? [])
const latest = computed(() => events.value.at(-1))
const writing = computed(() => latest.value?.stage === 'RESPONSE_STREAMING' || (!events.value.length && !!props.message.content))
const archived = computed(() => !streaming.value || writing.value)
const expanded = ref(false)
watch(() => props.message.id, () => expanded.value = false)
const rows = computed(() => workRows(events.value, streaming.value, now.value, !!props.diagnostics))
const history = computed(() => rows.value.filter(row => !(archived.value && row.running)))
const olderCount = computed(() => archived.value ? 0 : Math.max(0, history.value.length - 1))
const visibleHistory = computed(() => expanded.value || archived.value ? history.value : history.value.slice(-1))
const current = computed(() => rows.value.filter(row => row.running).at(-1))
const total = computed(() => latest.value?.elapsedMsTotal)
const reasoningOpen = ref(false)
const thinking = computed(() => streaming.value && latest.value?.stage === 'MODEL_REASONING')
watch(thinking, () => { reasoningOpen.value = false; followReasoning.value = true })
function elapsed(ms: number, running = false) { return running ? `${Math.floor(ms / 1000)} 秒` : duration(ms) }
const reasoningScroll = ref<HTMLElement | null>(null)
const followReasoning = ref(true)
const scroll = ref<HTMLElement | null>(null)
const follow = ref(true)
const historyMotion = useSmoothScroll(scroll)
const reasoningMotion = useSmoothScroll(reasoningScroll)
let lastHistoryTop = 0
let lastReasoningTop = 0
function trackScroll() {
  const el = scroll.value
  if (!el) return
  if (!historyMotion.isMoving()) {
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight
    follow.value = follow.value ? remaining < 32 : remaining < 4 && el.scrollTop > lastHistoryTop
  }
  lastHistoryTop = el.scrollTop
}
function trackReasoningScroll() {
  const el = reasoningScroll.value
  if (!el) return
  if (!reasoningMotion.isMoving()) {
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight
    followReasoning.value = followReasoning.value ? remaining < 32 : remaining < 4 && el.scrollTop > lastReasoningTop
  }
  lastReasoningTop = el.scrollTop
}
function pauseHistory() { historyMotion.stop(); follow.value = false; lastHistoryTop = scroll.value?.scrollTop ?? 0 }
function pauseReasoning() { reasoningMotion.stop(); followReasoning.value = false; lastReasoningTop = reasoningScroll.value?.scrollTop ?? 0 }
async function onTextRendered() {
  await nextTick()
  if (follow.value) historyMotion.bottom()
  if (followReasoning.value) reasoningMotion.bottom()
  emit('rendered')
}
watch(() => [props.message.reasoningContent, events.value.length, expanded.value, reasoningOpen.value], async () => {
  await onTextRendered()
})
function icon(stage: string) {
  if (stage === 'TIME_READING') return Clock3
  if (['SEARCHING', 'DOCUMENTS_LISTING'].includes(stage)) return FileSearch
  if (stage.startsWith('TOOL_')) return Wrench
  return Sparkles
}
</script>

<template>
  <section class="work-process" aria-label="工作过程">
    <button v-if="archived && (history.length || message.reasoningContent)" class="work-summary" :aria-expanded="expanded" @click="expanded = !expanded">
      <Sparkles :size="14" aria-hidden="true" /><span>分析过程</span><time v-if="total != null">{{ duration(total) }}</time>
      <ChevronRight :size="14" :class="{ expanded }" aria-hidden="true" />
    </button>
    <div v-if="!archived || expanded" class="work-history" :class="{ 'live-work': !archived }">
      <button v-if="olderCount" class="reasoning-disclosure" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起较早事件' : `查看较早 ${olderCount} 条事件` }}</button>
      <div ref="scroll" class="work-scroll" :class="{ 'expanded-history': expanded }" @scroll="trackScroll" @wheel.passive="pauseHistory" @touchstart.passive="pauseHistory">
        <div v-for="row in visibleHistory" :key="row.key" class="work-row" :role="row.running ? 'status' : undefined" :class="{ 'work-note': row.note, 'is-running': row.running, 'is-failed': row.failed }">
          <template v-if="!row.note">
            <component :is="row.failed ? CircleAlert : row.running ? icon(row.stage) : Check" :size="14" aria-hidden="true" />
            <span class="work-label">{{ row.label }}</span>
            <WebSourceIcons v-if="row.sources?.length" :sources="row.sources" />
            <time v-if="row.elapsedMs != null">{{ elapsed(row.elapsedMs, row.running) }}</time>
          </template>
          <p v-else>{{ row.label }}</p>
        </div>
        <div v-if="message.reasoningContent" class="work-reasoning" :class="{ 'thinking-live': thinking }">
          <div v-if="thinking || archived" class="work-reasoning-heading"><Sparkles :size="13"/><span>分析思路</span></div>
          <button v-if="!thinking && !archived" class="reasoning-disclosure" :aria-expanded="reasoningOpen" @click="reasoningOpen = !reasoningOpen"><ChevronRight :size="13" :class="{ expanded: reasoningOpen }"/><span>查看思考内容</span></button>
          <div v-if="thinking || reasoningOpen || archived" ref="reasoningScroll" class="work-reasoning-text" @scroll="trackReasoningScroll" @wheel.passive.stop="pauseReasoning" @touchstart.passive.stop="pauseReasoning">{{ message.reasoningContent }}</div>
        </div>
      </div>
    </div>
    <div v-if="streaming && (archived || !rows.length)" class="work-row is-running" role="status">
      <Sparkles :size="14" aria-hidden="true" /><span class="work-label">{{ current?.label || (writing ? '正在撰写回复' : '正在准备') }}</span>
      <time v-if="current?.elapsedMs != null">{{ elapsed(current.elapsedMs, true) }}</time>
    </div>
  </section>
</template>
