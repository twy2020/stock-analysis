import { computed, defineComponent, h, type VNodeChild } from 'vue'

/** Vue patches sanitized Markdown nodes in place, preserving links and completed blocks. */
export default defineComponent({
  props: { html: { type: String, required: true }, animate: Boolean },
  setup(props) {
    const nodes = computed(() => {
      const template = document.createElement('template')
      template.innerHTML = props.html
      function convert(node: Node, key: string, animate: boolean): VNodeChild {
        if (node.nodeType === Node.TEXT_NODE) {
          const text = node.textContent || ''
          if (!animate || !text.trim()) return text
          const chars = Array.from(text)
          const chunks: VNodeChild[] = []
          for (let i = 0; i < chars.length; i++) {
            chunks.push(h('span', { key: `${key}:${i}`, class: 'stream-reveal' }, chars[i]))
          }
          return chunks
        }
        if (!(node instanceof Element)) return null
        const tag = node.tagName.toLowerCase()
        const attributes = Object.fromEntries(Array.from(node.attributes, attr => [attr.name, attr.value]))
        return h(tag, { ...attributes, key }, Array.from(node.childNodes, (child, index) =>
          convert(child, `${key}.${index}`, animate && !['button', 'code', 'pre'].includes(tag))))
      }
      return Array.from(template.content.childNodes, (node, index) => convert(node, String(index), props.animate))
    })
    return () => h('div', { class: 'answer-markdown' }, nodes.value)
  },
})
