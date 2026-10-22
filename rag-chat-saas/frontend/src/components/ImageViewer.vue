<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, LoaderCircle, RotateCcw } from 'lucide-vue-next'

const props=defineProps<{images:Array<{url:string;name:string}>;index:number}>()
const emit=defineEmits<{close:[]}>()
const dialog=ref<HTMLDialogElement|null>(null),stage=ref<HTMLElement|null>(null)
const current=ref(props.index),zoom=ref(1),loading=ref(true),failed=ref(false),retry=ref(0)
const size=ref({width:1,height:1}),viewport=ref({width:1,height:1})
const selected=computed(()=>props.images[current.value])
const fit=computed(()=>Math.min(1,Math.max(1,viewport.value.width-32)/size.value.width,Math.max(1,viewport.value.height-32)/size.value.height))
const dimensions=computed(()=>({width:Math.round(size.value.width*fit.value*zoom.value),height:Math.round(size.value.height*fit.value*zoom.value)}))
let observer:ResizeObserver|undefined,opener:HTMLElement|null=null,disposed=false
let drag:{x:number;y:number;left:number;top:number}|null=null
function measure(){if(stage.value)viewport.value={width:stage.value.clientWidth,height:stage.value.clientHeight}}
function reset(){zoom.value=1;if(stage.value){stage.value.scrollTop=0;stage.value.scrollLeft=0}}
function change(delta:number){current.value=Math.max(0,Math.min(props.images.length-1,current.value+delta))}
function loaded(event:Event){const img=event.target as HTMLImageElement;size.value={width:img.naturalWidth||1,height:img.naturalHeight||1};loading.value=false;failed.value=false;measure()}
async function scale(value:number){
 if(loading.value||failed.value)return
 const node=stage.value,old=dimensions.value
 const centerX=node?(node.scrollLeft+node.clientWidth/2-Math.max(0,(node.clientWidth-old.width)/2))/old.width:.5
 const centerY=node?(node.scrollTop+node.clientHeight/2-Math.max(0,(node.clientHeight-old.height)/2))/old.height:.5
 zoom.value=Math.min(4,Math.max(1,value));await nextTick()
 if(node){node.scrollLeft=centerX*dimensions.value.width-node.clientWidth/2;node.scrollTop=centerY*dimensions.value.height-node.clientHeight/2}
}
function wheel(event:WheelEvent){void scale(zoom.value*(event.deltaY<0?1.15:1/1.15))}
function startDrag(event:PointerEvent){if(event.pointerType==='touch'||zoom.value<=1||event.button!==0||!stage.value)return;stage.value.setPointerCapture(event.pointerId);drag={x:event.clientX,y:event.clientY,left:stage.value.scrollLeft,top:stage.value.scrollTop}}
function moveDrag(event:PointerEvent){if(drag&&stage.value){stage.value.scrollLeft=drag.left+drag.x-event.clientX;stage.value.scrollTop=drag.top+drag.y-event.clientY}}
function close(){dialog.value?.close();emit('close')}
function keys(event:KeyboardEvent){if(event.key==='ArrowLeft'){event.preventDefault();change(-1)}else if(event.key==='ArrowRight'){event.preventDefault();change(1)}}
function reload(){failed.value=false;loading.value=true;retry.value++}
watch(()=>selected.value?.url,()=>{reset();size.value={width:1,height:1};loading.value=true;failed.value=false})
watch(()=>props.images.length,n=>{if(!n)close();else current.value=Math.min(current.value,n-1)})
onMounted(async()=>{opener=document.activeElement instanceof HTMLElement?document.activeElement:null;await nextTick();if(disposed)return;dialog.value?.showModal();measure();observer=new ResizeObserver(measure);if(stage.value)observer.observe(stage.value)})
onBeforeUnmount(()=>{disposed=true;observer?.disconnect();dialog.value?.close();if(opener?.isConnected)opener.focus({preventScroll:true})})
</script>
<template>
 <Teleport to="body"><dialog ref="dialog" class="image-viewer" aria-label="图片查看器" @cancel.stop.prevent="close" @keydown.stop="keys">
  <header class="image-viewer-header"><strong :title="selected?.name">{{selected?.name||'图片'}}</strong><span>{{current+1}} / {{images.length}}</span><button type="button" aria-label="关闭图片查看器" title="关闭（Esc）" @click="close"><X :size="20"/></button></header>
  <div ref="stage" class="image-viewer-stage" :class="{zoomed:zoom>1}" @wheel.prevent="wheel" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="drag=null" @pointercancel="drag=null" @lostpointercapture="drag=null">
   <div v-if="selected" class="image-viewer-canvas" :style="{width:`${Math.max(viewport.width,dimensions.width)}px`,height:`${Math.max(viewport.height,dimensions.height)}px`}"><img :key="selected.url+retry" :src="selected.url" :alt="selected.name" :style="{width:dimensions.width+'px',height:dimensions.height+'px',visibility:loading||failed?'hidden':'visible'}" draggable="false" @load="loaded" @error="failed=true;loading=false"/></div>
  </div>
  <div v-if="loading" class="image-viewer-state" role="status"><LoaderCircle class="image-viewer-spinner" :size="26"/><span>正在加载图片…</span></div>
  <div v-else-if="failed" class="image-viewer-state" role="alert"><span>图片未能加载，请重试。</span><button type="button" aria-label="重新加载图片" @click="reload"><RotateCcw :size="18"/>重新加载</button></div>
  <footer class="image-viewer-tools"><button type="button" aria-label="上一张图片" :disabled="current===0" @click="change(-1)"><ChevronLeft :size="20"/></button><button type="button" aria-label="缩小图片" :disabled="loading||failed||zoom<=1" @click="scale(zoom/1.25)"><ZoomOut :size="19"/></button><span aria-label="缩放比例">{{Math.round(zoom*100)}}%</span><button type="button" aria-label="放大图片" :disabled="loading||failed||zoom>=4" @click="scale(zoom*1.25)"><ZoomIn :size="19"/></button><button type="button" aria-label="适应窗口" title="适应窗口" @click="reset"><Maximize :size="18"/></button><button type="button" aria-label="下一张图片" :disabled="current>=images.length-1" @click="change(1)"><ChevronRight :size="20"/></button></footer>
 </dialog></Teleport>
