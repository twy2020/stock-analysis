import type { EvidencePage } from '../../types'
import type { HighlightRegion } from './pdfTextHighlights'

/** Package boxes describe source blocks, never verified character-level matches. */
export function packagePageRegions(evidence: EvidencePage, page: number, rotation: number,
  view: number[]): HighlightRegion[] {
  const pointer = evidence.packageEvidence
  if (pointer?.sourceArtifactKey !== 'package-source-pdf' || rotation !== 0
      || view.length !== 4 || view[0] !== 0 || view[1] !== 0) return []
  const seen = new Set<string>()
  return (pointer.sources ?? []).flatMap(source => {
    // Split/reordered review pages need an explicit transform; never guess one.
    if (!Number.isInteger(source.source_page_index) || source.source_page_index! + 1 !== page
        || source.display_page_number !== page
        || source.coordinate_space !== 'normalized_logical_review_page'
        || source.layout?.column_count !== 1 || source.layout?.reading_order_mode !== 'single_ttb'
        || source.layout?.text_direction !== 'horizontal') return []
    const box = source.bbox
    if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite)) return []
    const [x, y, width, height] = box
    if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > 1.001 || y + height > 1.001
        || width * height >= .9) return []
    const key = box.join(',')
    if (seen.has(key)) return []
    seen.add(key)
    return [{ x, y, width: Math.min(width, 1 - x), height: Math.min(height, 1 - y) }]
  })
}
