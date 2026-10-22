import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:1000}})
    let saved
    await page.route('**/api/v1/**',route=>{
      const url=new URL(route.request().url()).pathname
      let json={}
      if(url.endsWith('/auth/session'))json={user:{username:'verify',role:'ADMIN',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(url.endsWith('/settings/features'))json={ragEnabled:false,webEnabled:true}
      else if(url.endsWith('/settings/web-proxy')){
        if(route.request().method()==='PUT')saved=route.request().postDataJSON()
        json={enabled:!!saved?.enabled,configured:true,endpoint:'socks5://host.docker.internal:10808',mode:'selected',domains:['bing.com','yahoo.com']}
      }else if(url.endsWith('/settings/web-proxy/test'))json={ok:true,elapsedMs:250}
      else if(url.endsWith('/stats'))json={ragRequests:0,providerRequests:0,providerFailures:0,tokens:0,averageProviderLatencyMs:0,activeUsers:1}
      else if(url.endsWith('/admin/health'))json={rag:{status:'NOT_CONFIGURED'},providers:[]}
      else if(url.endsWith('/feedback/stats'))json={new:0,reviewing:0,unread:0}
      else if(url.endsWith('/conversations')||url.endsWith('/knowledge-bases'))json=[]
      return route.fulfill({json})
    })
    await page.goto('http://127.0.0.1:18110/admin')
    await page.getByRole('button',{name:'系统设置',exact:true}).click()
    const form=page.locator('.web-proxy-settings')
    await form.getByLabel('启用代理').check()
    await form.getByRole('button',{name:'保存代理',exact:true}).click()
    await form.getByRole('status').waitFor()
    assert.equal(saved.enabled,true)
    assert.equal(saved.url,undefined)
    await form.getByRole('button',{name:'测试已保存代理',exact:true}).click()
    await form.getByRole('status').filter({hasText:'代理连通'}).waitFor()
    for(const theme of ['dark','light']){
      await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme)
      await form.scrollIntoViewIfNeeded()
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      await page.screenshot({path:`F:/my_projects/stock_analizer/.stock-private/proxy-${width}-${theme}.png`,fullPage:true})
    }
    console.log(JSON.stringify({width,saved:true,testButton:true,themes:true}))
    await page.close()
  }
}finally{await browser.close()}
