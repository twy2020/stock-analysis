<script setup lang="ts">
import { ref,onMounted,onBeforeUnmount } from 'vue'
import { ImagePlus,LoaderCircle } from 'lucide-vue-next'
import { api } from '../../api/client'
import type { ChatImage } from '../../types'
import ImageAttachments from './ImageAttachments.vue'
const props=defineProps<{modelValue:ChatImage[];disabled?:boolean;previewTarget?:HTMLElement|null}>()
const emit=defineEmits<{'update:modelValue':[images:ChatImage[]];busy:[value:boolean]}>()
const enabled=ref(false),busy=ref(false),error=ref('')
const fileInput=ref<HTMLInputElement|null>(null)
let disposed=false
onMounted(async()=>{try{const value=await api<{enabled:boolean}>('/api/v1/images/capabilities');if(!disposed)enabled.value=value.enabled}catch{/* Remain hidden when unavailable. */}})
onBeforeUnmount(()=>{disposed=true})
async function accept(files:File[]){
 if(!enabled.value||props.disabled||busy.value)return
 busy.value=true;emit('busy',true);error.value=''
 try{for(const file of files){
  if(props.modelValue.length>=4){error.value='最多添加 4 张图片';break}
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024){error.value='请选择不超过 5 MB 的 PNG、JPEG 或 WebP 图片';continue}
  const body=new FormData();body.append('image',file)
  const result=await api<ChatImage>('/api/v1/images',{method:'POST',body})
  if(disposed)return
  emit('update:modelValue',[...props.modelValue,result])
  await Promise.resolve()
 }}catch(e){if(!disposed)error.value=e instanceof Error?e.message:'图片上传失败'}finally{if(!disposed){busy.value=false;emit('busy',false)}}
}
function paste(event:ClipboardEvent){const files=Array.from(event.clipboardData?.files||[]).filter(f=>f.type.startsWith('image/'));if(files.length&&enabled.value){event.preventDefault();void accept(files)}}
function upload(event:Event){const input=event.target as HTMLInputElement;void accept(Array.from(input.files||[]));input.value=''}
async function remove(id:string){if(props.disabled||busy.value)return;try{await api(`/api/v1/images/${id}`,{method:'DELETE'});if(!disposed)emit('update:modelValue',props.modelValue.filter(i=>i.id!==id))}catch(e){error.value=e instanceof Error?e.message:'移除失败'}}
defineExpose({paste})
</script>
<template>
  <template v-if="enabled">
    <button class="thinking-control image-attach" type="button" :class="{selected:modelValue.length>0}"
      :aria-label="busy?'正在上传图片':'添加图片'" :aria-busy="busy" :title="modelValue.length>=4?'最多添加 4 张图片':'添加图片'"
      :disabled="disabled||busy||modelValue.length>=4" @click="fileInput?.click()">
      <LoaderCircle v-if="busy" class="upload-spinner" :size="16" aria-hidden="true"/><ImagePlus v-else :size="16" aria-hidden="true"/>
      <span class="thinking-label">{{busy?'正在上传':'添加图片'}}</span>
    </button>
    <input ref="fileInput" class="image-file-input" type="file" accept="image/png,image/jpeg,image/webp" multiple
      :disabled="disabled||busy||modelValue.length>=4" @change="upload"/>
    <Teleport :to="previewTarget||'body'" :disabled="!previewTarget">
      <div v-if="modelValue.length||error" class="image-composer-previews">
        <ImageAttachments v-if="modelValue.length" :images="modelValue" removable :disabled="disabled||busy" @remove="remove"/>
        <p v-if="error" role="alert">{{error}}</p>
      </div>
    </Teleport>
  </template>
</template>
<style scoped>
.image-file-input{display:none}
.image-attach{color:var(--ink-secondary);cursor:pointer}
.image-attach:disabled{opacity:.5;cursor:default}
.image-composer-previews{display:grid;gap:6px;min-width:0;padding:4px 8px 8px;font-size:12px}
.image-composer-previews p{margin:0;color:var(--danger)}
.upload-spinner{animation:upload-spin 1s linear infinite}
@keyframes upload-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.upload-spinner{animation:none}}
</style>
