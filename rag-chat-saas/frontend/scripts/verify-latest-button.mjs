import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const base = process.env.STOCK_VERIFY_URL ?? 'http://127.0.0.1:18110'
const report = []
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } })
    const page = await context.newPage()
    const conversation = { id: 'verify', title: '按钮验证', knowledgeBaseId: null, activeRunId: 'r', createdAt: '', updatedAt: '' }
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url()).pathname
      let json = {}
      if (url.endsWith('/auth/session')) json = { user: { username: 'verify', role: 'USER', passwordChangeRequired: false }, csrfToken: 'fixture' }
      else if (url.endsWith('/capabilities')) json = { ragAvailable: false, reasoningToggle: false }
      else if (url.endsWith('/knowledge-bases')) json = []
      else if (url.endsWith('/conversations')) json = [conversation]
      else if (url.endsWith('/conversations/verify')) json = conversation
      else if (url.endsWith('/messages')) json = [{ id: 'a', role: 'ASSISTANT', status: 'STREAMING', content: '', citations: [] }]
      else if (url.endsWith('/runs/r')) json = { id: 'r', conversationId: 'verify', assistantMessageId: 'a', userMessageId: 'u', status: 'RUNNING' }
      else if (url.endsWith('/events')) return route.fulfill({ contentType: 'text/event-stream', body: 'event: progress\ndata: {"stage":"AGENT_THINKING","eventId":1}\n\n' })
      await route.fulfill({ json })
    })
    await page.goto(base)
    if (width < 600) await page.getByRole('button', { name: '打开对话导航', exact: true }).click()
    await page.locator('.conversation-item').filter({ hasText: conversation.title }).click()
    const button = page.getByRole('button', { name: '回到最新回复', exact: true })
    await button.waitFor()
    const before = await button.boundingBox()
    await page.mouse.move(before.x + before.width / 2, before.y + before.height / 2)
    await page.mouse.down()
    await page.waitForTimeout(180)
    const pressed = await button.boundingBox()
    await page.mouse.up()
    await page.waitForTimeout(180)
    const after = await button.boundingBox()
    assert.ok(Math.abs(before.x - pressed.x) < 0.5, 'Button shifts horizontally when pressed')
    assert.ok(Math.abs(before.x - after.x) < 0.5, 'Button shifts horizontally after clicking')
    const waves = await button.locator('svg circle').evaluateAll(dots => dots.map(dot => ({ name: getComputedStyle(dot).animationName, delay: getComputedStyle(dot).animationDelay })))
    assert.deepEqual(waves.map(dot => dot.name), ['latest-dot-wave', 'latest-dot-wave', 'latest-dot-wave'])
    assert.equal(new Set(waves.map(dot => dot.delay)).size, 3)
    await page.screenshot({path:`F:/my_projects/stock_analizer/.stock-private/latest-wave-${width}.png`})
    await page.emulateMedia({reducedMotion:'reduce'})
    assert.ok(await button.locator('svg circle').evaluateAll(dots => dots.every(dot => getComputedStyle(dot).animationName === 'none')))
    report.push({ width, beforeX: before.x, pressedX: pressed.x, afterX: after.x, staggeredWave:true, reducedMotion:true })
    await context.close()
  }
  console.log(JSON.stringify(report))
} finally { await browser.close() }
