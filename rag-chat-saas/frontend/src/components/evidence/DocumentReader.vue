<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Download, Info, Minus, Plus, X } from 'lucide-vue-next'
import { api } from '../../api/client'
import type { Citation, EvidencePage } from '../../types'
import { locatePdfText, type HighlightRegion } from './pdfTextHighlights'
import { packagePageRegions } from './packageHighlights'
import { imageDocument } from './imageDocument'

const props = defineProps<{ citation: Citation }>()
defineEmits<{ close: [] }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const readerBody = ref<HTMLElement | null>(null)
const zoom = ref(1)
const evidenceExpanded = ref(false)
const locationReady = ref(false)
const noticeExpanded = ref(true)
let noticeTimer: ReturnType<typeof setTimeout> | undefined
let noticeHovered = false
let noticeFocused = false
const textHighlights = ref<HighlightRegion[]>([])
const regionPage = ref(0)
const regionKind = ref<'text' | 'source'>('text')
const pageInfo = ref<EvidencePage | null>(null)
const pageNumber = ref(1)
const pageCount = ref(0)
const loading = ref(true)
const pageLoading = ref(false)
const hasPagePaint = ref(false)
const error = ref('')
let pdf: any = null
let renderTask: any = null
let loadingTask: any = null
let loadGeneration = 0
let evidenceController: AbortController | null = null
let documentController: AbortController | null = null
let renderGeneration = 0
let resizeObserver: ResizeObserver | null = null
let pendingLocation = false
let documentKey = ''
let paintKey = ''
let redrawTimer: ReturnType<typeof setTimeout> | undefined
const textCache = new Map<number, Promise<any>>()

const isPdf = computed(() => pageInfo.value?.mediaType === 'application/pdf')
const isEvidencePage = computed(() => {
  const start = props.citation.pageStart ?? pageInfo.value?.pageNumber ?? 1
  const end = props.citation.pageEnd ?? start
  return (pageNumber.value >= start && pageNumber.value <= end)
    || !!pageInfo.value?.packageEvidence?.sources?.some(source => source.source_page_index! + 1 === pageNumber.value)
})
const activeRegions = computed(() => {
  if (pageNumber.value === pageInfo.value?.pageNumber && pageInfo.value.highlightMode === 'EXACT'
      && pageInfo.value.regions.length) return pageInfo.value.regions
  return regionPage.value === pageNumber.value ? textHighlights.value : []
})

function stopNoticeTimer() { clearTimeout(noticeTimer); noticeTimer = undefined }
function scheduleNoticeCollapse() {
  stopNoticeTimer()
  if (!locationReady.value || !noticeExpanded.value || noticeHovered || noticeFocused) return
  noticeTimer = setTimeout(() => { noticeExpanded.value = false }, 3200)
}
function setNoticeInteraction(kind: 'hover' | 'focus', active: boolean) {
  if (kind === 'hover') noticeHovered = active
  else noticeFocused = active
  scheduleNoticeCollapse()
}
function toggleNotice() {
  noticeExpanded.value = !noticeExpanded.value
  scheduleNoticeCollapse()
}
function toggleEvidence() {
  evidenceExpanded.value = !evidenceExpanded.value
}

function releaseDocument() {
  renderGeneration += 1
  renderTask?.cancel?.()
  renderTask = null
  loadingTask?.destroy?.()
  loadingTask = null
  pdf?.destroy?.()
  pdf = null
  documentKey = ''
  paintKey = ''
  hasPagePaint.value = false
  textCache.clear()
  pageCount.value = 0
}

