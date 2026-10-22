import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MessageBubble from '../src/components/chat/MessageBubble.vue'

describe('chat evidence', () => {
  it('renders answer Markdown without executing raw HTML or unsafe links', () => {
    const wrapper = mount(MessageBubble, { props: { message: {
      id: 'markdown', role: 'ASSISTANT', status: 'COMPLETED', citations: [],
      content: '## 判断\n\n- **适用**\n\n| 文件 | 页码 |\n| --- | --- |\n| GB150 | 12 |\n\n<script>alert(1)</script> [危险](javascript:alert(1))',
    } } })
    const answer = wrapper.get('.answer-markdown')
    expect(answer.find('h2').text()).toBe('判断')
    expect(answer.find('li strong').text()).toBe('适用')
    expect(answer.find('table').text()).toContain('GB150')
    expect(answer.find('script').exists()).toBe(false)
    expect(answer.html()).not.toContain('href="javascript:')
  })
  it('shows a plain-language progress stage while waiting for the answer', () => {
    const wrapper = mount(MessageBubble, { props: { message: {
      id: 'pending', role: 'ASSISTANT', content: '', status: 'STREAMING',
      statusText: '正在查找相关内容', citations: [],
    } } })
    expect(wrapper.text()).toContain('正在准备')
  })
  it('renders a compact evidence link and opens a source only on click', async () => {
    const citation = { label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 12, pageEnd: 12, passage: '设计压力', retrievalScore: .8, rerankScore: .93, retrievalMode: 'hybrid' }
    const wrapper = mount(MessageBubble, { props: { showDiagnostics: true, message: {
      id: 'm1', role: 'ASSISTANT', content: '设计压力按工况确定 [1]', status: 'COMPLETED',
      citations: [citation], retrieval: { queryId: 'q1', durationMs: 83, mode: 'hybrid',
        embeddingModel: 'bge-m3', rerankModel: 'bge-reranker' },
    } } })
    expect(wrapper.get('.answer-markdown .inline-citation').text()).toBe('1')
    await wrapper.get('.inline-citation').trigger('pointerover')
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain('压力容器规范')
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain('第 12 页')
    await wrapper.get('.answer-markdown').trigger('pointerleave')
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    await wrapper.get('.inline-citation').trigger('focusin')
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain('第 12 页')
    await wrapper.get('.answer-markdown .inline-citation').trigger('click')
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(wrapper.emitted('openEvidence')?.[0]).toEqual([citation])
    expect(wrapper.find('.citation-link').exists()).toBe(false)
    await wrapper.get('.sources-toggle').trigger('click')
    expect(wrapper.text()).toContain('压力容器规范')
    expect(wrapper.text()).toContain('第 12 页')
    expect(wrapper.text()).toContain('bge-reranker')
    await wrapper.get('.citation-link').trigger('pointerdown')
    expect(wrapper.emitted('openEvidence')).toHaveLength(1)
    await wrapper.get('.citation-link').trigger('click')
    expect(wrapper.emitted('openEvidence')).toHaveLength(2)
  })

  it('shows only the current activity above the streaming Markdown', () => {
    const wrapper = mount(MessageBubble, { props: { message: {
      id: 'live', role: 'ASSISTANT', content: '遵循**第一个连接界面**规则', status: 'STREAMING',
      citations: [], statusText: '正在回复',
      reasoningEnabled: true,
    } } })
    expect(wrapper.get('.answer-markdown strong').text()).toBe('第一个连接界面')
    expect(wrapper.findAll('[role="status"]')).toHaveLength(1)
    expect(wrapper.find('ol').exists()).toBe(false)
    expect(wrapper.get('.message-content').element.firstElementChild?.classList.contains('work-process')).toBe(true)
    expect(wrapper.text()).toContain('正在撰写回复')
  })

  it('keeps low-ranked evidence collapsed and opens a complete result list', async () => {
    const citations = Array.from({ length: 5 }, (_, index) => ({
      label: index + 1, queryId: 'q1', citationId: `c${index + 1}`, title: `规范 ${index + 1}`,
      fileName: 'GB150.pdf', pageStart: 10 + index, pageEnd: 10 + index,
      passage: `第 ${index + 1} 条完整召回内容`, retrievalScore: .8 - index * .05,
      rerankScore: .93 - index * .04, retrievalMode: index % 2 ? 'keyword' : 'hybrid',
    }))
    const wrapper = mount(MessageBubble, { props: { message: {
      id: 'm2', role: 'ASSISTANT', content: '回答 [1]', status: 'COMPLETED', citations,
      retrieval: { queryId: 'q1', durationMs: 83, mode: 'hybrid' },
    } } })

    expect(wrapper.findAll('.citation-list .citation-link')).toHaveLength(0)
    await wrapper.get('.sources-toggle').trigger('click')
    expect(wrapper.findAll('.citation-list .citation-link')).toHaveLength(3)
    await wrapper.get('.show-all-results').trigger('click')
    expect(wrapper.get('[aria-label="全部检索结果"]').text()).toContain('第 5 条完整召回内容')
    expect(wrapper.findAll('.retrieval-result-row')).toHaveLength(5)
    await wrapper.findAll('.retrieval-result-row')[4].trigger('click')
    expect(wrapper.emitted('openEvidence')?.[0]).toEqual([citations[4]])
    expect(wrapper.find('[aria-label="全部检索结果"]').exists()).toBe(false)
  })

  it('hides retrieval diagnostics from ordinary users but keeps sources and thinking', async () => {
    const wrapper = mount(MessageBubble, { props: { message: {
      id: 'private', role: 'ASSISTANT', content: '回答 [1]', status: 'COMPLETED',
      citations: [{ label: 1, queryId: 'q', citationId: 'c', title: '规范', fileName: 'file.pdf', pageStart: 1, pageEnd: 1, passage: '原文', retrievalMode: 'hybrid', retrievalScore: .8, rerankScore: .9 }],
      reasoningContent: '先核对适用范围', processEvents: [{stage:'RERANK', candidateCount:20}],
      retrieval: { queryId: 'q', durationMs: 80, mode: 'hybrid', embeddingModel: 'private-model' },
    } } })
    expect(wrapper.find('.retrieval-meta').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('检索过程')
    await wrapper.get('.work-summary').trigger('click')
    expect(wrapper.text()).toContain('先核对适用范围')
    expect(wrapper.find('.work-row').exists()).toBe(false)
    expect(wrapper.find('.inline-citation').exists()).toBe(true)
  })
})
