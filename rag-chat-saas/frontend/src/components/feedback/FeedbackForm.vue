<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import ImageViewer from '../ImageViewer.vue'
import { ImagePlus, X } from 'lucide-vue-next'
import { api } from '../../api/client'
import { useChatStore } from '../../stores/chat'
const props=defineProps<{draft:string}>()
const emit=defineEmits<{submitted:[id:string];busy:[value:boolean]}>()
const chat=useChatStore(), revision=chat.sessionRevision
const comment=ref(''),pending=ref(false),error=ref('')
const images=ref<Array<{file:File;url:string}>>([])
const imageIndex=ref<number|null>(null)
const previewImages=computed(()=>images.value.map(item=>({url:item.url,name:item.file.name})))
const controller=new AbortController()
const conversationId=chat.activeConversation?.id||'',title=chat.activeConversation?.title||'新对话'
const messages:Array<Record<string,string>>=[]
let budget=700000
for(const item of [...chat.messages.slice(-200)].reverse()){
 const content=item.content.slice(0,100000),size=new TextEncoder().encode(content).length
 if(size>budget)break
 budget-=size;messages.unshift({role:item.role,content,status:item.status,model:item.model||''})
}
const snapshot={messages,draft:props.draft,error:chat.error,knowledgeBase:chat.knowledgeBases.find(item=>item.id===chat.selectedKnowledgeBaseId)?.name||'',capturedAt:new Date().toISOString(),truncated:messages.length<chat.messages.length||chat.messages.some(item=>item.content.length>100000)}
function clear(){images.value.forEach(item=>URL.revokeObjectURL(item.url));images.value=[]}
function accept(files:File[]){
 if(pending.value)return
 error.value=''
 for(const file of files){
  if(images.value.length>=3){error.value='最多上传 3 张图片';break}
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024){error.value='请选择不超过 5 MB 的 PNG、JPEG 或 WebP 图片';continue}
  images.value.push({file,url:URL.createObjectURL(file)})
 }
}
function paste(event:ClipboardEvent){const files=Array.from(event.clipboardData?.items||[]).filter(i=>i.kind==='file'&&i.type.startsWith('image/')).map(i=>i.getAsFile()).filter((f):f is File=>!!f);if(files.length){if(!event.clipboardData?.getData('text/plain'))event.preventDefault();accept(files)}}
function upload(event:Event){const input=event.target as HTMLInputElement;accept(Array.from(input.files||[]));input.value=''}
function remove(index:number){URL.revokeObjectURL(images.value[index].url);images.value.splice(index,1)}
async function submit(){
 if(pending.value||!comment.value.trim())return
 pending.value=true;emit('busy',true);error.value=''
 const body=new FormData();body.set('comment',comment.value.trim());body.set('conversationId',conversationId);body.set('snapshot',JSON.stringify(snapshot));images.value.forEach(i=>body.append('images',i.file))
 try{const result=await api<{id:string}>('/api/v1/feedback',{method:'POST',body,signal:controller.signal});if(revision!==chat.sessionRevision||controller.signal.aborted)return;comment.value='';clear();emit('submitted',result.id)}
 catch(e){if(!controller.signal.aborted)error.value=e instanceof Error?e.message:'提交失败，请重试'}
 finally{pending.value=false;emit('busy',false)}
}
onUnmounted(()=>{controller.abort();clear()})
</script>
<template>
 <form class="feedback-form center-feedback-form" @submit.prevent="submit" @paste="paste">
  <div class="center-section-heading"><h3>提交反馈</h3><p>提交后生成工单，可在历史反馈中查看回复并继续沟通。</p></div>
  <div class="feedback-context">将附上当前对话「{{title}}」的文字快照与输入框内容，供管理员排查。<span v-if="snapshot.truncated">仅附最近可记录的消息。</span></div>
  <label for="feedback-comment">反馈内容</label><textarea id="feedback-comment" v-model="comment" rows="6" maxlength="5000" required placeholder="请描述遇到的问题或改进建议" :disabled="pending"/>
  <div class="feedback-upload"><label class="secondary-button"><ImagePlus :size="16"/>添加图片<input type="file" accept="image/png,image/jpeg,image/webp" multiple :disabled="pending||images.length>=3" @change="upload"/></label><small>支持粘贴图片 · 最多 3 张，每张 5 MB</small></div>
  <div v-if="images.length" class="feedback-images"><figure v-for="(item,index) in images" :key="item.url"><button type="button" class="feedback-image-preview" :aria-label="`查看图片：${item.file.name}`" @click="imageIndex=index"><img :src="item.url" :alt="item.file.name"/></button><button type="button" class="icon-button" :aria-label="`移除 ${item.file.name}`" :disabled="pending" @click="remove(index)"><X :size="14"/></button></figure></div>
  <p v-if="error" class="form-error" role="alert">{{error}}</p>
  <footer><span class="field-count">{{comment.length}} / 5000</span><button class="primary-button" :disabled="pending||!comment.trim()">{{pending?'正在提交…':'提交工单'}}</button></footer>
 <ImageViewer v-if="imageIndex!==null" :images="previewImages" :index="imageIndex" @close="imageIndex=null"/>
 </form>
</template>
