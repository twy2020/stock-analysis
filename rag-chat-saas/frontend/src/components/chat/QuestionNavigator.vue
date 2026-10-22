<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Message } from '../../types'

const props = defineProps<{ messages: Message[]; container: HTMLElement | null }>()
const emit = defineEmits<{ navigate: [] }>()
const questions = computed(() => props.messages.filter(message => message.role === 'USER'))
const activeId = ref('')
const expanded = ref(false)
const list = ref<HTMLElement | null>(null)
let frame = 0
let resize: ResizeObserver | undefined
function update() {
  frame = 0
  const container = props.container
  if (!container) return
  const rows = Array.from(container.querySelectorAll<HTMLElement>('.message-row.user'))
  const edge = container.getBoundingClientRect().top + 40
  let current: HTMLElement | undefined = rows[0]
  for (const row of rows) {
    if (row.getBoundingClientRect().top > edge) break
    current = row
  }
  if (container.scrollHeight - container.scrollTop - container.clientHeight < 2) current = rows.at(-1)
  activeId.value = current?.dataset.messageId ?? ''
}
function schedule() { if (!frame) frame = requestAnimationFrame(update) }
watch(() => props.container, (container, previous) => {
  previous?.removeEventListener('scroll', schedule)
  resize?.disconnect()
  container?.addEventListener('scroll', schedule, { passive: true })
  if (container && typeof ResizeObserver !== 'undefined') {
    resize = new ResizeObserver(schedule)
    resize.observe(container)
  }
  schedule()
}, { flush: 'post' })
watch(() => questions.value.map(q => q.id).join(','), async () => {
  expanded.value = false
  await nextTick()
  schedule()
}, { immediate: true })
watch(activeId, async () => {
  await nextTick()
  const active = list.value?.querySelector<HTMLElement>('[aria-current="true"]')
  if (active && list.value && !expanded.value) {
    list.value.scrollTop = active.offsetTop - list.value.clientHeight / 2 + active.offsetHeight / 2
  }
})
function jump(id: string) {
  const container = props.container
  const target = Array.from(container?.querySelectorAll<HTMLElement>('.message-row.user') ?? []).find(row => row.dataset.messageId === id)
  if (!container || !target) return
  emit('navigate')
  const top = container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - 24
  container.scrollTo({ top: Math.max(0, top), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  activeId.value = id
}
function leaveFocus(event: FocusEvent) {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) expanded.value = false
}
onBeforeUnmount(() => {
  props.container?.removeEventListener('scroll', schedule)
  resize?.disconnect()
  cancelAnimationFrame(frame)
})
</script>

<template>
  <nav v-if="questions.length > 1" class="question-navigator" :class="{ expanded }" aria-label="问题导航"
    @pointerenter="expanded = true" @pointerleave="expanded = false" @focusin="expanded = true" @focusout="leaveFocus"
    @keydown.esc.stop="expanded = false; ($event.target as HTMLElement).blur()">
    <div ref="list" class="question-navigator-list">
      <button v-for="question in questions" :key="question.id" type="button" :aria-label="`跳转到问题：${question.content}`"
        :aria-current="activeId === question.id ? 'true' : undefined" :title="question.content" @click="jump(question.id)">
        <span class="question-navigator-title">{{ question.content }}</span><i aria-hidden="true" />
      </button>
    </div>
  </nav>
</template>
