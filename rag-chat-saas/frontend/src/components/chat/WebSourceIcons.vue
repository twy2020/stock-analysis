<script setup lang="ts">
import { ref } from 'vue'
import { Globe } from 'lucide-vue-next'
import type { WebSource } from '../../types'
defineProps<{ sources: WebSource[] }>()
const failed = ref(new Set<string>())
function safeUrl(value: string) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url : null } catch { return null }
}
</script>

<template>
  <span class="web-source-icons">
    <template v-for="source in sources" :key="source.id">
      <a v-if="safeUrl(source.url)" :href="source.url" target="_blank" rel="noopener noreferrer" :title="`${source.title} · ${source.domain}${source.read ? ' · 已读取原文' : ' · 搜索摘要'}`" :aria-label="source.title">
        <img v-if="!failed.has(source.id)" :src="`${safeUrl(source.url)!.origin}/favicon.ico`" alt="" width="16" height="16" loading="lazy" referrerpolicy="no-referrer" @error="failed.add(source.id)" />
        <Globe v-else :size="14" aria-hidden="true" />
      </a>
    </template>
  </span>
</template>

<style scoped>
.web-source-icons { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; flex: 0 1 auto; }
a { width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border-radius: 4px; color: inherit; background: color-mix(in srgb, currentColor 6%, transparent); }
a:hover { background: color-mix(in srgb, currentColor 14%, transparent); }
img { object-fit: contain; }
</style>
