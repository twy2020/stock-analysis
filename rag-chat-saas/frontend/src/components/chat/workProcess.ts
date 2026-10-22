import type { Message } from '../../types'
import { progressLabel } from './progress'

export type ProcessEvent = NonNullable<Message['processEvents']>[number]
export type WorkRow = { key: number; label: string; sources?: ProcessEvent['sources']; elapsedMs?: number; running: boolean; failed: boolean; note: boolean; stage: string }

export function workRows(events: ProcessEvent[], streaming: boolean, now: number, diagnostics: boolean): WorkRow[] {
  const rows: WorkRow[] = []
  events.forEach((item, index) => {
    if (item.stage === 'PROCESS_COMPLETED' || item.stage === 'QUEUED') return
    // A tool's completion updates its own row, including when retrieval emitted substeps.
    if (item.operationId && /TOOL_(COMPLETED|FAILED)/.test(item.stage)
      && events.slice(0, index).some(e => e.operationId === item.operationId)) return
    const end = item.operationId ? events.slice(index + 1).find(e => e.operationId === item.operationId && /TOOL_(COMPLETED|FAILED)/.test(e.stage)) : undefined
    const next = events[index + 1]
    const interrupted = !end && next?.stage === 'PROCESS_FAILED'
    const running = streaming && !end && (item.operationId ? item.status === 'RUNNING' : !next)
    const display = end ?? item
    const note = item.stage === 'MODEL_NOTE'
    let label = note ? (item.content ?? '').replace(/\r\n?/g, '\n').trim().replace(/\n[\t ]*\n(?:[\t ]*\n)+/g, '\n\n') : progressLabel(display)
    if (note && !label) return
    if (!diagnostics && !note) {
      if (item.parentOperationId || ['EMBEDDING_RUNNING', 'QUERY_EMBEDDING_RUNNING', 'RERANK_RUNNING', 'RETRIEVE_FUSED', 'RERANK', 'CONTEXT', 'CHECKING'].includes(item.stage)) return
      if (['SEARCHING', 'DOCUMENTS_LISTING'].includes(item.stage)) label = end ? (end.status === 'FAILED' ? '未能查阅资料' : '已查阅资料') : '正在查阅资料'
      if (item.stage === 'TOOL_PREPARING') label = '正在准备下一步'
    }
    if (interrupted && !note) label = label.replace(/^正在/, '') + '未完成'
    else if (!running && !end && !note && !display.status?.includes('FAILED')) label = label.replace(/^正在/, '已')
    const elapsedMs = end?.elapsedMs ?? (running && item.atMs ? Math.max(0, now - item.atMs) : item.elapsedMs ?? (next && item.elapsedMsTotal != null && next.elapsedMsTotal != null
      ? Math.max(0, next.elapsedMsTotal - item.elapsedMsTotal)
      : undefined))
    rows.push({ key: index, label, sources: display.sources, elapsedMs, running, failed: interrupted || display.status === 'FAILED' || display.stage === 'TOOL_FAILED', note, stage: item.stage })
  })
  return rows
}

export function duration(ms?: number): string {
  if (ms == null) return ''
  return ms < 60000 ? `${(ms / 1000).toFixed(1)} 秒` : `${Math.floor(ms / 60000)} 分 ${Math.floor(ms % 60000 / 1000)} 秒`
}
