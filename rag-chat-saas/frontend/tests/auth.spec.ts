import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

import LoginView from '../src/views/LoginView.vue'
import PasswordChangeView from '../src/views/PasswordChangeView.vue'
import { useSessionStore } from '../src/stores/session'
import { setCsrfToken } from '../src/api/client'

describe('authentication views', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    replace.mockReset()
    setCsrfToken('test-csrf')
  })
  afterEach(() => vi.unstubAllGlobals())

  it('logs out from required password change without filling the form', async () => {
    const session = useSessionStore()
    session.user = { username: 'operator', role: 'USER', passwordChangeRequired: true }
    const request = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', request)
    const wrapper = mount(PasswordChangeView)
    await wrapper.get('button.secondary-button').trigger('click')
    await flushPromises()
    expect(request).toHaveBeenCalledWith('/api/v1/auth/logout', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }))
    expect(request.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('test-csrf')
    expect(session.user).toBeNull()
    expect(replace).toHaveBeenCalledWith('/login')
  })

  it('keeps the session on logout failure and allows retry', async () => {
    const session = useSessionStore()
    session.user = { username: 'operator', role: 'USER', passwordChangeRequired: true }
    const request = vi.fn().mockRejectedValueOnce(new Error('连接失败，请重试'))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', request)
    const wrapper = mount(PasswordChangeView)
    await wrapper.get('button.secondary-button').trigger('click')
    await flushPromises()
    expect(session.user).not.toBeNull()
    expect(replace).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('连接失败')
    expect(wrapper.get('button.secondary-button').attributes('disabled')).toBeUndefined()
    await wrapper.get('button.secondary-button').trigger('click')
    await flushPromises()
    expect(session.user).toBeNull()
    expect(replace).toHaveBeenCalledWith('/login')
  })

  it('submits credentials and exposes forced password state', async () => {
    const session = useSessionStore()
    session.login = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(LoginView)
    await wrapper.get('input[name="username"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('Initial-Password-42!')
    await wrapper.get('form').trigger('submit')
    expect(session.login).toHaveBeenCalledWith('admin', 'Initial-Password-42!')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('validates confirmation before changing the initial password', async () => {
    const session = useSessionStore()
    session.changePassword = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(PasswordChangeView)
    await wrapper.get('input[name="password"]').setValue('New-Password-84!')
    await wrapper.get('input[name="confirmation"]').setValue('different')
    await wrapper.get('form').trigger('submit')
    expect(session.changePassword).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('两次输入')
  })
})
