import { describe, expect, it } from 'vitest'
import { locatePdfText } from '../src/components/evidence/pdfTextHighlights'

const viewport = {
  width: 600, height: 800, scale: 1,
  convertToViewportPoint: (x: number, y: number) => [x, 800 - y],
}

describe('PDF source highlighting', () => {
  it('locates a passage split across adjacent text items', () => {
    const regions = locatePdfText([
      { str: '钢制压力容器的设计压力', transform: [1, 0, 0, 1, 40, 700], width: 150, height: 15 },
      { str: '适用范围不得大于35MPa', transform: [1, 0, 0, 1, 190, 700], width: 180, height: 15 },
    ], viewport, '钢制压力容器的设计压力\n适用范围不得大于35MPa')

    expect(regions).toHaveLength(2)
    expect(regions[0]).toMatchObject({ x: 40 / 600, y: 85 / 800 })
  })

  it('does not highlight an ambiguous repeated fragment', () => {
    const repeated = '本标准适用于钢制压力容器设计压力范围'
    const items = [0, 1].map((index) => ({
      str: repeated, transform: [1, 0, 0, 1, 40, 700 - index * 30], width: 250, height: 15,
    }))

    expect(locatePdfText(items, viewport, repeated)).toEqual([])
  })

  it('does not turn a short coincidental term into a source highlight', () => {
    expect(locatePdfText([
      { str: '设计压力', transform: [1, 0, 0, 1, 40, 700], width: 80, height: 15 },
    ], viewport, '设计压力')).toEqual([])
  })
})
