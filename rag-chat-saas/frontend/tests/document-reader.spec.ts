import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))

const render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }))
let onResize: (() => void) | undefined
const viewport = ({ scale }: { scale: number }) => ({
  width: 600 * scale, height: 800 * scale, scale,
  convertToViewportPoint: (x: number, y: number) => [x * scale, (800 - y) * scale],
})
const textContent = async () => ({ items: [{
  str: '钢制容器不大于35MPa', transform: [1, 0, 0, 1, 40, 700], width: 180, height: 15,
}] })
const getPage = vi.fn(async (_page?: number) => ({
  getViewport: viewport,
  getTextContent: textContent,
  render,
}))

vi.mock('../src/api/client', () => ({
  api,
}))

vi.mock('../src/components/evidence/imageDocument', () => ({
  imageDocument: vi.fn(async () => ({
    numPages: 464, getPage, destroy: vi.fn(),
  })),
}))

import DocumentReader from '../src/components/evidence/DocumentReader.vue'
import { imageDocument as getDocument } from '../src/components/evidence/imageDocument'

describe('document reader', () => {
  afterEach(() => { vi.useRealTimers() })
  beforeEach(() => {
    vi.stubGlobal('devicePixelRatio', 1)
    onResize = undefined
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { onResize = callback }
      observe() {}
      disconnect() {}
    })
    api.mockReset()
    api.mockResolvedValue({
      title: '压力容器规范', fileName: 'GB150.pdf', mediaType: 'application/pdf',
      pageNumber: 9, documentUrl: '/api/v1/evidence/q1/c1/document',
      matchedText: '钢制容器不大于35MPa', highlightMode: 'TEXT_ONLY', regions: [],
    })
    render.mockClear()
    getPage.mockReset()
    getPage.mockImplementation(async () => ({ getViewport: viewport, getTextContent: textContent, render }))
    vi.mocked(getDocument).mockClear()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new Uint8Array([37, 80, 68, 70]), {
      status: 206,
      headers: { 'Content-Range': 'bytes 0-3/45562792' },
    })))
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)
  })

  it('mounts the canvas before rendering the cited page', async () => {
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })

    await flushPromises()

    expect(wrapper.find('canvas').exists()).toBe(true)
    expect(wrapper.text()).toContain('第 9 / 464 页')
    expect(getPage).toHaveBeenCalledWith(9)
    expect(render).toHaveBeenCalledOnce()
    expect(getDocument).toHaveBeenCalledWith('/api/v1/evidence/q1/c1/pages', expect.any(AbortSignal))
  })

  it('hides the empty canvas while the first page image loads', async () => {
    let finish!: (page: any) => void
    getPage.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q', citationId: 'c', title: '规范', fileName: 'file.pdf',
      pageStart: 9, pageEnd: 9, passage: '', retrievalScore: .8, rerankScore: .9, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.get('.pdf-page').attributes('style')).toContain('visibility: hidden')
    expect(wrapper.get('.reader-page-loading').text()).toBe('正在加载页面')
    finish({ getViewport: viewport, getTextContent: textContent, render })
    await flushPromises()
    expect(wrapper.get('.pdf-page').attributes('style')).toContain('visibility: visible')
    expect(wrapper.find('.reader-page-loading').exists()).toBe(false)
    wrapper.unmount()
  })

  it('ends loading and offers retry when page preparation throws synchronously', async () => {
    getPage.mockResolvedValueOnce({ getViewport() { throw new Error('页面尺寸无效') }, getTextContent: textContent, render })
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q', citationId: 'c', title: '规范', fileName: 'file.pdf',
      pageStart: 9, pageEnd: 9, passage: '', retrievalScore: .8, rerankScore: .9, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('页面尺寸无效')
    expect(wrapper.get('.reader-body').attributes('aria-busy')).toBe('false')
    await wrapper.get('.reader-retry').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('.pdf-page').attributes('style')).toContain('visibility: visible')
  })

  it('refits the PDF when the reader grows and lets the user zoom', async () => {
    let width = 360
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.get('canvas').element.width).toBe(328)

    width = 900
    onResize?.()
    await new Promise(resolve => setTimeout(resolve, 120))
    await flushPromises()
    expect(wrapper.get('canvas').element.width).toBe(868)

    await wrapper.get('[aria-label="放大原文"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('canvas').element.width).toBeGreaterThan(868)
  })

  it('fits a portrait page to the available reader height', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(900)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.get('canvas').element.height).toBeLessThanOrEqual(452)
  })

  it('renders at phone pixel density without enlarging the page or shifting highlights', async () => {
    vi.stubGlobal('devicePixelRatio', 3)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(390)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(700)
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '规范', fileName: 'file.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    const element = wrapper.get('canvas').element
    expect(element.width).toBe(1074)
    expect(parseFloat(element.style.width)).toBeCloseTo(358)
    expect(element.height / parseFloat(element.style.height)).toBeCloseTo(3, 2)
    expect(wrapper.findAll('.evidence-highlight')).toHaveLength(1)
    await wrapper.get('[aria-label="放大原文"]').trigger('click')
    await flushPromises()
    expect(element.width / parseFloat(element.style.width)).toBeCloseTo(3, 2)
    wrapper.unmount()
  })

  it('shows page-level positioning when exact highlight coordinates are unavailable', async () => {
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })

    await flushPromises()

    const location = wrapper.get('[data-testid="text-only-location"]')
    expect(location.attributes('role')).toBe('status')
    expect(location.text()).toContain('已高亮第 9 页')
    expect(wrapper.findAll('.evidence-highlight')).toHaveLength(1)
  })

  it('attempts text highlighting for PAGE_ONLY evidence returned by the RAG service', async () => {
    api.mockResolvedValueOnce({
      title: '压力容器规范', fileName: 'GB150.pdf', mediaType: 'application/pdf',
      pageNumber: 9, documentUrl: '/api/v1/evidence/q1/c1/document',
      matchedText: '钢制容器不大于35MPa', highlightMode: 'PAGE_ONLY', regions: [],
    })
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.get('[data-testid="text-only-location"]').text()).toContain('已高亮')
    expect(wrapper.findAll('.evidence-highlight')).toHaveLength(1)
  })

  it('keeps the matching passage closed by default and preserves manual drawer state', async () => {
    api.mockResolvedValueOnce({
      title: '压力容器规范', fileName: 'GB150.pdf', mediaType: 'application/pdf',
      pageNumber: 9, documentUrl: '/api/v1/evidence/q1/c1/document',
      matchedText: '钢制容器不大于35MPa', highlightMode: 'PAGE_ONLY', regions: [],
    })
    getPage.mockResolvedValue({
      getViewport: viewport, render, getTextContent: async () => ({ items: [] }),
    })
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.get('.reader-page-location').text()).toContain('页内文字未能可靠匹配')
    expect(wrapper.get('.reader-evidence-toggle').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.reader-evidence p').exists()).toBe(false)
    onResize?.()
    await flushPromises()
    expect(wrapper.get('.reader-evidence-toggle').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.reader-evidence p').exists()).toBe(false)
    await wrapper.get('[aria-label="放大原文"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.reader-evidence-toggle').attributes('aria-expanded')).toBe('false')
    await wrapper.get('[title="下一页"]').trigger('click')
    await flushPromises()
    await wrapper.get('[title="上一页"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.reader-evidence-toggle').attributes('aria-expanded')).toBe('false')
    await wrapper.get('.reader-evidence-toggle').trigger('click')
    onResize?.()
    await flushPromises()
    expect(wrapper.get('.reader-evidence-toggle').attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })

  it('does not redraw for drawer toggles and batches wheel zoom', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q', citationId: 'c', title: '规范', fileName: 'GB.pdf', pageStart: 9, pageEnd: 9,
      passage: '钢制容器不大于35MPa', retrievalScore: .8, rerankScore: .9, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    const calls = render.mock.calls.length
    await wrapper.get('.reader-evidence-toggle').trigger('click')
    await wrapper.get('.reader-evidence-toggle').trigger('click')
    await flushPromises()
    expect(render).toHaveBeenCalledTimes(calls)
    await wrapper.get('.pdf-page').trigger('wheel', { deltaY: -80 })
    await wrapper.get('.pdf-page').trigger('wheel', { deltaY: -80 })
    expect(render).toHaveBeenCalledTimes(calls)
    await vi.advanceTimersByTimeAsync(100)
    await flushPromises()
    expect(render).toHaveBeenCalledTimes(calls + 1)
    expect(wrapper.get('.reader-zoom-value').text()).not.toBe('100%')
    wrapper.unmount()
  })

  it('reuses the loaded PDF for another citation in the same document version', async () => {
    api.mockResolvedValue({ title: '规范', mediaType: 'application/pdf', documentVersionId: 'version1',
      pageNumber: 9, documentUrl: '/first', matchedText: '', highlightMode: 'PAGE_ONLY', regions: [] })
    const citation = { label: 1, queryId: 'q', citationId: 'c', title: '规范', fileName: 'GB.pdf', pageStart: 9, pageEnd: 9,
      passage: '', retrievalScore: .8, rerankScore: .9, retrievalMode: 'hybrid' }
    const wrapper = mount(DocumentReader, { props: { citation } })
    await flushPromises()
    api.mockResolvedValue({ title: '规范', mediaType: 'application/pdf', documentVersionId: 'version1',
      pageNumber: 10, documentUrl: '/second', matchedText: '', highlightMode: 'PAGE_ONLY', regions: [] })
    await wrapper.setProps({ citation: { ...citation, citationId: 'other' } })
    await flushPromises()
    expect(getDocument).toHaveBeenCalledTimes(1)
    expect(getPage).toHaveBeenLastCalledWith(10)
    wrapper.unmount()
  })

  it('repaints a remounted canvas when another citation has the same document and page', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(332)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    getPage.mockResolvedValue({ getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 300 * scale }), getTextContent: textContent, render } as any)
    api.mockResolvedValue({ title: '规范', mediaType: 'application/pdf', documentVersionId: 'same', pageNumber: 9,
      documentUrl: '/document', matchedText: '', highlightMode: 'PAGE_ONLY', regions: [] })
    const citation = { label: 1, queryId: 'q', citationId: 'a', title: '规范', fileName: 'a.pdf',
      pageStart: 9, pageEnd: 9, passage: '', retrievalScore: .8, rerankScore: .9, retrievalMode: 'hybrid' }
    const wrapper = mount(DocumentReader, { props: { citation } })
    await flushPromises()
    expect(wrapper.get('canvas').element.width).toBe(300)
    await wrapper.setProps({ citation: { ...citation, citationId: 'b' } })
    await flushPromises()
    expect(render).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.pdf-page').attributes('style')).toContain('visibility: visible')
    wrapper.unmount()
  })

  it('collapses the location notice to an icon, pauses for interaction, and resets for a new citation', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const citation = { label: 1, queryId: 'q1', citationId: 'c1', title: '规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid' }
    const wrapper = mount(DocumentReader, { props: { citation } })
    await flushPromises()
    expect(wrapper.get('.reader-location-icon').attributes('aria-expanded')).toBe('true')
    await vi.advanceTimersByTimeAsync(3200)
    expect(wrapper.get('.reader-page-location').classes()).toContain('collapsed')
    await wrapper.get('.reader-location-icon').trigger('click')
    await wrapper.get('.reader-page-location').trigger('pointerenter')
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.get('.reader-location-icon').attributes('aria-expanded')).toBe('true')
    await wrapper.get('.reader-page-location').trigger('pointerleave')
    await vi.advanceTimersByTimeAsync(3200)
    expect(wrapper.get('.reader-location-icon').attributes('aria-expanded')).toBe('false')
    await wrapper.setProps({ citation: { ...citation, citationId: 'c2' } })
    await flushPromises()
    expect(wrapper.get('.reader-location-icon').attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('scrolls the cited page to a matched passage below the fold', async () => {
    getPage.mockResolvedValue({
      getViewport: viewport, render, getTextContent: async () => ({ items: [{
        str: '钢制容器不大于35MPa', transform: [1, 0, 0, 1, 40, 100], width: 180, height: 15,
      }] }),
    })
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect((wrapper.get('.reader-body').element as HTMLElement).scrollTop).toBeGreaterThan(200)
  })

  it('shows source regions across both cited pages even when PDF text is corrupt', async () => {
    const source = { source_page_index: 424, display_page_number: 425,
      coordinate_space: 'normalized_logical_review_page', pdf_highlight_verified: false,
      bbox: [.117291, .211629, .776905, .415562],
      layout: { column_count: 1, reading_order_mode: 'single_ttb', text_direction: 'horizontal' } }
    api.mockResolvedValueOnce({ title: '压力容器', mediaType: 'application/pdf', pageNumber: 425,
      documentUrl: '/document', matchedText: '焊接工艺评定技术档案应保存至该工艺评定失效为止',
      highlightMode: 'PAGE_ONLY', regions: [], packageEvidence: {
        sourceArtifactKey: 'package-source-pdf', sources: [source,
          { ...source, source_page_index: 425, display_page_number: 426, bbox: [.1, .26, .78, .64] }],
      } })
    getPage.mockResolvedValue({ getViewport: viewport, render, rotate: 0, view: [0, 0, 600, 800],
      getTextContent: async () => ({ items: [{ str: 'º/`#O', transform: [1,0,0,1,40,700], width: 60, height: 12 }] }),
    } as any)
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q', citationId: 'c', title: '压力容器', fileName: 'GB150.pdf',
      pageStart: 425, pageEnd: 426, passage: '焊接工艺', retrievalScore: .8, rerankScore: .9, retrievalMode: 'hybrid',
    } } })
    await flushPromises()
    expect(wrapper.findAll('.source-region-highlight')).toHaveLength(1)
    expect(wrapper.get('.reader-page-location').text()).toContain('已标出来源区域')
    expect(wrapper.get('.reader-evidence-toggle').attributes('aria-expanded')).toBe('false')
    await wrapper.get('[title="下一页"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.source-region-highlight').attributes('style')).toContain('top: 26%')
    await wrapper.get('[aria-label="放大原文"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.source-region-highlight').attributes('style')).toContain('top: 26%')
    await wrapper.get('[title="下一页"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.evidence-highlight').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the latest citation when an older evidence request finishes later', async () => {
    let resolveFirst!: (value: unknown) => void
    const first = new Promise(resolve => { resolveFirst = resolve })
    api.mockImplementation((path: string) => path.includes('/q1/c1/') ? first : Promise.resolve({
      title: '第二份规范', fileName: 'second.txt', mediaType: 'text/plain',
      pageNumber: 3, documentUrl: '/api/v1/evidence/q2/c2/document',
      matchedText: '第二条证据', highlightMode: 'TEXT_ONLY', regions: [],
    }))
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '第一份规范', fileName: 'first.txt',
      pageStart: 1, pageEnd: 1, passage: '第一条证据', retrievalScore: .8,
      rerankScore: .9, retrievalMode: 'hybrid',
    } } })

    await wrapper.setProps({ citation: {
      label: 2, queryId: 'q2', citationId: 'c2', title: '第二份规范', fileName: 'second.txt',
      pageStart: 3, pageEnd: 3, passage: '第二条证据', retrievalScore: .7,
      rerankScore: .85, retrievalMode: 'keyword',
    } })
    await flushPromises()
    expect(wrapper.text()).toContain('第二份规范')

    resolveFirst({
      title: '第一份规范', fileName: 'first.txt', mediaType: 'text/plain',
      pageNumber: 1, documentUrl: '/api/v1/evidence/q1/c1/document',
      matchedText: '第一条证据', highlightMode: 'TEXT_ONLY', regions: [],
    })
    await flushPromises()

    expect(wrapper.text()).toContain('第二份规范')
    expect(wrapper.text()).not.toContain('第一条证据')
  })

  it('does not let a slower previous page overwrite the latest page', async () => {
    const wrapper = mount(DocumentReader, { props: { citation: {
      label: 1, queryId: 'q1', citationId: 'c1', title: '压力容器规范', fileName: 'GB150.pdf',
      pageStart: 9, pageEnd: 9, passage: '钢制容器不大于35MPa', retrievalScore: .8,
      rerankScore: .93, retrievalMode: 'hybrid',
    } } })
    await flushPromises()

    let resolvePage10!: (value: any) => void
    const page10Render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }))
    const page11Render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }))
    getPage.mockImplementation((page?: number) => {
      if (page === 10) return new Promise<any>(resolve => { resolvePage10 = resolve })
      return Promise.resolve({
        getViewport: viewport,
        getTextContent: textContent,
        render: page11Render,
      })
    })

    const next = wrapper.findAll('.reader-toolbar button')[1]
    void next.trigger('click')
    await nextTick()
    expect(wrapper.get('.pdf-page').attributes('style')).toContain('visibility: hidden')
    await next.trigger('click')
    await flushPromises()
    resolvePage10({
      getViewport: viewport,
      getTextContent: textContent,
      render: page10Render,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('第 11 / 464 页')
    expect(page11Render).toHaveBeenCalledOnce()
    expect(page10Render).not.toHaveBeenCalled()
  })
})
