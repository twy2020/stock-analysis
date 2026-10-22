import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
const base=process.env.CORE_PREVIEW_URL||'http://127.0.0.1:18211'
mkdirSync('../../artifacts/verification',{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:1000}}),errors=[]
    page.on('pageerror',e=>errors.push(e.message))
    await page.goto(base+'/admin#models')
    await page.getByLabel('密码',{exact:true}).fill('preview-admin-password')
    await page.getByRole('button',{name:'登录',exact:true}).click()
    const search=page.getByLabel('搜索模型',{exact:true})
    await search.fill('no-such-model')
    assert.equal(await page.locator('[data-resource-row]:visible').count(),0)
    await page.getByText('暂无匹配模型',{exact:true}).waitFor()
    await search.fill('deepseek-flash')
    assert.equal(await page.locator('[data-resource-row]:visible').count(),1)
    await page.route('**/admin/api/models/*/test',route=>route.fulfill({json:{status:'failed',code:'INVALID_PROVIDER_ENDPOINT',elapsedMs:1300,mode:'text',httpStatus:200}}))
    await page.getByRole('button',{name:'测试连接',exact:true}).first().click()
    const drawer=page.getByRole('dialog')
    await page.getByText('接口返回网页，请检查 Base URL 是否包含 /v1。',{exact:false}).waitFor()
    await page.unroute('**/admin/api/models/*/test')
    await page.route('**/admin/api/models/*/test',route=>route.fulfill({json:{status:'succeeded',code:'OK',elapsedMs:2200,mode:'tools'}}))
    await drawer.getByRole('button',{name:'测试工具调用',exact:true}).click()
    await page.getByText('工具调用验证通过',{exact:false}).waitFor()
    await drawer.getByLabel('名称',{exact:true}).fill('Unsaved name')
    await page.keyboard.press('Escape')
    assert.equal(await drawer.getByLabel('名称',{exact:true}).inputValue(),'Unsaved name')
    for(const theme of ['light','dark']){
      await page.evaluate(t=>document.documentElement.dataset.theme=t,theme)
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      await page.screenshot({path:`../../artifacts/verification/core-model-diagnostics-${width}-${theme}.png`,animations:'disabled'})
    }
    page.once('dialog',dialog=>dialog.dismiss())
    await drawer.getByRole('button',{name:'取消',exact:true}).click()
    assert.ok(await drawer.isVisible())
    page.once('dialog',dialog=>dialog.accept())
    await drawer.getByRole('button',{name:'取消',exact:true}).click()
    assert.ok(await drawer.isHidden())
    await page.locator('#navigation [data-page="providers"]').click()
    await page.locator('[data-provider-node="providers:deepseek"] .tree-label').click()
    await drawer.getByLabel('HTTP 代理地址',{exact:true}).fill('http://host.docker.internal:10808')
    const saved=page.waitForResponse(r=>r.url().endsWith('/admin/api/registry')&&r.request().method()==='PATCH')
    await drawer.getByRole('button',{name:'保存更改',exact:true}).click()
    const registry=await (await saved).json()
    assert.equal(registry.providers.find(p=>p.id==='deepseek').proxyUrl,'http://host.docker.internal:10808')
    assert.deepEqual(errors,[])
    console.log(JSON.stringify({width,search:true,diagnostics:true,dirtyGuard:true,themes:true}))
    await page.close()
  }
}finally{await browser.close()}
