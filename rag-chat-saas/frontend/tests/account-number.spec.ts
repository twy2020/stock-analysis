import { mount, flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import AccountNumberField from '../src/components/AccountNumberField.vue'

it('saves a weight without waiting for blur and validates the range', async () => {
  vi.useFakeTimers()
  const save=vi.fn().mockResolvedValue(undefined)
  const wrapper=mount(AccountNumberField,{props:{value:1,label:'权重',save}})
  const input=wrapper.get('input')
  ;(input.element as HTMLInputElement).value='73'
  await input.trigger('input')
  expect(save).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(500)
  expect(save).toHaveBeenCalledWith(73)
  expect(wrapper.text()).toContain('已保存')
  await input.setValue('101')
  await vi.advanceTimersByTimeAsync(500)
  expect(save).toHaveBeenCalledTimes(1)
  expect(wrapper.text()).toContain('1–100')
  wrapper.unmount();vi.useRealTimers()
})

it('does not lose the last edit while a save is in progress', async () => {
  let finish!:()=>void
  const save=vi.fn().mockImplementationOnce(()=>new Promise<void>(resolve=>finish=resolve)).mockResolvedValue(undefined)
  const wrapper=mount(AccountNumberField,{props:{value:1,label:'权重',save}})
  await wrapper.get('input').setValue('2')
  await wrapper.get('input').setValue('3')
  finish();await flushPromises()
  expect(save.mock.calls.map(call=>call[0])).toEqual([2,3])
  expect(wrapper.text()).toContain('已保存');wrapper.unmount()
})
