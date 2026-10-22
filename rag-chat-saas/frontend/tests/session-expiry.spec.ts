import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, streamApi, onSessionExpired } from '../src/api/client'
import { useSessionStore } from '../src/stores/session'
import { useChatStore } from '../src/stores/chat'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => { useChatStore().leavePage(); onSessionExpired(); vi.unstubAllGlobals() })

function expiredSession() {
  const session = useSessionStore()
  session.user = { username: 'test', role: 'USER', passwordChangeRequired: false }
  const redirect = vi.fn(() => session.expire())
  onSessionExpired(redirect)
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ code: 'AUTHENTICATION_REQUIRED', message: 'Sign in required' }, { status: 401 })))
  return { session, redirect }
}

it('invalidates a cached session and clears polling when chat reload returns 401', async () => {
  const { session, redirect } = expiredSession()
  const chat = useChatStore()
  await chat.load()
  expect(redirect).toHaveBeenCalled()
  expect(session.user).toBeNull()
  expect(session.ready).toBe(true)
  expect(chat.pollTimer).toBeNull()
  expect(chat.loading).toBe(false)
  expect(chat.error).toBe('')
})

it('stops observing an unauthorized stream without retries', async () => {
  const { session } = expiredSession()
  const chat = useChatStore()
  chat.sending = true
  chat.messages = [{ id: 'a', role: 'ASSISTANT', content: '', citations: [], status: 'STREAMING' }]
  await chat.observe({ id: 'r', conversationId: 'c', userMessageId: 'u', assistantMessageId: 'a', status: 'RUNNING' })
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(session.user).toBeNull()
  expect(chat.sending).toBe(false)
  expect(chat.streamController).toBeNull()
  expect(chat.messages).toEqual([])
})

it('reports stream authentication errors even without a registered handler', async () => {
  expiredSession()
  onSessionExpired()
  await expect(streamApi('/api/v1/conversations/c/events', null, () => {}, undefined, 'GET'))
    .rejects.toMatchObject({ status: 401, code: 'AUTHENTICATION_REQUIRED' })
})

it.each(['login', 'register', 'session'])('does not redirect for an unauthenticated %s request', async (endpoint) => {
  const { session, redirect } = expiredSession()
  await expect(api(`/api/v1/auth/${endpoint}`)).rejects.toMatchObject({ status: 401 })
  expect(redirect).not.toHaveBeenCalled()
  expect(session.user?.username).toBe('test')
})
