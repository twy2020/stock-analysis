import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useChatStore } from '../src/stores/chat'
import { useSessionStore } from '../src/stores/session'

const conversation = { id: 'old', title: '旧用户对话', knowledgeBaseId: 'kb', createdAt: '', updatedAt: '' }
const message = { id: 'm', role: 'USER' as const, content: '私有消息', status: 'COMPLETED' as const, citations: [] }
beforeEach(() => setActivePinia(createPinia()))
afterEach(() => { useChatStore().leavePage(); vi.unstubAllGlobals() })

it('clears all chat data on logout and starts empty on another login', async () => {
  const chat = useChatStore()
  const session = useSessionStore()
  chat.activeConversation = conversation
  chat.messages = [message]
  chat.conversations = [conversation]
  chat.selectedKnowledgeBaseId = 'kb'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(Response.json({ user: { username: 'next', role: 'USER', passwordChangeRequired: false }, csrfToken: 'next' })))
  await session.logout()
  expect(chat.messages).toEqual([])
  expect(chat.conversations).toEqual([])
  expect(chat.activeConversation).toBeNull()
  expect(chat.selectedKnowledgeBaseId).toBe('')
  // Login is an independent boundary, even if stale state was restored elsewhere.
  chat.messages = [message]
  await session.login('next', 'password')
  expect(chat.messages).toEqual([])
})

it('loads history without automatically opening it', async () => {
  const chat = useChatStore()
  const fetcher = vi.fn(async (url: string) => Response.json(
    url.endsWith('/capabilities') ? { reasoningToggle: false }
      : url.endsWith('/knowledge-bases') ? [{ id: 'kb' }] : [conversation]))
  vi.stubGlobal('fetch', fetcher)
  await chat.load()
  expect(chat.conversations).toEqual([conversation])
  expect(chat.activeConversation).toBeNull()
  expect(chat.messages).toEqual([])
  expect(fetcher.mock.calls.some(([url]) => url.endsWith('/messages'))).toBe(false)
})

it('discards an old history response after logout', async () => {
  const chat = useChatStore()
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/logout')
    ? Promise.resolve(new Response(null, { status: 204 }))
    : new Promise<Response>(done => { resolve = done })))
  const pending = chat.openConversation(conversation)
  await useSessionStore().logout()
  resolve(Response.json([message]))
  await pending
  expect(chat.messages).toEqual([])
  expect(chat.activeConversation).toBeNull()
})

it('discards a pending conversation creation after switching accounts', async () => {
  const chat = useChatStore()
  chat.selectedKnowledgeBaseId = 'kb'
  let resolve!: (response: Response) => void
  const fetcher = vi.fn((url: string) => url.endsWith('/logout')
    ? Promise.resolve(new Response(null, { status: 204 }))
    : new Promise<Response>(done => { resolve = done }))
  vi.stubGlobal('fetch', fetcher)
  const pending = chat.send('旧账号问题')
  await useSessionStore().logout()
  resolve(Response.json(conversation))
  await pending
  expect(chat.messages).toEqual([])
  expect(chat.conversations).toEqual([])
  expect(chat.activeConversation).toBeNull()
  expect(fetcher).toHaveBeenCalledTimes(2)
})

it('does not restore old lists when loading finishes after logout', async () => {
  const chat = useChatStore()
  const replies: Array<() => void> = []
  vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/logout')
    ? Promise.resolve(new Response(null, { status: 204 }))
    : new Promise<Response>(resolve => replies.push(() => resolve(Response.json(
      url.endsWith('/capabilities') ? { reasoningToggle: true } : [conversation]))))))
  const pending = chat.load()
  await useSessionStore().logout()
  replies.forEach(resolve => resolve())
  await pending
  expect(chat.conversations).toEqual([])
  expect(chat.knowledgeBases).toEqual([])
  expect(chat.reasoningAvailable).toBe(false)
})

it('aborts the previous stream and ignores late events after logout', async () => {
  const chat = useChatStore()
  chat.selectedKnowledgeBaseId = 'kb'
  chat.activeConversation = conversation
  let stream!: ReadableStreamDefaultController<Uint8Array>
  let signal!: AbortSignal
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    if (url.endsWith('/logout')) return new Response(null, { status: 204 })
    if (url.endsWith('/runs')) return Response.json({ id:'run', conversationId:'old', userMessageId:'u1', assistantMessageId:'a1', status:'RUNNING' })
    if (url.endsWith('/messages')) return Response.json([{ id:'a1', role:'ASSISTANT', content:'', status:'STREAMING', citations:[] }])
    signal = options.signal as AbortSignal
    return new Response(new ReadableStream({ start(controller) { stream = controller } }))
  }))
  const pending = chat.send('旧问题')
  await flushPromises()
  await useSessionStore().logout()
  expect(signal.aborted).toBe(true)
  stream.enqueue(new TextEncoder().encode('event: error\ndata: {"code":"NO_EVIDENCE"}\n\nevent: complete\ndata: {"content":"旧回答"}\n\n'))
  stream.close()
  await pending
  expect(chat.messages).toEqual([])
  expect(chat.error).toBe('')
  expect(chat.sending).toBe(false)
})
