import { onBeforeUnmount, type Ref } from 'vue'

/** Keep one animation alive while the stream moves its destination. */
export function useSmoothScroll(element: Ref<HTMLElement | null>) {
  let frame = 0
  let previousTime = 0
  let moving = false
  const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
  function stop() {
    cancelAnimationFrame(frame)
    frame = 0
    moving = false
    previousTime = 0
  }
  function paint(time: number) {
    frame = 0
    const el = element.value
    if (!el) { stop(); return }
    const destination = Math.max(0, el.scrollHeight - el.clientHeight)
    const distance = destination - el.scrollTop
    const elapsed = previousTime ? Math.min(64, time - previousTime) : 16
    previousTime = time
    if (Math.abs(distance) < 1 || reduced()) {
      el.scrollTop = destination
      // Scroll events are delivered after this frame's DOM write.
      frame = requestAnimationFrame(nextTime => {
        frame = 0
        if (element.value && Math.abs(element.value.scrollHeight - element.value.clientHeight - element.value.scrollTop) >= 1) paint(nextTime)
        else { moving = false; previousTime = 0 }
      })
      return
    }
    const step = Math.max(1, Math.abs(distance) * (1 - Math.exp(-elapsed / 95)))
    el.scrollTop += Math.sign(distance) * Math.min(Math.abs(distance), step)
    frame = requestAnimationFrame(paint)
  }
  function bottom() {
    if (!element.value || frame) return
    moving = true
    frame = requestAnimationFrame(paint)
  }
  onBeforeUnmount(stop)
  return { bottom, stop, isMoving: () => moving }
}
