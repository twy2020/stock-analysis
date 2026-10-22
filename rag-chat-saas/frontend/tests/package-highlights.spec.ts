import { expect, it } from 'vitest'
import { packagePageRegions } from '../src/components/evidence/packageHighlights'
import type { EvidencePage } from '../src/types'

const source = { source_page_index: 424, display_page_number: 425,
  coordinate_space: 'normalized_logical_review_page', pdf_highlight_verified: false,
  bbox: [.117291, .211629, .776905, .415562],
  layout: { column_count: 1, reading_order_mode: 'single_ttb', text_direction: 'horizontal' } }
const evidence = { packageEvidence: { sourceArtifactKey: 'package-source-pdf', sources: [source,
  { ...source, source_page_index: 425, display_page_number: 426, bbox: [.1, .26, .78, .64] }] } } as EvidencePage

it('uses original PDF page indices and xywh boxes for cross-page source regions', () => {
  expect(packagePageRegions(evidence, 425, 0, [0, 0, 595, 842])).toEqual([
    { x: .117291, y: .211629, width: .776905, height: .415562 },
  ])
  expect(packagePageRegions(evidence, 426, 0, [0, 0, 595, 842])).toEqual([
    { x: .1, y: .26, width: .78, height: .64 },
  ])
  expect(packagePageRegions(evidence, 427, 0, [0, 0, 595, 842])).toEqual([])
  expect(source.pdf_highlight_verified).toBe(false)
})

it('rejects unknown transforms, split pages, malformed boxes and whole-page highlights', () => {
  expect(packagePageRegions(evidence, 425, 90, [0, 0, 595, 842])).toEqual([])
  expect(packagePageRegions(evidence, 425, 0, [10, 0, 595, 842])).toEqual([])
  for (const invalid of [
    { ...source, display_page_number: 1 }, { ...source, layout: {} },
    { ...source, bbox: [0, 0, 1, 1] }, { ...source, bbox: [0, 0, NaN, .2] },
    { ...source, bbox: [.9, .1, .5, .2] }, { ...source, coordinate_space: 'unknown' },
  ]) {
    const value = { packageEvidence: { sourceArtifactKey: 'package-source-pdf', sources: [invalid] } } as EvidencePage
    expect(packagePageRegions(value, 425, 0, [0, 0, 595, 842])).toEqual([])
  }
})
