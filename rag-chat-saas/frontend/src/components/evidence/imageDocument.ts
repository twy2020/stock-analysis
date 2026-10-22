import { api } from '../../api/client'

type PageMetadata = {
  rotation: number; view: number[]; pageWidth: number; pageHeight: number;
  textItems: { str: string; transform: number[]; width: number; height: number }[];
}

/** Page images stay in a bounded decoded cache; zooming never requests the PDF. */
export async function imageDocument(baseUrl: string, signal?: AbortSignal) {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) cancel()
  let manifest: { pageCount: number }
  try { manifest = await ready<{ pageCount: number }>(baseUrl, controller.signal) }
  catch (cause) { signal?.removeEventListener('abort', cancel); throw cause }
  if (!Number.isInteger(manifest.pageCount) || manifest.pageCount < 1) throw new Error('文档页数无效')
  const pages = new Map<number, Promise<any>>()
  return {
    numPages: manifest.pageCount,
    destroy() { controller.abort(); signal?.removeEventListener('abort', cancel); pages.clear() },
    getPage(number: number) {
      if (number < 1 || number > manifest.pageCount) return Promise.reject(new Error('页码超出范围'))
      if (!pages.has(number)) {
        if (pages.size >= 4) pages.delete(pages.keys().next().value!)
        const request = (async () => {
          const meta = await ready<PageMetadata>(`${baseUrl}/${number}`, controller.signal)
          const image = new Image()
          image.src = `${baseUrl}/${number}/image`
          let timer: ReturnType<typeof setTimeout> | undefined
          try {
            await Promise.race([
              image.decode(),
              new Promise<never>((_, reject) => {
                timer = setTimeout(() => {
                  image.src = ''
                  reject(new Error('页面图片加载超时，请重试'))
                }, 30000)
              }),
            ])
          } finally { clearTimeout(timer) }
          const width = image.naturalWidth, height = image.naturalHeight
          return {
            rotate: meta.rotation, view: meta.view,
            getTextContent: async () => ({ items: meta.rotation ? [] : meta.textItems }),
            getViewport: ({ scale }: { scale: number }) => ({
              width: width * scale, height: height * scale, scale: width / meta.pageWidth * scale,
              convertToViewportPoint: (x: number, y: number) => [x / meta.pageWidth * width * scale, (1 - y / meta.pageHeight) * height * scale],
            }),
            render: ({ canvasContext, viewport }: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }) => {
              canvasContext.drawImage(image, 0, 0, viewport.width, viewport.height)
              return { promise: Promise.resolve(), cancel() {} }
            },
          }
        })()
        pages.set(number, request)
        void request.catch(() => pages.delete(number))
      }
      return pages.get(number)!
    },
  }
}

async function ready<T>(url: string, signal?: AbortSignal): Promise<T> {
  const deadline = Date.now() + 60000
  while (Date.now() < deadline) {
    signal?.throwIfAborted()
    const controller = new AbortController()
    const cancel = () => controller.abort()
    signal?.addEventListener('abort', cancel, { once: true })
    const timer = setTimeout(() => controller.abort(), Math.min(30000, deadline - Date.now()))
    let value: T & { status?: string }
    try { value = await api<T & { status?: string }>(url, { signal: controller.signal }) }
    catch (cause) {
      signal?.throwIfAborted()
      if (Date.now() >= deadline) break
      throw cause
    }
    finally { clearTimeout(timer); signal?.removeEventListener('abort', cancel) }
    if (value.status !== 'PREPARING') return value
    if (Date.now() >= deadline) break
    await new Promise<void>((resolve, reject) => {
      const cancel = () => { clearTimeout(timer); reject(new DOMException('已取消加载', 'AbortError')) }
      const timer = setTimeout(() => { signal?.removeEventListener('abort', cancel); resolve() }, Math.min(1000, deadline - Date.now()))
      signal?.addEventListener('abort', cancel, { once: true })
      if (signal?.aborted) cancel()
    })
  }
  throw new Error('页面仍在后台生成，请稍后重新打开')
}
