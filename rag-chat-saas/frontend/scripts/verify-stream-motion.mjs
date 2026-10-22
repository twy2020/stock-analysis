import { chromium } from '@playwright/test'
import { createServer } from 'node:http'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const base = process.env.STOCK_VERIFY_URL ?? 'http://127.0.0.1:18110'
const output = path.resolve('../../artifacts/verification')
mkdirSync(output, { recursive: true })
const timers = new Set()
let answerPaused = false
const server = createServer((request, response) => {
  if (request.method === 'OPTIONS') {
    response.writeHead(204, { 'Access-Control-Allow-Origin': base, 'Access-Control-Allow-Headers': 'content-type,x-csrf-token', 'Access-Control-Allow-Methods': 'GET,OPTIONS' })
    response.end()
    return
  }
  response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache',
    'Access-Control-Allow-Origin': base, 'Access-Control-Allow-Credentials': 'true' })
  const send = (event, data) => response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  const schedule = (delay, callback) => {
    const timer = setTimeout(() => { timers.delete(timer); if (!response.destroyed) callback() }, delay)
    timers.add(timer)
  }
  send('progress', { stage: 'MODEL_REASONING' })
  for (let i = 0; i < 10; i++) schedule(100 + i * 100, () => send('reasoning', { content: '先核对行情日期与复权方式，再比较趋势、波动率及事件样本。'.repeat(4) }))
  schedule(1200, () => send('progress', { stage: 'RESPONSE_STREAMING' }))
  const chunk = '行情摘要显示均线趋势向上，波动区间扩大。统计结果需要结合样本量、回撤与交易成本解读，不能把历史表现视为未来收益保证。'.repeat(3) + '\n\n'
  for (let i = 0; i < 60; i++) schedule(1300 + i * 200, () => { if (!answerPaused) send('delta', { content: chunk }) })
  schedule(20000, () => { send('complete', { content: chunk.repeat(60), citations: [] }); response.end() })
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const streamUrl = `http://127.0.0.1:${server.address().port}/events`
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const report = []
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    answerPaused = false
    const context = await browser.newContext({ viewport })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const conversation = { id: 'motion', title: '流式动效验证', knowledgeBaseId: null, activeRunId: 'run', createdAt: '', updatedAt: '' }
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url()).pathname
      if (url.endsWith('/events')) { await route.continue({ url: streamUrl }); return }
      let json = {}
      if (url.endsWith('/auth/session')) json = { user: { username: 'motion-check', role: 'USER', passwordChangeRequired: false }, csrfToken: 'browser-fixture' }
      else if (url.endsWith('/capabilities')) json = { ragAvailable: false, reasoningToggle: true }
      else if (url.endsWith('/knowledge-bases')) json = []
      else if (url.endsWith('/conversations')) json = [conversation]
      else if (url.endsWith('/messages')) json = [
        { id: 'question', role: 'USER', content: '分析趋势和风险', status: 'COMPLETED', citations: [] },
        { id: 'answer', role: 'ASSISTANT', content: '', status: 'STREAMING', citations: [] },
      ]
      else if (url.endsWith('/runs/run')) json = { id: 'run', conversationId: 'motion', assistantMessageId: 'answer', userMessageId: 'question', status: 'RUNNING' }
      else if (url.endsWith('/conversations/motion')) json = conversation
      await route.fulfill({ json })
    })
    await page.goto(base)
    if (viewport.width < 600) await page.getByRole('button', { name: '打开对话导航', exact: true }).click()
    await page.locator('.conversation-open').filter({ hasText: '流式动效验证' }).click()
    await page.locator('.work-reasoning-text').waitFor()
    const reasoningFade = await page.locator('.work-reasoning-text').evaluate(el => getComputedStyle(el).animationName)
    if(await page.locator('.work-process .stream-reveal, .work-process .work-shimmer').count())throw new Error('Process text still animates')
    await page.locator('.answer-markdown').waitFor()
    await page.evaluate(() => {
      window.motionSamples = []
      window.motionSampling = true
      const sample = () => {
        const el = document.querySelector('.message-transcript')
        window.motionSamples.push(el.scrollTop)
        if (window.motionSampling) requestAnimationFrame(sample)
      }
      requestAnimationFrame(sample)
    })
    await page.waitForTimeout(1300)
    const transcript = page.locator('.message-transcript')
    const before = await transcript.evaluate(el => ({ top: el.scrollTop, remaining: el.scrollHeight - el.clientHeight - el.scrollTop }))
    if (before.top < 20) throw new Error('Long answer did not follow the stream')
    const bounds = await transcript.boundingBox()
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)
    const wheelStart = await transcript.evaluate(el => el.scrollTop)
    await page.mouse.wheel(0, -500)
    await page.waitForFunction(top => document.querySelector('.message-transcript').scrollTop < top - 100, wheelStart)
    await page.waitForTimeout(100)
    const paused = await transcript.evaluate(el => el.scrollTop)
    await page.waitForTimeout(600)
    const held = await transcript.evaluate(el => el.scrollTop)
    if (Math.abs(held - paused) > 2) throw new Error(`Auto-scroll interrupted manual reading: ${JSON.stringify({ viewport, before, paused, held })}`)
    const latestButton=page.getByRole('button',{name:'回到最新回复',exact:true})
    const buttonBox=await latestButton.boundingBox(),composerBox=await page.locator('.composer').boundingBox()
    if(!buttonBox||!composerBox||buttonBox.y+buttonBox.height>composerBox.y||Math.abs(buttonBox.x+buttonBox.width/2-composerBox.x-composerBox.width/2)>3)throw new Error('Latest reply button is not centered above the composer')
    answerPaused = true
    await latestButton.click()
    await page.waitForFunction(()=>{
      const el=document.querySelector('.message-transcript')
      return el.scrollHeight-el.clientHeight-el.scrollTop<=2
    },null,{timeout:5000})
    const resumed = await transcript.evaluate(el => ({ top: el.scrollTop, remaining: el.scrollHeight - el.clientHeight - el.scrollTop }))
    if (resumed.top <= held || resumed.remaining > 2) throw new Error(`Follow did not resume at the bottom: ${JSON.stringify({ viewport, before, paused, held, resumed })}`)
    answerPaused = false
    await page.waitForTimeout(650)
    if(await transcript.evaluate(el=>el.scrollTop)<=resumed.top)throw new Error('New output did not resume automatic following after button click')
    const answerFade = await page.locator('.answer-markdown .stream-reveal').first().evaluate(el => getComputedStyle(el).animationName)
    const sampledPositions = await page.evaluate(() => { window.motionSampling = false; return window.motionSamples })
    if (new Set(sampledPositions.map(top => Math.round(top))).size < 10) throw new Error('Scroll did not move through intermediate positions')
    if (reasoningFade !== 'none' || answerFade !== 'stream-text-reveal') throw new Error('Process or answer animation mode incorrect')
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Viewport overflows')
    await page.screenshot({ path: path.join(output, `stream-motion-${viewport.width}.png`) })
    if (errors.length) throw new Error(errors.join('; '))
    report.push({ viewport, reasoningFade, answerFade, manualReadingHeld: true, followResumed: true, latestReplyButton:true, intermediatePositions: new Set(sampledPositions.map(top => Math.round(top))).size })
    await context.close()
  }
  writeFileSync(path.join(output, 'stream-motion-report.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report))
} finally {
  await browser.close()
  for (const timer of timers) clearTimeout(timer)
  await new Promise(resolve => server.close(resolve))
}
