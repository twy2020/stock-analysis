import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import ImageComposer from '../src/components/chat/ImageComposer.vue'
vi.mock('../src/api/client', () => ({ api: vi.fn().mockResolvedValue({ enabled: true }) }))
afterEach(() => { document.body.innerHTML = '' })

it('opens the file picker from a non-submit button and keeps previews outside the toolbar', async () => {
  const preview = document.createElement('div')
  document.body.append(preview)
  const wrapper = mount(ImageComposer, { attachTo: document.body, props: {
    modelValue: [{ id: 'image-1', name: 'photo.png', url: '/api/v1/images/image-1', mediaType: 'image/png' }],
    previewTarget: preview,
  } })
  await flushPromises()
  const input = wrapper.get('input[type=file]').element as HTMLInputElement
  const click = vi.spyOn(input, 'click').mockImplementation(() => {})
  const button = wrapper.get('button[aria-label="添加图片"]')
  expect(button.attributes('type')).toBe('button')
  await button.trigger('click')
  expect(click).toHaveBeenCalledOnce()
  expect(preview.querySelector('img')?.getAttribute('src')).toBe('/api/v1/images/image-1')
  expect(wrapper.find('img').exists()).toBe(false)
  await wrapper.setProps({ disabled: true })
  expect((button.element as HTMLButtonElement).disabled).toBe(true)
  wrapper.unmount()
})
