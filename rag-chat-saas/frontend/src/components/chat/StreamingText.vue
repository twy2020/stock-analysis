<script setup lang="ts">
import { watch } from 'vue'
import { useStreamingText } from './useStreamingText'

const props = defineProps<{ text: string; streaming: boolean }>()
const emit = defineEmits<{ rendered: [] }>()
const animate = props.streaming
const displayed = useStreamingText(() => props.text, () => props.streaming)
watch(displayed, () => emit('rendered'), { flush: 'post' })
</script>

<template>
  <span v-if="animate"><span v-for="(char, index) in Array.from(displayed)" :key="index" class="stream-reveal">{{ char }}</span></span>
  <span v-else>{{ displayed }}</span>
</template>
