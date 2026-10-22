<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Check, ChevronUp, LibraryBig } from 'lucide-vue-next'
import type { KnowledgeBase } from '../../types'

const props = defineProps<{ modelValue: string; options: KnowledgeBase[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const open = ref(false)
const activeIndex = ref(0)
const selected = computed(() => props.options.find(item => item.id === props.modelValue))
const selectedLabel = computed(() => selected.value ? `${selected.value.name} · v${selected.value.versionNumber}` : props.options.length ? '选择知识库' : '暂无知识库')

function close() { open.value = false }
function show() {
  if (props.disabled || !props.options.length) return
  activeIndex.value = Math.max(0, props.options.findIndex(item => item.id === props.modelValue))
  open.value = true
}
function toggle() { open.value ? close() : show() }
async function choose(item: KnowledgeBase) {
  emit('update:modelValue', item.id)
  close()
  await nextTick()
  trigger.value?.focus()
}
function onKeydown(event: KeyboardEvent) {
  if (props.disabled || !props.options.length) return
  if (event.key === 'Escape') {
    if (open.value) { event.preventDefault(); close(); trigger.value?.focus() }
  } else if (event.key === 'Tab') {
    close()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) show()
    else activeIndex.value = (activeIndex.value + (event.key === 'ArrowDown' ? 1 : -1) + props.options.length) % props.options.length
  } else if (event.key === 'Home' && open.value) {
    event.preventDefault(); activeIndex.value = 0
  } else if (event.key === 'End' && open.value) {
    event.preventDefault(); activeIndex.value = props.options.length - 1
  } else if ((event.key === 'Enter' || event.key === ' ') && open.value) {
    event.preventDefault(); void choose(props.options[activeIndex.value]!)
  }
}
function onOutsidePointer(event: PointerEvent) {
  if (event.target instanceof Node && !root.value?.contains(event.target)) close()
}
onMounted(() => document.addEventListener('pointerdown', onOutsidePointer))
onUnmounted(() => document.removeEventListener('pointerdown', onOutsidePointer))
</script>

<template>
  <div ref="root" class="knowledge-base-picker" :class="{ 'is-open': open }" @keydown="onKeydown">
    <button ref="trigger" type="button" class="kb-trigger" role="combobox" aria-label="知识库"
            aria-haspopup="listbox" aria-controls="knowledge-base-options" :aria-expanded="open"
            :aria-activedescendant="open ? `knowledge-base-option-${activeIndex}` : undefined"
            :disabled="disabled || !options.length" :title="selectedLabel" @click="toggle">
      <LibraryBig class="kb-symbol" :size="16" aria-hidden="true" /><span class="kb-label">{{ selectedLabel }}</span><ChevronUp class="kb-chevron" :size="14" aria-hidden="true" />
    </button>
    <Transition name="composer-popover"><div v-if="open" id="knowledge-base-options" class="kb-options" role="listbox" aria-label="知识库">
      <button v-for="(item, index) in options" :id="`knowledge-base-option-${index}`" :key="item.id"
              type="button" role="option" class="kb-option" :class="{ active: index === activeIndex }"
              :aria-selected="item.id === modelValue" :title="`${item.name} · v${item.versionNumber}`"
              tabindex="-1" @mouseenter="activeIndex = index" @click="choose(item)">
        <span>{{ item.name }}</span><small>v{{ item.versionNumber }}</small>
        <Check v-if="item.id === modelValue" :size="15" aria-hidden="true" />
      </button>
    </div></Transition>
  </div>
</template>
