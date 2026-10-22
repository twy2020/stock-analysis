import { mount, flushPromises } from '@vue/test-utils'
import { expect,it,vi } from 'vitest'
import WebProxySettings from '../src/components/WebProxySettings.vue'
import {api} from '../src/api/client'
vi.mock('../src/api/client',()=>({api:vi.fn(async()=>({enabled:false,configured:true,endpoint:'http://host.docker.internal:7890',mode:'selected',domains:['bing.com']}))}))
it('keeps saved proxy credentials out of fields and submits routing policy',async()=>{
  const wrapper=mount(WebProxySettings)
  await flushPromises()
  expect((wrapper.get('input[type=password]').element as HTMLInputElement).value).toBe('')
  await wrapper.get('input[type=checkbox]').setValue(true)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api).toHaveBeenLastCalledWith('/api/v1/admin/settings/web-proxy',{method:'PUT',body:JSON.stringify({enabled:true,mode:'selected',domains:['bing.com']})})
  expect(wrapper.get('[role=status]').text()).toContain('已保存')
})
