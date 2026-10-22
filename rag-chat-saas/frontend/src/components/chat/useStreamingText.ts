import { onBeforeUnmount, ref, watch } from 'vue'

/** Pace bursty network chunks without delaying the authoritative message in the store. */
export function useStreamingText(content: () => string, streaming: () => boolean) {
  const displayed = ref(content())
  let frame = 0
  let lastPaint = 0
  let changedAt = 0
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
  function cancel() { cancelAnimationFrame(frame); frame = 0 }
  function paint(time: number) {
    frame = 0
    const target = content()
    if (time - lastPaint >= 32) {
      lastPaint = time
      const missing = target.length - displayed.value.length
      let end = time - changedAt >= 240 || missing <= 2 ? target.length
        : displayed.value.length + Math.max(2, Math.ceil(missing / 4))
      // Never expose one half of a UTF-16 surrogate pair.
      if (end < target.length && /[\uD800-\uDBFF]/.test(target[end - 1])) end++
      displayed.value = target.slice(0, end)
    }
    if (displayed.value !== target) frame = requestAnimationFrame(paint)
  }
  watch([content, streaming], ([target], [previous, wasStreaming]) => {
    if (target === displayed.value) return
    if (reduced || (!wasStreaming && !streaming()) || !target.startsWith(displayed.value)) {
      cancel(); displayed.value = target; return
    }
    if (target !== previous) changedAt = performance.now()
    if (!frame) frame = requestAnimationFrame(paint)
  })
  onBeforeUnmount(cancel)
  return displayed
}
