import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    const source = { id:'web_fixture', url:'https://example.com/report', title:'公告原文', domain:'example.com', engines:['bing','so360'], read:true }
    const conversation = { id:'web-verify', title:'来源验证', knowledgeBaseId:null, activeRunId:null, createdAt:'', updatedAt:'' }
    await page.route('https://example.com/favicon.ico', route => route.fulfill({status:404}))
    await page.route('**/api/v1/**', route => {
      const url = new URL(route.request().url()).pathname
      let json = {}
      if (url.endsWith('/auth/session')) json = { user:{username:'verify',role:'USER',passwordChangeRequired:false},csrfToken:'fixture' }
      else if(url.endsWith('/capabilities')) json = {ragAvailable:false,reasoningToggle:false}
      else if(url.endsWith('/knowledge-bases')) json = []
      else if(url.endsWith('/conversations')) json = [conversation]
      else if(url.endsWith('/conversations/web-verify')) json = conversation
      else if(url.endsWith('/messages')) json = [{id:'a',role:'ASSISTANT',status:'COMPLETED',content:'公告事实[公告原文](https://example.com/report)',citations:[],processEvents:[{stage:'TOOL_EXECUTING',operationId:'1',status:'RUNNING'},{stage:'TOOL_COMPLETED',operationId:'1',status:'COMPLETED',tool:'stock_web_search',sources:[source]}]}]
      return route.fulfill({json})
    })
    await page.goto('http://127.0.0.1:18110')
    if(width<600)await page.getByRole('button',{name:'打开对话导航',exact:true}).click()
    await page.locator('.conversation-item').filter({hasText:conversation.title}).click()
    await page.locator('.work-summary').click()
    await page.locator('.web-source-icons a').waitFor()
    assert.equal(await page.locator('.web-source-icons a').getAttribute('href'),source.url)
    assert.equal(await page.getByRole('link',{name:'公告原文',exact:true}).first().getAttribute('href'),source.url)
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
    await page.screenshot({path:`F:/my_projects/stock_analizer/.stock-private/web-sources-${width}.png`,fullPage:true})
    console.log(JSON.stringify({width,sourceIcon:true,markdownLink:true}))
    await page.close()
  }
} finally { await browser.close() }