async function load() {
  const generation = ++loadGeneration
  evidenceController?.abort()
  documentController?.abort()
  const controller = new AbortController()
  evidenceController = controller
  const timeout = setTimeout(() => controller.abort(), 30000)
  renderGeneration += 1
  renderTask?.cancel?.()
  stopNoticeTimer()
  locationReady.value = false
  noticeExpanded.value = true
  noticeHovered = false
  noticeFocused = false
  evidenceExpanded.value = false
  loading.value = true
  pageLoading.value = false
  error.value = ''
  pageInfo.value = null
  hasPagePaint.value = false
  textHighlights.value = []
  // The loading branch unmounts the canvas, even when the document is reused.
  paintKey = ''
  regionPage.value = 0
  regionKind.value = 'text'
  try {
    const evidence = await api<EvidencePage>(`/api/v1/evidence/${props.citation.queryId}/${props.citation.citationId}/page`, { signal: controller.signal })
    clearTimeout(timeout)
    if (generation !== loadGeneration) return
    pageInfo.value = evidence
    pageNumber.value = evidence.pageNumber ?? props.citation.pageStart ?? 1
    zoom.value = 1
    pendingLocation = true
    if (isPdf.value) {
      const nextKey = evidence.documentVersionId || evidence.documentUrl
      if (pdf && documentKey === nextKey) {
        pageCount.value = pdf.numPages
      } else {
      releaseDocument()
      const pendingController = new AbortController()
      documentController = pendingController
      const nextPdf = await imageDocument(`/api/v1/evidence/${props.citation.queryId}/${props.citation.citationId}/pages`, pendingController.signal)
      if (documentController === pendingController) documentController = null
      if (generation !== loadGeneration) { nextPdf.destroy?.(); return }
      loadingTask = null
      pdf = nextPdf
      documentKey = nextKey
      pageCount.value = pdf.numPages
      }
    } else {
      releaseDocument()
    }
  } catch (cause) {
    if (generation !== loadGeneration) return
    loadingTask?.destroy?.()
    loadingTask = null
    error.value = cause instanceof Error && cause.name === 'AbortError' ? '原文加载超时，请重试' : cause instanceof Error ? cause.message : '原文加载失败'
  } finally {
    clearTimeout(timeout)
    if (generation === loadGeneration) loading.value = false
  }
  if (generation === loadGeneration && !error.value && isPdf.value) {
    await nextTick()
    await renderPage()
  }
}

async function renderPage() {
  if (!pdf || !canvas.value) return
  const generation = ++renderGeneration
  renderTask?.cancel?.()
  renderTask = null
  const targetPage = pageNumber.value
  pageLoading.value = true
  let page: any
  let task: any = null
  try {
  page = await pdf.getPage(targetPage)
  if (generation !== renderGeneration || !canvas.value) return
  const available = Math.max(320, readerBody.value?.clientWidth ?? 700)
  const availableHeight = readerBody.value?.clientHeight ?? 0
  const base = page.getViewport({ scale: 1 })
  const widthFit = (available - 32) / base.width
  const heightFit = availableHeight > 80 ? (availableHeight - 48) / base.height : widthFit
  const fit = base.height >= base.width ? Math.min(widthFit, heightFit) : widthFit
  const displayScale = Math.min(4, fit * zoom.value)
  const viewport = page.getViewport({ scale: displayScale })
  // Keep layout/highlight coordinates in CSS pixels, but paint for the display's density.
  // Bound the backing store so zooming a large page does not exhaust mobile memory.
  const density = Math.min(Math.max(1, window.devicePixelRatio || 1), 3,
    Math.sqrt(16000000 / (viewport.width * viewport.height)),
    8192 / Math.max(viewport.width, viewport.height))
  const paintViewport = page.getViewport({ scale: displayScale * density })
  const nextPaintKey = `${documentKey}:${targetPage}:${viewport.width}:${viewport.height}:${density}`
  const buffer = document.createElement('canvas')
  buffer.width = Math.max(1, Math.floor(paintViewport.width))
  buffer.height = Math.max(1, Math.floor(paintViewport.height))
  const mustPaint = nextPaintKey !== paintKey || canvas.value.width !== buffer.width || canvas.value.height !== buffer.height
  task = mustPaint ? page.render({ canvasContext: buffer.getContext('2d')!, viewport: paintViewport }) : null
  renderTask = task
    await task?.promise
    if (generation !== renderGeneration || !canvas.value) return
    if (mustPaint) {
      canvas.value.width = buffer.width
      canvas.value.height = buffer.height
      canvas.value.style.width = `${viewport.width}px`
      canvas.value.style.height = `${viewport.height}px`
      canvas.value.getContext('2d')!.drawImage(buffer, 0, 0)
      paintKey = nextPaintKey
    }
    hasPagePaint.value = true
    if (generation === renderGeneration && pageInfo.value?.matchedText
        && !(pageInfo.value.highlightMode === 'EXACT' && pageInfo.value.regions.length && targetPage === pageInfo.value.pageNumber)
        && isEvidencePage.value) {
      let matched: HighlightRegion[] = []
      try {
        if (!textCache.has(targetPage)) {
          if (textCache.size >= 8) textCache.delete(textCache.keys().next().value!)
          const request = page.getTextContent()
          textCache.set(targetPage, request)
          void request.catch(() => textCache.delete(targetPage))
        }
        const content = await textCache.get(targetPage)
        if (generation === renderGeneration) {
          matched = locatePdfText(content.items, viewport, pageInfo.value.matchedText)
        }
      } catch { /* Scanned or malformed text layers can still have source-block coordinates. */ }
      if (generation === renderGeneration) {
        regionKind.value = matched.length ? 'text' : 'source'
        textHighlights.value = matched.length ? matched : packagePageRegions(pageInfo.value, targetPage, page.rotate ?? 0, page.view ?? [])
        regionPage.value = targetPage
      }
    }
    if (generation === renderGeneration && pendingLocation && targetPage === pageInfo.value?.pageNumber) {
      const region = activeRegions.value[0]
      if (region && readerBody.value && canvas.value) {
        const body = readerBody.value
        body.scrollTop = Math.max(0, canvas.value.getBoundingClientRect().top
          - body.getBoundingClientRect().top + body.scrollTop
          + region.y * viewport.height - body.clientHeight * .25)
      }
      pendingLocation = false
      locationReady.value = true
      scheduleNoticeCollapse()
    }
  } catch (cause: any) {
    if (generation === renderGeneration && cause?.name !== 'RenderingCancelledException') {
      error.value = cause instanceof Error ? cause.message : '原文页面渲染失败，请重试'
    }
  } finally {
    if (generation === renderGeneration) pageLoading.value = false
    if (renderTask === task) renderTask = null
  }
}


