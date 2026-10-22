type TextItem = { str: string; transform: number[]; width: number; height: number }
type Viewport = { width: number; height: number; scale: number; convertToViewportPoint: (x: number, y: number) => number[] }
export type HighlightRegion = { x: number; y: number; width: number; height: number }

const normalize = (value: string) => value.normalize('NFKC').replace(/\s+/g, '').toLocaleLowerCase()

export function locatePdfText(items: TextItem[], viewport: Viewport, passage: string): HighlightRegion[] {
  const needle = normalize(passage)
  if (needle.length < 12 || viewport.width <= 0 || viewport.height <= 0) return []

  let offset = 0
  const entries = items.map(item => {
    const text = normalize(item.str)
    const entry = { item, start: offset, end: offset + text.length, length: text.length, text }
    offset = entry.end
    return entry
  }).filter(entry => entry.length > 0)
  const pageText = entries.map(entry => entry.text).join('')

  let matchStart = -1
  let matchLength = 0
  for (const size of [needle.length, 48, 32, 24, 16]) {
    const length = Math.min(size, needle.length)
    for (let start = 0; start <= needle.length - length; start += 8) {
      const segment = needle.slice(start, start + length)
      const found = pageText.indexOf(segment)
      if (found >= 0 && pageText.indexOf(segment, found + 1) < 0) {
        matchStart = found
        matchLength = length
        break
      }
    }
    if (matchStart >= 0) break
  }
  if (matchStart < 0) return []

  const matchEnd = matchStart + matchLength
  return entries.filter(entry => entry.start < matchEnd && entry.end > matchStart).map(entry => {
    const from = Math.max(0, matchStart - entry.start) / entry.length
    const to = Math.min(entry.length, matchEnd - entry.start) / entry.length
    const [originX, baselineY] = viewport.convertToViewportPoint(entry.item.transform[4], entry.item.transform[5])
    const itemWidth = Math.abs(entry.item.width * viewport.scale)
    const height = Math.max(8, Math.abs(entry.item.height * viewport.scale))
    return {
      x: (originX + itemWidth * from) / viewport.width,
      y: (baselineY - height) / viewport.height,
      width: itemWidth * (to - from) / viewport.width,
      height: height / viewport.height,
    }
  }).filter(region => region.width > 0)
}
