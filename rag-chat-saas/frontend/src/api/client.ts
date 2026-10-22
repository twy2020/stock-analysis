export type User = {
  username: string
  role: 'ADMIN' | 'USER'
  passwordChangeRequired: boolean
}

class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

let csrfToken = ''
let sessionExpiredHandler: (() => void) | undefined

export function onSessionExpired(handler?: () => void) {
  sessionExpiredHandler = handler
}

function handleUnauthorized(path: string, status: number) {
  if (status !== 401 || /^\/api\/v1\/auth\/(login|register|session)(?:\?|$)/.test(path)) return
  sessionExpiredHandler?.()
}

export function setCsrfToken(value: string) {
  csrfToken = value
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (csrfToken && options.method && options.method !== 'GET') headers.set('X-CSRF-Token', csrfToken)
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) abort()
  const timer = setTimeout(abort, 45000)
  try {
  const response = await fetch(path, { ...options, signal: controller.signal, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ code: 'REQUEST_FAILED', message: '请求失败' }))
    handleUnauthorized(path, response.status)
    throw new ApiError(response.status, body.code ?? 'REQUEST_FAILED', body.message ?? '请求失败')
  }
  if (response.status === 204) return undefined as T
  return await response.json().catch(() => { throw new ApiError(response.status, 'INVALID_RESPONSE', '服务返回了网页而非有效数据，请检查服务或访问地址后重试') }) as T
  } catch (cause) {
    if (controller.signal.aborted && !options.signal?.aborted) throw new ApiError(0, 'REQUEST_TIMEOUT', '请求超时，请重试')
    throw cause
  } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abort) }
}

export async function streamApi(
  path: string,
  body: unknown,
  onEvent: (name: string, payload: Record<string, any>) => void,
  signal?: AbortSignal,
  method: 'POST' | 'GET' = 'POST',
) {
  const controller = new AbortController()
  let timedOut = false
  const expire = () => { timedOut = true; controller.abort() }
  let timer = setTimeout(expire, 90000)
  const deadline = setTimeout(expire, 600000)
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) abort()
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  try {
  const response = await fetch(path, {
    method, credentials: 'same-origin',
    signal: controller.signal,
    headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream', 'X-CSRF-Token': csrfToken },
    body: method === 'GET' ? undefined : JSON.stringify(body),
  })
  if (!response.ok || !response.body) {
    handleUnauthorized(path, response.status)
    throw new ApiError(response.status, response.status === 401 ? 'AUTHENTICATION_REQUIRED' : 'STREAM_FAILED', response.status === 401 ? '登录已过期，请重新登录' : '问答请求失败')
  }
  const mime = response.headers.get('Content-Type')
  if (mime && !mime.includes('text/event-stream')) throw new ApiError(response.status, 'INVALID_RESPONSE', '问答连接返回了无效内容，请重试或检查服务连接')
  reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminal = false
  while (true) {
    const { done, value } = await reader.read()
    clearTimeout(timer)
    timer = setTimeout(expire, 90000)
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    buffer = buffer.replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      let name = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) name = line.slice(6).trim()
        if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (data) {
        let payload: Record<string, any>
        try { payload = JSON.parse(data) } catch { throw new ApiError(0, 'INVALID_EVENT', '回复数据异常，可以重新发送') }
        onEvent(name, payload)
        if (name === 'complete' || name === 'error') { terminal = true; return }
      }
    }
    if (done) break
  }
  if (!terminal) throw new ApiError(0, 'STREAM_INTERRUPTED', '连接已中断，请重新发送')
  } catch (cause) {
    if (timedOut) throw new ApiError(0, 'STREAM_TIMEOUT', '等待回复超时，已结束等待，可以重新提问')
    if (signal?.aborted) throw new ApiError(0, 'CANCELLED', '已停止回复，可以继续提问')
    throw cause
  } finally {
    clearTimeout(timer)
    clearTimeout(deadline)
    signal?.removeEventListener('abort', abort)
    void reader?.cancel().catch(() => {})
    controller.abort()
  }
}

export { ApiError }
