import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const base = process.env.STOCK_VERIFY_URL ?? 'http://127.0.0.1:18110'
const output = path.resolve('../../artifacts/verification')
mkdirSync(output, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    for (const screen of ['login', 'admin']) {
      const context = await browser.newContext({ viewport, colorScheme: 'light' })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      if (screen === 'admin') await page.route('**/api/v1/**', route => {
        const auth = route.request().url().endsWith('/auth/session')
        return route.fulfill({ json: auth ? { user: { username: 'theme-verification', role: 'ADMIN', passwordChangeRequired: false }, csrfToken: 'fixture' }
          : { rag: { status: 'UNKNOWN', latencyMs: null }, providers: [], ragRequests: 0, providerRequests: 0, providerFailures: 0, tokens: 0, averageProviderLatencyMs: 0, activeUsers: 0 } })
      })
      await page.goto(`${base}/${screen}`)
      await page.getByRole('button', { name: '切换到夜间模式', exact: true }).click()
      await page.waitForTimeout(200)
      if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'dark') throw new Error('Theme toggle failed')
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`${screen} overflows`)
      await page.screenshot({ path: path.join(output, `${screen}-dark-${viewport.width}.png`) })
      await page.getByRole('button', { name: '切换到日间模式', exact: true }).click()
      await page.waitForTimeout(200)
      await page.screenshot({ path: path.join(output, `${screen}-light-${viewport.width}.png`) })
      if (errors.length) throw new Error(errors.join('; '))
      await context.close()
    }
  }
  console.log('Login and admin light/dark themes verified on desktop and mobile')
} finally { await browser.close() }
