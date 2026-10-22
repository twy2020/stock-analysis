import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import StockPlot from '../src/components/stock/StockPlot.vue'
import { theme } from '../src/theme'

const plot = vi.hoisted(() => ({ setOption: vi.fn(), getOption: vi.fn(), dispatchAction: vi.fn(), getDataURL: vi.fn(), on: vi.fn(), resize: vi.fn(), dispose: vi.fn() }))
vi.mock('echarts/core', () => ({ init: () => plot, use: vi.fn() }))
afterEach(() => { theme.value = 'light'; vi.unstubAllGlobals(); vi.clearAllMocks() })
it('updates chart colors with the global theme, preserves zoom and exports the matching background', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  theme.value = 'light'
  plot.getOption.mockReturnValue({ dataZoom: [{ start: 25, end: 75 }] })
  const wrapper = mount(StockPlot, { props: { chart: { kind: 'line', title: '日线', unit: 'CNY', fields: ['close'], rows: [{ date: '2026-09-30', close: 12 }] } } })
  expect(plot.setOption.mock.calls.at(-1)?.[0].xAxis.axisLabel.color).toBe('#77818c')
  theme.value = 'dark'
  await nextTick()
  expect(plot.setOption.mock.calls.at(-1)?.[0].xAxis.axisLabel.color).toBe('#a8b6bd')
  expect(plot.dispatchAction).toHaveBeenCalledWith({ type: 'dataZoom', dataZoomIndex: 0, start: 25, end: 75 })
  wrapper.vm.exportImage()
  expect(plot.getDataURL).toHaveBeenLastCalledWith({ type: 'png', pixelRatio: 2, backgroundColor: '#202328' })
  wrapper.unmount()
})