async function changePage(delta: number) {
  pageNumber.value = Math.min(pageCount.value, Math.max(1, pageNumber.value + delta))
  hasPagePaint.value = false
  textHighlights.value = []
  locationReady.value = false
  await renderPage()
  if (readerBody.value) readerBody.value.scrollTop = 0
}

function changeZoom(delta: number) {
  zoom.value = Math.min(2.5, Math.max(.5, Math.round((zoom.value + delta) * 100) / 100))
  void renderPage()
}

function wheelZoom(event: WheelEvent) {
  if (!pdf || !event.deltaY) return
  zoom.value = Math.min(2.5, Math.max(.5, Math.round(zoom.value * Math.exp(-Math.max(-120, Math.min(120, event.deltaY)) * .002) * 100) / 100))
  clearTimeout(redrawTimer)
  redrawTimer = setTimeout(() => { void renderPage() }, 80)
}

watch(() => [props.citation.queryId, props.citation.citationId], load, { immediate: true })
onMounted(() => {
  if (readerBody.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (!pdf || !readerBody.value?.clientWidth) return
      clearTimeout(redrawTimer)
      redrawTimer = setTimeout(() => { void renderPage() }, 100)
    })
    resizeObserver.observe(readerBody.value)
  }
})
onBeforeUnmount(() => { evidenceController?.abort(); documentController?.abort(); clearTimeout(redrawTimer); stopNoticeTimer(); resizeObserver?.disconnect(); loadGeneration += 1; releaseDocument() })
</script>

