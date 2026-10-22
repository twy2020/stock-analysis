import type { Message, StockArtifact } from '../../types'

export type AnalysisEntry = { key: string; messageId: string; artifact: StockArtifact; index: number; title: string; label: string; kind: string; groupId: string; round: number }
export type AnalysisGroup = { id: string; title: string; entries: AnalysisEntry[] }
const tasks: Record<string, string> = { query: '数据查询', sql: '数据查询', screen: '条件选股', events: '事件研究', backtest: '策略回测', analyze: '个股分析' }
export function analysisCatalog(messages: Message[]) {
  const groups = new Map<string, AnalysisGroup>()
  const entries: AnalysisEntry[] = []
  let round = 0
  for (const message of messages) {
    if (message.role === 'USER') round++
    for (const artifact of message.stockArtifacts ?? []) {
      // One data set can contain charts for several securities; classify each chart.
      const charts = artifact.charts.length ? artifact.charts : [{ kind: 'table', title: artifact.title }]
      charts.forEach((chart, index) => {
        const codes = artifact.provenance.query?.universe?.codes ?? []
        const code = chart.title.match(/\b\d{6}\b/)?.[0] ?? (codes.length === 1 ? String(codes[0]) : undefined)
        const task = artifact.provenance.query?.task ?? 'query'
        const groupId = code ? `stock:${code}` : `task:${task}`
        const identity = code ? artifact.charts.find(c => c.kind === 'candlestick' && c.title.includes(code))?.title ?? code : tasks[task] ?? artifact.title
        let group = groups.get(groupId)
        if (!group) { group = { id: groupId, title: identity, entries: [] }; groups.set(groupId, group) }
        else if (code && identity !== code) group.title = identity
        const label = chart.kind === 'candlestick' ? '日线' : chart.kind === 'volume' ? '成交量' : chart.title.replace(/\s*·\s*\d{6}\b/g, '')
        const entry = { key: `${artifact.datasetRef}:${index}`, messageId: message.id, artifact, index, title: chart.title, label, kind: chart.kind, groupId, round: Math.max(1, round) }
        entries.push(entry); group.entries.push(entry)
      })
    }
  }
  return { entries, groups: [...groups.values()] }
}
