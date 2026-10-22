import { expect, it } from 'vitest'
import { analysisCatalog } from '../src/components/stock/analysisCatalog'
import type { Message, StockArtifact } from '../src/types'

it('groups multi-stock charts by security and keeps non-chart queries as data entries', () => {
  const artifact = { version: '1', summary: {}, warnings: [], rowCount: 0, datasetRef: 'ds_a', title: '个股分析', provenance: { query: { task: 'analyze', universe: { codes: ['000001', '002415'] } } }, charts: [
    { kind: 'candlestick', title: '平安银行 · 000001' }, { kind: 'volume', title: '成交量 · 000001' },
    { kind: 'candlestick', title: '海康威视 · 002415' }, { kind: 'volume', title: '成交量 · 002415' },
  ] } as StockArtifact
  const query = { datasetRef: 'ds_b', title: '只读查询结果', provenance: { query: { task: 'query' } }, charts: [] } as unknown as StockArtifact
  const messages = [{ role: 'USER' }, { id: 'm1', role: 'ASSISTANT', stockArtifacts: [artifact, query] }] as Message[]
  const catalog = analysisCatalog(messages)
  expect(catalog.groups.map(group => group.title)).toEqual(['平安银行 · 000001', '海康威视 · 002415', '数据查询'])
  expect(catalog.groups[0].entries.map(e => e.label)).toEqual(['日线', '成交量'])
  expect(catalog.groups[1].entries.map(e => e.index)).toEqual([2, 3])
  expect(catalog.groups[2].entries[0].kind).toBe('table')
})
