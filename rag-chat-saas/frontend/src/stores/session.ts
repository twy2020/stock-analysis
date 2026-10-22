import { defineStore } from 'pinia'
import { api, setCsrfToken, type User } from '../api/client'
import { useChatStore } from './chat'

type AuthResponse = { user: User; csrfToken: string }

export const useSessionStore = defineStore('session', {
  state: () => ({ user: null as User | null, ready: false }),
  getters: { isAdmin: (state) => state.user?.role === 'ADMIN' },
  actions: {
    expire() {
      useChatStore().resetForSession()
      setCsrfToken('')
      this.user = null
      this.ready = true
    },
    async bootstrap() {
      try {
        const response = await api<AuthResponse>('/api/v1/auth/session')
        if (this.user?.username !== response.user.username) useChatStore().resetForSession()
        setCsrfToken(response.csrfToken)
        this.user = response.user
      } catch {
        useChatStore().resetForSession()
        setCsrfToken('')
        this.user = null
      } finally {
        this.ready = true
      }
    },
    async login(username: string, password: string) {
      const response = await api<AuthResponse>('/api/v1/auth/login', {
        method: 'POST', body: JSON.stringify({ username, password }),
      })
      useChatStore().resetForSession()
      setCsrfToken(response.csrfToken)
      this.user = response.user
      this.ready = true
    },
    async changePassword(password: string) {
      const response = await api<AuthResponse>('/api/v1/auth/change-password', {
        method: 'POST', body: JSON.stringify({ password }),
      })
      setCsrfToken(response.csrfToken)
      this.user = response.user
    },
    async register(username: string, password: string, inviteCode: string) {
      const response = await api<AuthResponse>('/api/v1/auth/register', {
        method: 'POST', body: JSON.stringify({ username, password, inviteCode }),
      })
      useChatStore().resetForSession()
      setCsrfToken(response.csrfToken)
      this.user = response.user
      this.ready = true
    },
    async logout() {
      await api<void>('/api/v1/auth/logout', { method: 'POST' })
      useChatStore().resetForSession()
      this.user = null
      setCsrfToken('')
    },
  },
})
