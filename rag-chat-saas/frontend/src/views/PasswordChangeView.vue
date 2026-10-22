<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { KeyRound } from 'lucide-vue-next'
import { useSessionStore } from '../stores/session'
import ThemeToggle from '../components/ThemeToggle.vue'

const session = useSessionStore()
const router = useRouter()
const password = ref('')
const confirmation = ref('')
const error = ref('')
const pending = ref(false)
const leaving = ref(false)

async function logout() {
  if (pending.value || leaving.value) return
  error.value = ''
  leaving.value = true
  try {
    await session.logout()
    password.value = ''
    confirmation.value = ''
    await router.replace('/login')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '退出失败，请重试'
  } finally {
    leaving.value = false
  }
}

async function submit() {
  if (pending.value || leaving.value) return
  error.value = ''
  if (password.value !== confirmation.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  if (password.value.length < 12) {
    error.value = '密码至少需要 12 个字符'
    return
  }
  pending.value = true
  try {
    await session.changePassword(password.value)
    await router.replace('/')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '密码修改失败'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main class="auth-layout">
    <ThemeToggle class="auth-theme-toggle"/>
    <section class="auth-panel" aria-labelledby="password-title">
      <header>
        <div class="product-mark"><KeyRound :size="22" /></div>
        <h1 id="password-title">设置新密码</h1>
      </header>
      <div class="business-notice">当前账号需要设置新密码才能继续使用。也可以退出，返回登录页切换账号。</div>
      <form @submit.prevent="submit">
        <label for="new-password">新密码</label>
        <input id="new-password" v-model="password" name="password" type="password" autocomplete="new-password" required />
        <label for="confirmation">确认密码</label>
        <input id="confirmation" v-model="confirmation" name="confirmation" type="password" autocomplete="new-password" required />
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="primary-button" type="submit" :disabled="pending || leaving">{{ pending ? '正在保存' : '保存并进入' }}</button>
        <button class="secondary-button" type="button" :disabled="pending || leaving" @click="logout">{{ leaving ? '正在退出' : '退出并返回登录' }}</button>
      </form>
    </section>
  </main>
</template>
