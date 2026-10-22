export type KnowledgeBase = { id: string; name: string; versionNumber: number; publicationRevision: number }
export type Conversation = { id: string; title: string; knowledgeBaseId: string | null; createdAt: string; updatedAt: string; activeRunId?: string | null; completedRunId?: string | null; unread?: boolean }
export type Citation = {
  label: number; queryId: string; citationId: string; title: string; fileName: string
  pageStart: number | null; pageEnd: number | null; passage: string
  retrievalScore: number | null; rerankScore: number | null; retrievalMode: string
}
export type RetrievalInfo = {
  errorCode?: string
  queryId: string; durationMs: number; mode?: string; embeddingModel?: string | null
  rerankModel?: string | null; stages?: Array<Record<string, unknown>>
}
export type WebSource = { id: string; url: string; title: string; domain: string; engines: string[]; read: boolean }
export type Message = {
  errorCode?: string
  stockArtifacts?: StockArtifact[]
  images?: ChatImage[]
  parentMessageId?: string | null; vote?: number
  id: string; role: 'USER' | 'ASSISTANT'; content: string; status: string; model?: string | null
  citations: Citation[]; retrieval?: RetrievalInfo | null; createdAt?: string; statusText?: string
  reasoningEnabled?: boolean | null
  reasoningContent?: string
  processEvents?: Array<{ stage: string; code?: string; sources?: WebSource[]; elapsedMsTotal?: number; atMs?: number; candidateCount?: number; elapsedMs?: number; enabled?: boolean; status?: string; channelCounts?: Record<string, number>; tool?: string; operationId?: string; parentOperationId?: string; resultCount?: number; content?: string }>
}

export type StockRow = Record<string, string | number | null>
export type StockAnnotation = { date: string; endDate?: string | null; field: string; value: number; label: string; sourceDatasetRef?: string }
export type StockChartData = { kind: 'candlestick' | 'volume' | 'line' | 'histogram'; title: string; unit: string; xField?: string; fields?: string[]; rows: StockRow[] }
export type StockArtifact = {
  version: string; datasetRef: string; title: string; summary: Record<string, any>
  provenance: { dataAsOf?: string; retrievedAt?: string; adjustment?: string; query?: Record<string, any>; queryHash?: string }
  warnings: string[]; preview?: StockRow[]; table?: StockRow[]; rowCount: number
  charts: Array<Pick<StockChartData, 'kind' | 'title'> & Partial<StockChartData>>
  annotations?: StockAnnotation[]; schema?: Record<string, string>
}
export type ChatImage = {id:string;name:string;url:string;mediaType:string}
export type EvidencePage = {
  documentVersionId?: string
  queryId: string; citationId: string; title: string; fileName: string; mediaType: string
  pageNumber: number | null; highlightMode: 'EXACT' | 'TEXT_ONLY' | 'PAGE_ONLY'
  regions: Array<{ x: number; y: number; width: number; height: number }>
  matchedText: string; contentUrl: string; documentUrl: string
  packageEvidence?: {
    sourceArtifactKey?: string
    sources?: Array<{
      source_page_index?: number; display_page_number?: number; coordinate_space?: string
      bbox?: number[]; pdf_highlight_verified?: boolean
      layout?: { column_count?: number; reading_order_mode?: string; text_direction?: string }
    }>
  } | null
}
