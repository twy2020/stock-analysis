<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
const required=ref(false),configured=ref(false),code=ref(''),loading=ref(true),saving=ref(false),error=ref(''),notice=ref(''),loaded=ref(false)
async function load(){loading.value=true;error.value='';try {const value=await api<{inviteRequired:boolean;inviteCodeConfigured:boolean}>('/api/v1/admin/settings/registration');required.value=value.inviteRequired;configured.value=value.inviteCodeConfigured;loaded.value=true}catch(e){error.value=e instanceof Error?e.message:'读取失败'}finally{loading.value=false}}
onMounted(load)
async function save(){saving.value=true;error.value='';notice.value='';try{const value=await api<{inviteRequired:boolean;inviteCodeConfigured:boolean}>('/api/v1/admin/settings/registration',{method:'PUT',body:JSON.stringify({inviteRequired:required.value,inviteCode:code.value})});required.value=value.inviteRequired;configured.value=value.inviteCodeConfigured;code.value='';notice.value='注册设置已保存'}catch(e){error.value=e instanceof Error?e.message:'保存失败'}finally{saving.value=false}}
</script>
<template>
 <form class="registration-settings" @submit.prevent="save">
  <div class="registration-heading"><strong>注册设置</strong><span>仅影响保存后的新注册，已有用户登录不受影响。</span></div>
  <div class="registration-fields"><label class="registration-toggle"><input v-model="required" type="checkbox" :disabled="!loaded||loading||saving"/>注册需要邀请码</label><label class="registration-code">系统邀请码<input v-model.trim="code" type="password" autocomplete="new-password" minlength="6" maxlength="128" :placeholder="configured?'已设置，留空保持不变':'设置 6–128 个字符'" :disabled="!loaded||loading||saving" :required="required&&!configured"/></label><button class="compact-button" :disabled="!loaded||loading||saving">{{saving?'保存中':'保存设置'}}</button><button v-if="!loaded&&!loading" type="button" class="text-button" @click="load">重新加载</button></div>
  <p v-if="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
 </form>
</template>
<style scoped>
.registration-settings{padding:16px 0;border-bottom:1px solid var(--separator);margin-bottom:16px;font-size:13px}
.registration-heading{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:14px}.registration-heading span{color:var(--ink-secondary);font-size:12px}
.registration-fields{display:flex;align-items:center;flex-wrap:wrap;gap:16px}.registration-toggle{display:flex;align-items:center;gap:8px}.registration-toggle input{width:16px;height:16px;accent-color:var(--accent)}.registration-code{display:flex;align-items:center;gap:10px}.registration-code input{width:240px;max-width:55vw;height:36px;border:1px solid var(--separator);border-radius:10px;padding:0 10px;background:var(--surface);color:var(--ink);font:inherit}.registration-settings p{margin:10px 0 0;color:var(--ink-secondary)}.registration-settings [role=alert]{color:var(--danger)}
</style>
