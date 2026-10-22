import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try {
  for(const width of [1440,390]) {
    const page=await browser.newPage({viewport:{width,height:1000}})
    const errors=[];page.on('pageerror',e=>errors.push(e.message))
    page.on('console',message=>{if(message.type()==='error')console.log(message.text())})
    page.on('requestfailed',request=>console.log('Request failed: '+request.url()+' '+request.failure()?.errorText))
    let saved
    const providers=['native','qianfan','zhihu','deepseek'].map((id,i)=>({id,name:['多引擎搜索','百度千帆 AI 搜索','知乎站内搜索','DeepSeek 官方 web_search'][i],enabled:i===0,priority:i+1,timeoutSeconds:18,toolName:'',configured:i===0,supported:i!==3,transport:i===0?'stdio':'MCP',docs:'https://example.com',health:{status:'untested'},reason:i===3?'当前官方文档不支持 web_search':undefined}))
    await page.route('**/api/v1/**',route=>{
      const path=new URL(route.request().url()).pathname
      let json={}
      if(path.endsWith('/auth/session'))json={user:{username:'verify',role:'ADMIN',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(path.endsWith('/settings/model'))json={backend:'core'}
      else if(path.endsWith('/settings/search-engines')){
        if(route.request().method()==='PUT'){
          saved=route.request().postDataJSON()
          saved.providers.forEach(p=>{const provider=providers.find(v=>v.id===p.id);Object.assign(provider,p,{configured:p.id==='native'||!!p.apiKey});delete provider.apiKey})
        }
        json={engines:[],providers}
      }else if(path.endsWith('/search-engines/qianfan/test'))json={ok:true,sources:[{url:'https://example.com/report',title:'真实来源测试'}],toolName:'ai_search'}
      else if(path.endsWith('/settings/web-proxy'))json={enabled:true,configured:true,endpoint:'socks5://host.docker.internal:10808',mode:'selected',domains:['duckduckgo.com']}
      else if(path.endsWith('/stats'))json={activeUsers:1}
      else if(path.endsWith('/admin/health'))json={rag:{status:'NOT_CONFIGURED'},providers:[]}
      else if(path.endsWith('/feedback/stats'))json={unread:0}
      return route.fulfill({json})
    })
    await page.goto('http://127.0.0.1:18110/admin',{waitUntil:'networkidle'})
    if(!await page.getByRole('button',{name:'AI 搜索引擎',exact:true}).count()){
      console.log(JSON.stringify({url:page.url(),errors,body:(await page.locator('body').innerText()).slice(0,2000)}))
      await page.screenshot({path:'F:/my_projects/stock_analizer/.stock-private/search-manager-error.png',fullPage:true})
    }
    await page.getByRole('button',{name:'AI 搜索引擎',exact:true}).click()
    const form=page.locator('.search-settings')
    await form.getByLabel('启用DeepSeek 官方 web_search').waitFor()
    assert.ok(await form.getByLabel('启用DeepSeek 官方 web_search').isDisabled())
    const qianfan=form.locator('.provider-row').filter({hasText:'百度千帆 AI 搜索'})
    await qianfan.getByLabel('API Key',{exact:true}).fill('fixture-key')
    await qianfan.getByLabel('启用百度千帆 AI 搜索').check()
    await form.getByRole('button',{name:'百度千帆 AI 搜索提高优先级'}).click()
    await form.getByRole('button',{name:'保存搜索配置',exact:true}).click()
    await form.getByRole('status').filter({hasText:'已保存'}).waitFor()
    assert.equal(saved.providers[0].id,'qianfan');assert.equal(saved.providers[0].apiKey,'fixture-key')
    await qianfan.getByRole('button',{name:'测试已保存配置',exact:true}).click()
    await form.getByRole('link',{name:'真实来源测试'}).waitFor()
    for(const theme of ['dark','light']){
      await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme)
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      await page.screenshot({path:`F:/my_projects/stock_analizer/.stock-private/search-manager-${width}-${theme}.png`,fullPage:true})
    }
    assert.deepEqual(errors,[])
    console.log(JSON.stringify({width,save:true,priority:true,test:true,themes:true}))
    await page.close()
  }
}finally{await browser.close()}
