import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { useStreamingText } from '../src/components/chat/useStreamingText'
import MarkdownAnswer from '../src/components/chat/MarkdownAnswer'
import { renderMarkdown } from '../src/components/chat/renderMarkdown'
import { useSmoothScroll } from '../src/components/chat/useSmoothScroll'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('paces a burst across frames, catches up after completion, and cancels on unmount', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 16))
  vi.stubGlobal('cancelAnimationFrame', clearTimeout)
  const content = ref('')
  const streaming = ref(true)
  const wrapper = mount(defineComponent({ setup() {
    const displayed = useStreamingText(() => content.value, () => streaming.value)
    return () => h('p', displayed.value)
  } }))
  content.value = '这是逐渐显示的回复。'.repeat(30) + '😀'
  await nextTick()
  await vi.advanceTimersByTimeAsync(48)
  expect(wrapper.text().length).toBeGreaterThan(0)
  expect(wrapper.text().length).toBeLessThan(content.value.length)
  streaming.value = false
  await nextTick()
  await vi.advanceTimersByTimeAsync(260)
  expect(wrapper.text()).toBe(content.value)
  streaming.value = true
  content.value += '更多内容'.repeat(30)
  await nextTick()
  wrapper.unmount()
  expect(vi.getTimerCount()).toBe(0)
})

it('uses immediate text for reduced motion and restores corrected final Markdown', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
  const content = ref('')
  const wrapper = mount(defineComponent({ setup() {
    const displayed = useStreamingText(() => content.value, () => true)
    return () => h('p', displayed.value)
  } }))
  content.value = '原始回复'.repeat(100)
  await nextTick()
  expect(wrapper.text()).toBe(content.value)
  content.value = '更正后的回复'
  await nextTick()
  expect(wrapper.text()).toBe(content.value)
})

it('preserves completed Markdown nodes and only creates reveal spans for new text', async () => {
  const wrapper = mount(MarkdownAnswer, { props: { html: renderMarkdown('第一段。\n\n第二段'), animate: true } })
  const first = wrapper.findAll('p')[0].element
  const firstText = wrapper.findAll('.stream-reveal')[0].element
  await wrapper.setProps({ html: renderMarkdown('第一段。\n\n第二段继续生成的文字。\n\n**第三段**') })
  expect(wrapper.findAll('p')[0].element).toBe(first)
  expect(wrapper.findAll('.stream-reveal')[0].element).toBe(firstText)
  expect(wrapper.get('strong').text()).toBe('第三段')
})

it('gives each appended character a new fade without replacing existing characters', async () => {
  const wrapper = mount(MarkdownAnswer, { props: { html: renderMarkdown('股'), animate: true } })
  const first = wrapper.get('.stream-reveal').element
  await wrapper.setProps({ html: renderMarkdown('股票😀') })
  expect(wrapper.findAll('.stream-reveal').map(span => span.text())).toEqual(['股', '票', '😀'])
  expect(wrapper.findAll('.stream-reveal')[0].element).toBe(first)
  wrapper.unmount()
})

it('smoothly follows a moving scroll destination and cancels when the reader interrupts', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 16))
  vi.stubGlobal('cancelAnimationFrame', clearTimeout)
  const el = document.createElement('div')
  let height = 1000
  Object.defineProperties(el, { scrollHeight: { get: () => height }, clientHeight: { value: 400 } })
  let motion!: ReturnType<typeof useSmoothScroll>
  const wrapper = mount(defineComponent({ setup() {
    motion = useSmoothScroll(ref(el))
    return () => h('div')
  } }))
  motion.bottom()
  await vi.advanceTimersByTimeAsync(32)
  expect(el.scrollTop).toBeGreaterThan(0)
  expect(el.scrollTop).toBeLessThan(600)
  height = 1400
  await vi.advanceTimersByTimeAsync(1000)
  expect(el.scrollTop).toBe(1000)
  height = 1800
  motion.bottom()
  await vi.advanceTimersByTimeAsync(32)
  motion.stop()
  const interrupted = el.scrollTop
  await vi.advanceTimersByTimeAsync(200)
  expect(el.scrollTop).toBe(interrupted)
  expect(motion.isMoving()).toBe(false)
  wrapper.unmount()
  expect(vi.getTimerCount()).toBe(0)
})
