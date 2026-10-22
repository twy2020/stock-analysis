import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeBasePicker from '../src/components/chat/KnowledgeBasePicker.vue'

const options = [
  { id: 'one', name: '压力容器国家标准知识库', versionNumber: 4, publicationRevision: 1 },
  { id: 'two', name: 'RAG 包入库验收库', versionNumber: 6, publicationRevision: 1 },
]

describe('knowledge base picker', () => {
  it('opens a positioned list and selects a knowledge base', async () => {
    const wrapper = mount(KnowledgeBasePicker, { props: { modelValue: 'one', options } })
    await wrapper.get('.kb-trigger').trigger('click')
    expect(wrapper.get('.kb-options').attributes('role')).toBe('listbox')
    expect(wrapper.findAll('.kb-option')).toHaveLength(2)
    await wrapper.findAll('.kb-option')[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['two'])
    expect(wrapper.find('.kb-options').exists()).toBe(false)
  })

  it('supports arrow keys and Escape', async () => {
    const wrapper = mount(KnowledgeBasePicker, { props: { modelValue: 'one', options } })
    await wrapper.get('.kb-trigger').trigger('keydown', { key: 'ArrowDown' })
    await wrapper.get('.kb-trigger').trigger('keydown', { key: 'ArrowDown' })
    await wrapper.get('.kb-trigger').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['two'])
    await wrapper.get('.kb-trigger').trigger('keydown', { key: 'ArrowDown' })
    await wrapper.get('.kb-trigger').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.kb-options').exists()).toBe(false)
  })

  it('keeps the knowledge base fixed for an existing conversation', async () => {
    const wrapper = mount(KnowledgeBasePicker, { props: { modelValue: 'one', options, disabled: true } })
    expect(wrapper.get('.kb-trigger').attributes('disabled')).toBeDefined()
    await wrapper.get('.kb-trigger').trigger('click')
    expect(wrapper.find('.kb-options').exists()).toBe(false)
  })
})
