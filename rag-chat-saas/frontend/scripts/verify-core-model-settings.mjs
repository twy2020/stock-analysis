import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:1000}})
    page.on('pageerror',error=>console.log('Page error: '+error.message))
    page.on('console',message=>{if(message.type()==='error')console.log(message.text())})
    page.on('requestfailed',request=>console.log('Request failed: '+request.url()+' '+request.failure()?.errorText))
    let selected='primary',saved
    await page.route('**/api/v1/**',route=>{
      const url=new URL(route.request().url()).pathname
      let json={}
      if(url.endsWith('/auth/session'))json={user:{username:'verify',role:'ADMIN',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(url.endsWith('/settings/model')){
        if(route.request().method()==='PUT'){saved=route.request().postDataJSON();selected=saved.modelProfile}
        json={backend:'core',revision:'fixture',writable:true,defaultModelProfile:selected,models:[
          {id:'primary',name:'SiliconFlow',model:'deepseek-ai/DeepSeek-V4-Flash',providerType:'SILICONFLOW',tools:true},
          {id:'native',name:'DeepSeek 官方',model:'deepseek-flash',providerType:'DEEPSEEK',tools:true}]}
      }else if(url.endsWith('/settings/features'))json={ragEnabled:false,webEnabled:true}
      else if(url.endsWith('/settings/web-proxy'))json={enabled:false,configured:false,domains:[],mode:'selected'}
      else if(url.endsWith('/stats'))json={ragRequests:0,providerRequests:0,providerFailures:0,tokens:0,averageProviderLatencyMs:0,activeUsers:1}
      else if(url.endsWith('/admin/health'))json={rag:{status:'NOT_CONFIGURED'},providers:[]}
      else if(url.endsWith('/feedback/stats'))json={new:0,reviewing:0,unread:0}
      else if(url.endsWith('/conversations')||url.endsWith('/knowledge-bases'))json=[]
      return route.fulfill({json})
    })
    await page.goto((process.env.STOCK_VERIFY_URL??'http://127.0.0.1:18110')+'/admin',{waitUntil:'networkidle'})
    await page.waitForTimeout(500)
    if(!await page.getByRole('button',{name:'模型供应商',exact:true}).count()){
      console.log(JSON.stringify({url:page.url(),body:(await page.locator('body').innerText()).slice(0,1500)}))
      await page.screenshot({path:'F:/my_projects/stock_analizer/.stock-private/core-model-error.png',fullPage:true})
    }
    await page.getByRole('button',{name:'模型供应商',exact:true}).click()
    const form=page.locator('.core-model-settings')
    await form.getByLabel('Core 授权模型').selectOption('native')
    await form.getByRole('button',{name:'保存模型',exact:true}).click()
    await form.getByRole('status').filter({hasText:'已同步至 Core'}).waitFor()
    assert.equal(saved.modelProfile,'native')
    assert.ok(await form.locator('.active-model').innerText().then(text=>text.includes('deepseek-flash')))
    assert.equal(await page.getByRole('button',{name:'添加供应商',exact:true}).count(),0)
    for(const theme of ['dark','light']){
      await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme)
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      await page.screenshot({path:`F:/my_projects/stock_analizer/.stock-private/core-model-${width}-${theme}.png`,fullPage:true})
    }
    console.log(JSON.stringify({width,saved:true,actualModel:true,themes:true}))
    await page.close()
  }
}finally{await browser.close()}
