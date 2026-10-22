import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from './stores/session'
import LoginView from './views/LoginView.vue'
import PasswordChangeView from './views/PasswordChangeView.vue'
import ChatView from './views/ChatView.vue'
import AdminView from './views/AdminView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/change-password', component: PasswordChangeView },
    { path: '/', component: ChatView },
    { path: '/admin', component: AdminView, meta: { admin: true } },
  ],
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  if (!session.ready) await session.bootstrap()
  if (!session.user && !to.meta.public) return '/login'
  if (session.user && to.path === '/login') return session.user.passwordChangeRequired ? '/change-password' : '/'
  if (session.user?.passwordChangeRequired && to.path !== '/change-password') return '/change-password'
  if (to.meta.admin && !session.isAdmin) return '/'
  return true
})
