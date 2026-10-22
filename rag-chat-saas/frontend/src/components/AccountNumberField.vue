<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
const props = defineProps<{ value: number; label: string; save: (value: number) => Promise<void> }>()
const draft = ref(String(props.value))
const state = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let saving = false
watch(() => props.value, value => { if (!saving && !timer) draft.value = String(value) })
function input() {
  clearTimeout(timer)
  state.value = '待保存'
  timer = setTimeout(() => { timer = undefined; void commit() }, 500)
}
async function commit() {
  clearTimeout(timer); timer = undefined
  if (saving) return
  const value = Number(draft.value)
  if (!String(draft.value).trim() || !Number.isInteger(value) || value < 1 || value > 100) { state.value = '请输入 1–100 的整数'; return }
  if (value === props.value) { state.value = ''; return }
  saving = true; state.value = '保存中'
  try { await props.save(value); state.value = '已保存' }
  catch { state.value = '保存失败，请重试' }
  finally { saving = false }
  if (Number(draft.value) !== value) void commit()
}
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <span class="account-number-field"><input v-model="draft" class="table-number" type="number" min="1" max="100" step="1" :aria-label="label" @input="input" @change="commit" @keydown.enter.prevent="commit"/><small role="status">{{ state }}</small></span>
</template>
