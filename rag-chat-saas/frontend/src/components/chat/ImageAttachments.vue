<script setup lang="ts">
import { ref } from 'vue'
import ImageViewer from '../ImageViewer.vue'
import { X } from 'lucide-vue-next'
import type { ChatImage } from '../../types'
defineProps<{images:ChatImage[];removable?:boolean;disabled?:boolean}>()
const emit=defineEmits<{remove:[id:string]}>()
const current=ref<number|null>(null)
</script>
<template><div class="chat-image-strip"><figure v-for="(image,index) in images" :key="image.id"><button type="button" class="chat-image-preview" :aria-label="`查看图片：${image.name}`" @click="current=index"><img :src="image.url" :alt="image.name"/></button><button v-if="removable" type="button" class="chat-image-remove" :disabled="disabled" :aria-label="`移除 ${image.name}`" @click="emit('remove',image.id)"><X :size="13"/></button></figure><ImageViewer v-if="current!==null&&images.length" :images="images" :index="current" @close="current=null"/></div></template>
<style scoped>
.chat-image-strip{display:flex;gap:8px;overflow-x:auto;max-width:100%;padding:5px 2px;scrollbar-width:thin}.chat-image-strip figure{position:relative;flex:none;margin:0}.chat-image-preview{width:72px;height:72px;display:block;padding:0;border:1px solid var(--separator);border-radius:10px;overflow:hidden;cursor:zoom-in;background:var(--surface-secondary)}.chat-image-preview img{display:block;width:100%;height:100%;object-fit:cover}.chat-image-remove{position:absolute;right:3px;top:3px;display:grid;place-items:center;width:22px;height:22px;min-height:22px;padding:0;border:0;border-radius:50%;color:#fff;background:#333b;cursor:pointer}
</style>
