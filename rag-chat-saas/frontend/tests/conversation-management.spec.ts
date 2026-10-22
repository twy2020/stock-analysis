import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', () => ({ api, ApiError: class extends Error {}, streamApi: vi.fn() }))

import { useChatStore } from '../src/stores/chat'

describe('conversation management', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.mockReset()
  })

  it('renames the matching list and active conversation', async () => {
    const store = useChatStore()
    const conversation = { id: 'c1', title: '旧标题', knowledgeBaseId: 'kb1', createdAt: 'a', updatedAt: 'a' }
    store.conversations = [conversation]
    store.activeConversation = conversation
    api.mockResolvedValue({ ...conversation, title: '新标题', updatedAt: 'b' })

    await store.renameConversation(conversation, '新标题')

    expect(api).toHaveBeenCalledWith('/api/v1/conversations/c1', expect.objectContaining({ method: 'PATCH' }))
    expect(store.conversations[0].title).toBe('新标题')
    expect(store.activeConversation?.title).toBe('新标题')
  })

  it('deletes the row and clears an active conversation', async () => {
    const store = useChatStore()
    const conversation = { id: 'c1', title: '待删除', knowledgeBaseId: 'kb1', createdAt: 'a', updatedAt: 'a' }
    store.conversations = [conversation]
    store.activeConversation = conversation
    store.messages = [{ id: 'm1', role: 'USER', content: '问题', status: 'COMPLETED', citations: [] }]
    api.mockResolvedValue(undefined)

    await store.deleteConversation(conversation)

    expect(api).toHaveBeenCalledWith('/api/v1/conversations/c1', { method: 'DELETE' })
    expect(store.conversations).toEqual([])
    expect(store.activeConversation).toBeNull()
    expect(store.messages).toEqual([])
  })
})
