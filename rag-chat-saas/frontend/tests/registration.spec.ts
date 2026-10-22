import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
const mocks=vi.hoisted(()=>({register:vi.fn(),login:vi.fn(),replace:vi.fn(),api:vi.fn()}))
vi.mock('vue-router',()=>({useRouter:()=>({replace:mocks.replace})}))
vi.mock('../src/stores/session',()=>({useSessionStore:()=>({register:mocks.register,login:mocks.login,user:{passwordChangeRequired:false}})}))
vi.mock('../src/api/client',()=>({api:mocks.api}))
import LoginView from '../src/views/LoginView.vue'
import RegistrationSettings from '../src/components/RegistrationSettings.vue'
beforeEach(()=>{vi.clearAllMocks();mocks.api.mockResolvedValue({inviteRequired:true,inviteCodeConfigured:true})})
it('shows required invitation and validates confirmation before registering and entering chat',async()=>{
 const wrapper=mount(LoginView)
 await wrapper.get('.login-help button').trigger('click');await flushPromises()
 expect(wrapper.find('#invite-code').exists()).toBe(true)
 await wrapper.get('#username').setValue('new-user')
 await wrapper.get('#password').setValue('long-password-42')
 await wrapper.get('#confirm-password').setValue('different')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(mocks.register).not.toHaveBeenCalled()
 await wrapper.get('#confirm-password').setValue('long-password-42')
 await wrapper.get('#invite-code').setValue('test-code')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(mocks.register).toHaveBeenCalledWith('new-user','long-password-42','test-code')
 expect(mocks.replace).toHaveBeenCalledWith('/')
 await wrapper.get('.login-help button').trigger('click')
 // Height transitions retain the fields; inactive fields must not participate
 // in validation or keyboard interaction after switching back to login.
 expect(wrapper.get('.login-expand').attributes('aria-hidden')).toBe('true')
 expect(wrapper.get('#invite-code').element.matches(':disabled')).toBe(true)
})
it('saves admin policy without exposing the saved invitation',async()=>{
 const wrapper=mount(RegistrationSettings);await flushPromises()
 const input=wrapper.get('input[type=password]')
 expect((input.element as HTMLInputElement).value).toBe('')
 await input.setValue('new-code');await wrapper.get('form').trigger('submit');await flushPromises()
 expect(mocks.api).toHaveBeenLastCalledWith('/api/v1/admin/settings/registration',{method:'PUT',body:JSON.stringify({inviteRequired:true,inviteCode:'new-code'})})
 expect((input.element as HTMLInputElement).value).toBe('')
})
it('disables policy saving after a failed load and offers retry',async()=>{
 mocks.api.mockRejectedValueOnce(new Error('unavailable'))
 const wrapper=mount(RegistrationSettings);await flushPromises()
 expect(wrapper.get('.compact-button').attributes('disabled')).toBeDefined()
 await wrapper.get('.text-button').trigger('click');await flushPromises()
 expect(wrapper.get('.compact-button').attributes('disabled')).toBeUndefined()
})
