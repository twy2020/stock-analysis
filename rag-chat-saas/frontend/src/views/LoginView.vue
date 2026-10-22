<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Eye, EyeOff, LoaderCircle } from 'lucide-vue-next'
import { useSessionStore } from '../stores/session'
import { api } from '../api/client'
import ThemeToggle from '../components/ThemeToggle.vue'

const session = useSessionStore()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const pending = ref(false)
const showPassword = ref(false)
const registering = ref(false)
const confirmPassword = ref('')
const inviteCode = ref('')
const inviteRequired = ref(false)
const policyReady = ref(false)
async function switchMode() {
  registering.value = !registering.value
  error.value = ''; password.value = ''; confirmPassword.value = ''; inviteCode.value = ''
  if (registering.value) {
    policyReady.value = false
    try { const policy = await api<{inviteRequired:boolean}>('/api/v1/auth/registration'); inviteRequired.value = policy.inviteRequired; policyReady.value = true }
    catch { error.value = '无法读取注册设置，请稍后重新进入注册' }
  }
}

async function submit() {
  if (pending.value) return
  error.value = ''
  pending.value = true
  try {
    if (registering.value) {
      if (!policyReady.value) throw new Error('注册设置尚未加载')
      if (password.value !== confirmPassword.value) throw new Error('两次输入的密码不一致')
      await session.register(username.value, password.value, inviteCode.value)
    } else await session.login(username.value, password.value)
    await router.replace(session.user?.passwordChangeRequired ? '/change-password' : '/')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败'
    if (registering.value) {
      try { inviteRequired.value = (await api<{inviteRequired:boolean}>('/api/v1/auth/registration')).inviteRequired } catch { /* Keep the submitted error visible. */ }
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main class="login-scene">
    <ThemeToggle class="auth-theme-toggle"/>
    <section class="login-window" aria-labelledby="login-title">
      <aside class="login-brand">
        <div class="brand-name"><img src="/favicon.svg" alt="" width="36" height="36"/><span>Stock Lab</span></div>
        <div class="brand-copy"><p class="brand-eyebrow">MARKET RESEARCH</p><h1 id="login-title">股票研究</h1><p class="brand-description">行情 · 事件统计 · 策略回测</p></div>
        <span class="brand-caption">Stock Lab · 研究工作台</span>
      </aside>
      <div class="login-form-panel">
      <header><h2>{{registering?'创建账号':'欢迎回来'}}</h2><p>{{registering?'注册后进入股票研究工作台':'登录你的研究账号'}}</p></header>
      <form @submit.prevent="submit" :aria-busy="pending">
        <div class="login-field">
        <label for="username">账号</label>
        <input id="username" v-model.trim="username" name="username" autocomplete="username" autocapitalize="none" :spellcheck="false" :placeholder="registering?'3–80 位，不含空格':'输入账号'" :minlength="registering?3:undefined" maxlength="80" :readonly="pending" required />
        </div><div class="login-field">
        <label for="password">密码</label>
        <div class="password-field"><input id="password" v-model="password" name="password" :type="showPassword?'text':'password'" :autocomplete="registering?'new-password':'current-password'" :placeholder="registering?'至少 12 个字符':'输入密码'" :minlength="registering?12:undefined" maxlength="256" :readonly="pending" required />
        <button type="button" class="password-visibility" :aria-label="showPassword?'隐藏密码':'显示密码'" :aria-pressed="showPassword" @click="showPassword=!showPassword"><EyeOff v-if="showPassword" :size="18"/><Eye v-else :size="18"/></button></div>
        </div>
        <div class="login-expand" :class="{'is-open':registering}" :inert="!registering" :aria-hidden="!registering">
          <fieldset class="login-expand-inner" :disabled="!registering || pending">
            <div class="login-field"><label for="confirm-password">确认密码</label><input id="confirm-password" v-model="confirmPassword" type="password" autocomplete="new-password" placeholder="再次输入密码" required /></div>
            <div class="login-invite-expand" :class="{'is-open':inviteRequired}" :inert="!inviteRequired" :aria-hidden="!inviteRequired"><div class="login-invite-inner"><div class="login-field"><label for="invite-code">邀请码</label><input id="invite-code" v-model.trim="inviteCode" autocomplete="off" placeholder="输入管理员提供的邀请码" maxlength="128" :disabled="!inviteRequired" required /></div></div></div>
          </fieldset>
        </div>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="pending || (registering && !policyReady)">
          {{ pending ? (registering?'正在注册':'正在登录') : (registering?'注册并登录':'登录') }}
          <LoaderCircle v-if="pending" class="login-spinner" :size="18" aria-hidden="true"/><ArrowRight v-else :size="18" aria-hidden="true"/>
        </button>
      </form>
      <p class="login-help">{{registering?'已有账号？':'还没有账号？'}} <button type="button" class="text-button" :disabled="pending" @click="switchMode">{{registering?'返回登录':'注册账号'}}</button></p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-scene { width: 100%; height: 100%; overflow: auto; display: grid; place-items: center; padding: 40px 24px; background: #dce5f1 url('/login-landscape.svg') center / cover no-repeat; color: #1d2638; }
.login-window { display: grid; grid-template-columns: 1.08fr 1fr; width: min(1040px,100%); min-height: 600px; border: 1px solid rgb(255 255 255 / 75%); border-radius: 28px; background: rgb(255 255 255 / 90%); box-shadow: 0 32px 100px rgb(31 53 88 / 16%), 0 2px 8px rgb(31 53 88 / 4%); overflow: hidden; }
.login-brand { position: relative; display: flex; flex-direction: column; padding: 44px; background: linear-gradient(150deg,rgb(236 243 253 / 70%),rgb(209 224 247 / 65%)); overflow: hidden; }
.login-brand::after { content: ''; position: absolute; width: 430px; height: 430px; border: 1px solid rgb(255 255 255 / 65%); border-radius: 50%; right: -160px; bottom: -250px; box-shadow: 0 0 0 48px rgb(255 255 255 / 12%),0 0 0 96px rgb(255 255 255 / 9%); pointer-events: none; }
.brand-name { display: flex; align-items: center; gap: 12px; font-size: 17px; font-weight: 600; letter-spacing: .1px; }
.brand-name img { border-radius: 10px; box-shadow: 0 4px 12px rgb(32 101 224 / 12%); }
.brand-copy { margin: auto 0; padding: 60px 0; position: relative; z-index: 1; }
.brand-eyebrow { margin: 0 0 20px; font-size: 13px; color: #56708e; letter-spacing: 1px; }
.brand-copy h1 { margin: 0; font-size: clamp(28px,3vw,40px); font-weight: 650; line-height: 1.5; letter-spacing: -1px; }
.brand-description { font-size: 15px; color: #61748a; line-height: 1.9; margin: 24px 0 0; }
.brand-caption { font-size: 12px; color: #647b92; }
.login-form-panel { align-self: center; padding: 60px 54px; }
.login-form-panel header { margin-bottom: 34px; }
.login-form-panel h2 { margin: 0 0 10px; font-size: 28px; font-weight: 650; letter-spacing: -.6px; }
.login-form-panel header p { margin: 0; color: #78808e; font-size: 14px; }
.login-form-panel form { display: grid; gap: 22px; }
.login-expand,.login-invite-expand { display:grid;grid-template-rows:0fr;opacity:0;transition:grid-template-rows 320ms cubic-bezier(.22,1,.36,1),opacity 200ms ease,margin-top 320ms cubic-bezier(.22,1,.36,1); }
.login-expand { margin-top:-22px; }
.login-expand.is-open { margin-top:0; }
.login-expand.is-open,.login-invite-expand.is-open { grid-template-rows:1fr;opacity:1; }
.login-expand-inner { min-width:0;min-height:0;overflow:hidden;border:0;padding:0;margin:0; }
.login-invite-inner { min-height:0;overflow:hidden; }
.login-invite-inner>.login-field { padding-top:22px; }
.login-field { display: grid; gap: 9px; }
.login-field label { font-size: 13px; font-weight: 550; color: #4d5665; }
.login-field input { display: block; width: 100%; height: 50px; border: 1px solid #dce1e9; border-radius: 12px; padding: 0 15px; background: rgb(247 249 252 / 90%); color: #202a3b; font: inherit; font-size: 16px; box-shadow: none; outline: none; transition: border-color 150ms,box-shadow 150ms; }
.login-field input::placeholder { color: #929aa8; font-size: 14px; }
.login-field input:focus { border-color: #6e9ce9; box-shadow: 0 0 0 3px rgb(57 120 219 / 12%); background: #fff; }
.password-field { position: relative; }
.password-field input { padding-right: 50px; }
.password-visibility { position: absolute; top: 3px; right: 3px; width: 44px; height: 44px; display: grid; place-items: center; border: 0; border-radius: 10px; background: transparent; color: #7c8696; cursor: pointer; }
.password-visibility:hover { color: #285fb8; background: #eef2f8; }
.login-submit { display: flex; align-items: center; justify-content: center; gap: 10px; height: 50px; margin-top: 6px; border: 0; border-radius: 12px; background: #2264d8; color: #fff; font-size: 15px; font-weight: 550; cursor: pointer; box-shadow: 0 4px 12px rgb(34 100 216 / 15%); }
.login-submit:hover:not(:disabled) { background: #1957c2; }
.login-submit:disabled { opacity: .65; cursor: wait; }
.login-help { font-size: 12px; line-height: 1.7; color: #858d9b; margin: 24px 0 0; }
.login-error { margin: -2px 0; padding: 10px 12px; border-radius: 10px; background: #fff0f0; color: #bb3542; font-size: 13px; line-height: 1.6; }
.login-spinner { animation: login-spin 1s linear infinite; }
@keyframes login-spin { to { transform: rotate(360deg); } }
@media(max-width:760px) { .login-scene { padding: 24px 16px; } .login-window { grid-template-columns: 1fr; min-height: 0; max-width: 440px; border-radius: 22px; } .login-brand { padding: 26px 28px; } .brand-copy { padding: 22px 0 0; } .brand-copy h1 { font-size: 25px; letter-spacing: -.5px; } .brand-eyebrow,.brand-caption,.brand-description { display: none; } .brand-name { font-size: 16px; } .login-form-panel { padding: 30px 28px; } .login-form-panel header { margin-bottom: 26px; } .login-form-panel h2 { font-size: 24px; } }
@media(prefers-reduced-motion:reduce) { .login-spinner { animation: none; } .login-field input,.login-expand,.login-invite-expand { transition: none; } }
</style>