<template>
  <aside class="document-reader" aria-label="原文阅读器">
    <header class="reader-header">
      <div class="reader-title"><strong>{{ pageInfo?.title || citation.title }}</strong><span>{{ pageInfo?.fileName || citation.fileName }}</span></div>
      <a v-if="pageInfo" class="icon-button" :href="pageInfo.documentUrl" download :title="'下载原文'"><Download :size="17" /></a>
      <button class="icon-button" title="关闭阅读器" @click="$emit('close')"><X :size="18" /></button>
    </header>
    <div v-if="pageInfo && isPdf" class="reader-toolbar">
      <div class="reader-page-controls">
        <button class="icon-button" title="上一页" :disabled="pageNumber <= 1" @click="changePage(-1)"><ChevronLeft :size="18" /></button>
        <span>第 {{ pageNumber }} / {{ pageCount }} 页</span>
        <button class="icon-button" title="下一页" :disabled="pageNumber >= pageCount" @click="changePage(1)"><ChevronRight :size="18" /></button>
      </div>
      <div class="reader-zoom-controls">
        <button class="icon-button" aria-label="缩小原文" title="缩小原文" :disabled="zoom <= .5" @click="changeZoom(-.25)"><Minus :size="16" /></button>
        <button class="reader-zoom-value" title="适应页面；在页面上滚轮缩放" @click="zoom = 1; renderPage()">{{ Math.round(zoom * 100) }}%</button>
        <button class="icon-button" aria-label="放大原文" title="放大原文" :disabled="zoom >= 2.5" @click="changeZoom(.25)"><Plus :size="16" /></button>
      </div>
    </div>
    <div ref="readerBody" class="reader-body" :aria-busy="loading || pageLoading">
      <div v-if="locationReady && !error && pageInfo && isEvidencePage && (pageInfo.highlightMode !== 'EXACT' || regionKind === 'source')"
           class="reader-location-overlay">
        <div class="reader-page-location" :class="{ collapsed: !noticeExpanded }" data-testid="text-only-location" role="status"
             @pointerenter="setNoticeInteraction('hover', true)" @pointerleave="setNoticeInteraction('hover', false)"
             @focusin="setNoticeInteraction('focus', true)" @focusout="setNoticeInteraction('focus', false)">
          <button class="reader-location-icon" :aria-expanded="noticeExpanded"
                  :aria-label="`${noticeExpanded ? '收起' : '查看'}定位提示：第 ${pageNumber} 页`" @click="toggleNotice"><Info :size="17" /></button>
          <div class="reader-location-copy" :aria-hidden="!noticeExpanded">
            <strong>{{ activeRegions.length ? (regionKind === 'source' ? '已标出来源区域 · 第' : '已高亮第') : '已定位到第' }} {{ pageNumber }} 页</strong>
            <span v-if="activeRegions.length && regionKind === 'source'">按原文段落或表格区域定位，可能包含相邻文字。</span>
            <span v-else-if="!activeRegions.length">页内文字未能可靠匹配，可在下方展开命中内容。</span>
          </div>
        </div>
      </div>
      <div v-if="loading" class="reader-state" role="status"><span class="reader-loading-spinner" aria-hidden="true"></span>正在加载原文</div>
      <div v-else-if="error" class="reader-state error" role="alert"><span>{{ error }}</span><button class="reader-retry" @click="load">重新加载</button></div>
      <div v-if="!loading && !error && pageLoading" class="reader-page-loading" role="status"><span class="reader-loading-spinner" aria-hidden="true"></span><span>正在加载页面</span></div>
      <div v-if="!loading && !error && isPdf" class="reader-pdf-content">
        <div class="pdf-page" :style="{ visibility: hasPagePaint ? 'visible' : 'hidden' }" @wheel.prevent="wheelZoom">
          <canvas ref="canvas" />
          <template v-if="activeRegions.length">
            <mark v-for="(region, index) in activeRegions"
                  :key="index" class="evidence-highlight" :class="{ 'source-region-highlight': regionKind === 'source' && pageInfo?.highlightMode !== 'EXACT' }"
                  :style="{ left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.width * 100}%`, height: `${region.height * 100}%` }" />
          </template>
        </div>
      </div>
      <iframe v-else-if="!loading && !error && pageInfo" :src="pageInfo.documentUrl" :title="pageInfo.title" />
    </div>
    <footer v-if="pageInfo?.matchedText" class="reader-evidence" :class="{ expanded: evidenceExpanded }">
      <button class="reader-evidence-toggle" :aria-expanded="evidenceExpanded" @click="toggleEvidence">
        <span>命中内容</span><ChevronDown v-if="evidenceExpanded" :size="14" /><ChevronUp v-else :size="14" />
      </button>
      <p v-if="evidenceExpanded">{{ pageInfo.matchedText }}</p>
    </footer>
  </aside>
</template>
