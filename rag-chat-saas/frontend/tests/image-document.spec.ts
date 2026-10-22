import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { imageDocument } from '../src/components/evidence/imageDocument'
import { locatePdfText } from '../src/components/evidence/pdfTextHighlights'
const { api, decode } = vi.hoisted(() => ({ api: vi.fn(), decode: vi.fn(async () => {}) }))
vi.mock('../src/api/client', () => ({ api }))
afterEach(() => vi.useRealTimers())

it('caps total preparation time even when every response is slow', async () => {
  vi.useFakeTimers()
  api.mockImplementation((_url: string, options: RequestInit) => new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve({ status: 'PREPARING' }), 20000)
    options.signal!.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('aborted', 'AbortError')) })
  }))
  const pending = expect(imageDocument('/pages')).rejects.toThrow('页面仍在后台生成')
  await vi.advanceTimersByTimeAsync(60000)
  await pending
})

it('cancels preparation when the reader switches documents', async () => {
  vi.useFakeTimers()
  const controller = new AbortController()
  api.mockResolvedValue({ status: 'PREPARING' })
  const pending = expect(imageDocument('/pages', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  await vi.advanceTimersByTimeAsync(0)
  controller.abort()
  await pending
  expect(vi.getTimerCount()).toBe(0)
})
beforeEach(() => {
  decode.mockClear(); api.mockReset()
  vi.stubGlobal('Image', class { src = ''; naturalWidth = 1200; naturalHeight = 1600; decode = decode })
  api.mockImplementation(async (path: string) => path.endsWith('/pages') ? { pageCount: 8 } : {
    rotation: 0, view: [0,0,600,800], pageWidth: 600, pageHeight: 800,
    textItems: [{ str: 'pressure vessel requirements', transform: [1,0,0,1,40,700], width: 180, height: 15 }],
  })
})
it('loads page images once, reuses decoded pages for zoom and preserves highlight coordinates', async () => {
  const doc = await imageDocument('/pages')
  const page = await doc.getPage(2)
  expect(await doc.getPage(2)).toBe(page)
  expect(decode).toHaveBeenCalledTimes(1)
  expect(api.mock.calls.map(call => call[0])).toEqual(['/pages','/pages/2'])
  const viewport = page.getViewport({ scale: .5 })
  const regions = locatePdfText((await page.getTextContent()).items,viewport,'pressure vessel requirements')
  expect(regions[0].x).toBeCloseTo(40/600)
  expect(regions[0].y).toBeCloseTo(85/800)
  await expect(doc.getPage(9)).rejects.toThrow('页码超出范围')
})
it('bounds decoded cache and retries failed image loads', async () => {
  const doc = await imageDocument('/pages')
  decode.mockRejectedValueOnce(new Error('network'))
  await expect(doc.getPage(1)).rejects.toThrow('network')
  await doc.getPage(1)
  for (let page=2;page<=5;page++) await doc.getPage(page)
  await doc.getPage(1)
  expect(decode).toHaveBeenCalledTimes(7)
})
it('waits for background generation instead of falling back to downloading a PDF', async () => {
  vi.useFakeTimers()
  api.mockResolvedValueOnce({ status: 'PREPARING' })
  const pending = imageDocument('/pages')
  await vi.advanceTimersByTimeAsync(1000)
  expect((await pending).numPages).toBe(8)
  expect(api.mock.calls.map(call => call[0])).toEqual(['/pages','/pages'])
})

it('ends a stalled image decode and permits retrying the same page', async () => {
  vi.useFakeTimers()
  decode.mockImplementationOnce(() => new Promise(() => {}))
  const doc = await imageDocument('/pages')
  const pending = expect(doc.getPage(1)).rejects.toThrow('页面图片加载超时')
  await vi.advanceTimersByTimeAsync(30000)
  await pending
  await expect(doc.getPage(1)).resolves.toBeDefined()
})

it('aborts a stalled metadata request', async () => {
  vi.useFakeTimers()
  api.mockImplementationOnce((_url: string, options: RequestInit) => new Promise((_, reject) => {
    options.signal!.addEventListener('abort', () => reject(new Error('aborted')))
  }))
  const pending = expect(imageDocument('/pages')).rejects.toThrow('aborted')
  await vi.advanceTimersByTimeAsync(30000)
  await pending
})
