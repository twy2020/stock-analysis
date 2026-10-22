import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, streamApi } from '../src/api/client'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('answer stream', () => {
  it('times out a stalled connection and releases the request', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const pending = expect(streamApi('/stream', {}, () => {})).rejects.toMatchObject({ code: 'STREAM_TIMEOUT' })
    await vi.advanceTimersByTimeAsync(90000)
    await pending
    expect(vi.getTimerCount()).toBe(0)
  })
  it('reports an HTML gateway response without exposing a JSON parser error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html><head>gateway</head></html>')))
    await expect(api('/api/v1/knowledge-bases')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
  it.each(['error', 'complete'])('releases a %s event without waiting for EOF', async (name) => {
    const cancel = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
      start(controller) { controller.enqueue(new TextEncoder().encode(`event: ${name}\ndata: {}\n\n`)) }, cancel,
    }), { headers: { 'Content-Type': 'text/event-stream' } })))
    const event = vi.fn()
    await streamApi('/stream', {}, event)
    expect(event).toHaveBeenCalledWith(name, {})
    expect(cancel).toHaveBeenCalled()
  })
  it('parses CRLF events split across network chunks', async () => {
    const chunks = ['event: progress\r\ndata: {"stage":"SEARCH', 'ING"}\r\n\r\nevent: complete\r\ndata: {"content":"ok"}\r\n\r\n']
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
      start(controller) { chunks.forEach(chunk => controller.enqueue(new TextEncoder().encode(chunk))); controller.close() },
    }))))
    const events: string[] = []
    await streamApi('/api/v1/conversations/c1/messages', { content: '问题' }, name => events.push(name))
    expect(events).toEqual(['progress', 'complete'])
  })
  it('rejects a connection that ends without completion or error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      'event: message\ndata: {"assistantMessageId":"a1"}\n\n',
      { headers: { 'Content-Type': 'text/event-stream' } },
    )))
    await expect(streamApi('/api/v1/conversations/c1/messages', { content: '问题' }, () => {}))
      .rejects.toMatchObject({ code: 'STREAM_INTERRUPTED' })
  })
})
