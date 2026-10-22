import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import './styles/base.css'
import './styles/stock.css'
import './styles/stock-analysis.css'
import './styles/theme.css'
import { initializeTheme } from './theme'
import { onSessionExpired } from './api/client'
import { useSessionStore } from './stores/session'

initializeTheme()
const pinia = createPinia()
onSessionExpired(() => {
  const session = useSessionStore(pinia)
  if (!session.user) return
  session.expire()
  void router.replace('/login')
})
createApp(App).use(pinia).use(router).mount('#app')