</template>
<style scoped>
.image-viewer{position:fixed;inset:0;width:calc(100vw - 40px);height:calc(100dvh - 40px);max-width:1600px;max-height:none;margin:auto;padding:0;border:1px solid rgb(255 255 255 / 18%);border-radius:18px;background:#17191e;color:#f5f5f7;box-shadow:0 24px 100px rgb(0 0 0 / 40%);overflow:hidden;font-size:14px}
.image-viewer[open]{display:grid;grid-template-rows:56px minmax(0,1fr) 62px}.image-viewer::backdrop{background:rgb(15 18 26 / 65%);backdrop-filter:blur(8px)}
.image-viewer-header{display:flex;align-items:center;gap:16px;padding:8px 16px;background:rgb(255 255 255 / 4%)}.image-viewer-header strong{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}.image-viewer-header span{font-size:12px;color:#b7bac4;white-space:nowrap}
.image-viewer button{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-width:36px;min-height:36px;padding:8px;border:0;border-radius:50%;background:transparent;color:inherit;cursor:pointer}.image-viewer button:hover{background:rgb(255 255 255 / 12%)}.image-viewer button:disabled{opacity:.3;cursor:default}.image-viewer button:focus-visible{outline:2px solid #90b9ff;outline-offset:2px}
.image-viewer-stage{min-height:0;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#686b74 transparent}.image-viewer-stage.zoomed{cursor:grab}.image-viewer-stage.zoomed:active{cursor:grabbing}.image-viewer-canvas{display:grid;place-items:center;min-width:100%;min-height:100%}.image-viewer-canvas img{display:block;max-width:none;max-height:none;object-fit:contain;user-select:none}
.image-viewer-tools{display:flex;align-items:center;justify-content:center;gap:10px;background:rgb(255 255 255 / 4%);padding-bottom:env(safe-area-inset-bottom)}.image-viewer-tools span{width:48px;text-align:center;font-size:12px;font-variant-numeric:tabular-nums}.image-viewer-state{position:absolute;inset:56px 0 62px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;pointer-events:none;color:#d5d7df}.image-viewer-state button{pointer-events:auto;border-radius:9px;background:rgb(255 255 255 / 9%);font:inherit}.image-viewer-spinner{animation:viewer-spin 1s linear infinite}@keyframes viewer-spin{to{transform:rotate(360deg)}}
@media(max-width:640px){.image-viewer{width:100vw;height:100dvh;border:0;border-radius:0}.image-viewer-header{padding-inline:12px}.image-viewer-tools{gap:6px}.image-viewer-tools button{min-width:40px;min-height:40px}}
@media(prefers-reduced-motion:reduce){.image-viewer-spinner{animation:none}}@media(prefers-reduced-transparency:reduce){.image-viewer::backdrop{backdrop-filter:none}}
</style>
