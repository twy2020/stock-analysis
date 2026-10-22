<script setup lang="ts">
import { ref,onMounted } from 'vue'
import { api } from '../api/client'
defineProps<{providers:Array<{id:string;name:string;accounts:Array<{id:string;name:string;model:string}>}>}>()
const enabled=ref(false),accountIds=ref<string[]>([]),busy=ref(false),loaded=ref(false),error=ref(''),saved=ref(false)
const backend=ref('model'),ocrAvailable=ref(false),managedByCore=ref(false)
onMounted(async()=>{try{const value=await api<{enabled:boolean;accountIds:string[];backend?:string;ocrAvailable?:boolean;managedByCore?:boolean}>('/api/v1/admin/settings/images');enabled.value=value.enabled;accountIds.value=value.accountIds;backend.value=value.backend||'model';ocrAvailable.value=!!value.ocrAvailable;managedByCore.value=!!value.managedByCore;loaded.value=true}catch(e){error.value=e instanceof Error?e.message:'设置加载失败'}})
async function save(){busy.value=true;error.value='';saved.value=false;try{await api('/api/v1/admin/settings/images',{method:'PUT',body:JSON.stringify({enabled:enabled.value,backend:backend.value,accountIds:accountIds.value})});saved.value=true}catch(e){error.value=e instanceof Error?e.message:'保存失败'}finally{busy.value=false}}
</script>
<template>
  <form class="image-settings" @submit.prevent="save">
    <div class="image-setting-heading"><strong>图片消息</strong><label><input v-model="enabled" type="checkbox" :disabled="busy||!loaded"/>允许用户上传图片</label></div>
    <div v-if="!managedByCore" class="image-backend" role="group" aria-label="图片识别方式">
      <label><input v-model="backend" type="radio" value="model" :disabled="busy||!loaded"/>视觉模型</label>
      <label><input v-model="backend" type="radio" value="ocr" :disabled="busy||!loaded||!ocrAvailable"/>OCR 视觉服务{{ocrAvailable?'':'（未配置）'}}</label>
    </div>
    <p>{{managedByCore?'由 Agent Core 统一调用 OCR 视觉服务。图片识别结果需要核对。':backend==='ocr'?'复用 OCR 服务的视觉模型，识别结果缓存用于后续对话。图片识别结果可能有误。':'仅选择已确认支持图片输入的模型账号。图片消息限定使用所选账号。'}}</p>
    <div v-if="backend==='model'&&!managedByCore" class="image-models"><template v-for="provider in providers" :key="provider.id"><label v-for="account in provider.accounts" :key="account.id"><input v-model="accountIds" type="checkbox" :value="account.id" :disabled="busy||!loaded"/><span>{{provider.name}} · {{account.name}} · {{account.model}}</span></label></template></div>
    <footer><span v-if="error" role="alert">{{error}}</span><span v-else-if="saved" role="status">已保存</span><button class="secondary-button" :disabled="busy||!loaded">保存图片设置</button></footer>
  </form>
</template>
<style scoped>
.image-backend{display:flex;flex-wrap:wrap;gap:16px;margin-top:14px}
.image-settings{max-width:880px;border:1px solid var(--separator);border-radius:12px;padding:16px;margin:12px 0 20px;font-size:14px}.image-setting-heading{display:flex;align-items:center;gap:20px}.image-setting-heading strong{font-size:14px}.image-settings label{display:flex;align-items:center;gap:8px;cursor:pointer}.image-settings p{color:var(--ink-secondary);line-height:1.6}.image-models{display:grid;gap:9px;max-height:160px;overflow:auto;scrollbar-width:thin}.image-models label{min-width:0}.image-models span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.image-settings input{width:15px;height:15px;flex:none}.image-settings footer{display:flex;align-items:center;justify-content:flex-end;gap:12px;margin-top:14px}.image-settings [role=alert]{color:var(--danger)}
</style>
