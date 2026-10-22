import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'

const base = process.env.STOCK_VERIFY_URL ?? 'http://127.0.0.1:18110'
const out = path.resolve('artifacts/verification')
await fs.mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const report = []
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error' && !message.text().includes('401 (Unauthorized)')) errors.push(message.text()) })
    let expired = false, saved
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url()).pathname
      if (expired && url.endsWith('/settings/features')) {
        return route.fulfill({ status: 401, json: { code: 'AUTHENTICATION_REQUIRED', message: 'Sign in required' } })
      }
      let json = {}
      if (url.endsWith('/auth/session')) json = { user: { username: 'verify', role: 'ADMIN', passwordChangeRequired: false }, csrfToken: 'fixture' }
      else if (url.endsWith('/settings/features')) {
        if (route.request().method() === 'PUT') saved = route.request().postDataJSON()
        json = saved ?? { ragEnabled: false, webEnabled: false }
      } else if (url.endsWith('/stats')) json = { ragRequests: 0, providerRequests: 0, providerFailures: 0, tokens: 0, averageProviderLatencyMs: 0, activeUsers: 1 }
      else if (url.endsWith('/admin/health')) json = { rag: { status: 'NOT_CONFIGURED' }, providers: [] }
      else if (url.endsWith('/feedback/stats')) json = { new: 0, reviewing: 0, unread: 0 }
      else if (url.endsWith('/capabilities')) json = { ragAvailable: false, webAvailable: false, reasoningToggle: false }
      else if (url.endsWith('/conversations') || url.endsWith('/knowledge-bases')) json = []
      await route.fulfill({ json })
    })
    await page.goto(base + '/admin')
    await page.getByRole('button', { name: '系统设置', exact: true }).click()
    const form = page.locator('.feature-settings')
    await form.getByRole('checkbox', { name: '开放知识库检索（RAG）' }).waitFor()
    await form.getByRole('checkbox', { name: '开放联网搜索与网页浏览' }).check()
    await form.getByRole('button', { name: '保存设置', exact: true }).click()
    await form.getByRole('status').filter({ hasText: '设置已保存' }).waitFor()
    assert.deepEqual(saved, { ragEnabled: false, webEnabled: true })
    for (const theme of ['dark', 'light']) {
      await page.evaluate(theme => {
        document.documentElement.dataset.theme = theme
        document.documentElement.style.colorScheme = theme
      }, theme)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
      for (const row of await form.locator('.feature-toggle').all()) {
        const bounds = await row.boundingBox()
        const input = await row.locator('input').boundingBox()
        const copy = await row.locator('.feature-copy').boundingBox()
        assert.ok(input && copy && bounds && input.x >= copy.x + copy.width)
        assert.ok(input.width <= 20 && bounds.x + bounds.width <= width)
      }
      await page.screenshot({ path: path.join(out, `settings-${width}-${theme}.png`) })
    }
    expired = true
    await form.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.waitForURL('**/login')
    await page.getByRole('heading', { name: '欢迎回来', exact: true }).waitFor()
    assert.deepEqual(errors, [])
    report.push({ width, saved: true, aligned: true, sessionRedirect: true, errors })
    await context.close()
  }
  console.log(JSON.stringify(report))
} finally { await browser.close() }
