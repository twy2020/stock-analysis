import { mount, flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import { api } from '../src/api/client'
import FeatureSettings from '../src/components/FeatureSettings.vue'
vi.mock('../src/api/client',()=>({api:vi.fn(async(path:string)=>path.endsWith('/settings/model')?{backend:'local'}:{ragEnabled:false,webEnabled:false})}))

it('loads the administrator RAG policy and saves the selected value',async()=>{
  const wrapper=mount(FeatureSettings)
  await flushPromises()
  const checkbox=wrapper.get('input[type="checkbox"]')
  expect((checkbox.element as HTMLInputElement).checked).toBe(false)
  await checkbox.setValue(true)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api).toHaveBeenLastCalledWith('/api/v1/admin/settings/features',{
    method:'PUT',body:JSON.stringify({ragEnabled:true,webEnabled:false}),
  })
  expect(wrapper.get('[role="status"]').text()).toContain('设置已保存')
  expect(wrapper.classes()).not.toContain('aligned-form')
  await checkbox.setValue(false)
  expect(wrapper.find('[role="status"]').exists()).toBe(false)
  wrapper.unmount()
})
