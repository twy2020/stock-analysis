import type { StockChartData } from '../../types'

const labels: Record<string, string> = {
  code: '股票代码', symbol: '证券标识', name: '股票名称', date: '日期', board: '板块', industry: '行业',
  open: '开盘价', close: '收盘价', high: '最高价', low: '最低价', volume: '成交量', amount: '成交额',
  pct_change: '涨跌幅', change_pct: '涨跌幅', totalReturn: '策略收益', benchmarkReturn: '买入持有收益',
  n: '有效样本', mean: '均值', median: '中位数', std: '标准差', min: '最小值', max: '最大值',
  upProbability: '上涨概率', winRate: '交易胜率', completedTrades: '完整交易', hitCount: '命中次数',
  matchedStocks: '命中股票', scannedStocks: '扫描股票', totalResultRows: '结果行数',
  lastClose: '收盘价', observations: '日线数量', lastDate: '最后交易日', firstDate: '起始交易日',
  annualizedVolatility: '年化波动率', maxPriceDrawdown: '价格最大回撤', priceReturn: '区间价格收益',
  maxDrawdown: '最大回撤', finalEquity: '期末权益', feesPaid: '交易费用', events: '事件样本',
  complete: '窗口完整', validObservations: '有效观测', limitReached: '达到查询上限',
}
export function fieldLabel(field: string) { return labels[field] ?? field }
export function formatValue(value: unknown, field = ''): string {
  if (value == null) return '--'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '--'
    if (/Return|Drawdown|Volatility|Probability|winRate|^return\d+$/.test(field)) return `${(value * 100).toFixed(2)}%`
    return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(value)
  }
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
export function renderableChart(chart: Partial<StockChartData>): chart is StockChartData {
  return ['candlestick', 'volume', 'line', 'histogram'].includes(chart.kind ?? '') && Array.isArray(chart.rows) && chart.rows.length > 0
}
