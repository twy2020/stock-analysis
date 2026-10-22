import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
const base=process.env.STOCK_VERIFY_URL||'http://127.0.0.1:18110'
const core=process.env.CORE_PREVIEW_URL||'http://127.0.0.1:18211'
mkdirSync('../../artifacts/verification',{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:1000}}),errors=[]
    page.on('pageerror',e=>errors.push(e.message))
    await page.goto(core+'/admin')
    await page.getByLabel('密码',{exact:true}).fill('preview-admin-password')
    await page.getByRole('button',{name:'登录',exact:true}).click()
    await page.locator('#shell').waitFor({state:'visible'})
    for(const section of ['overview','runs','apps','tools','usage','models']){
      await page.locator(`#navigation [data-page="${section}"]`).click()
      await page.locator('#content h1').waitFor()
      for(const theme of ['light','dark']){
        await page.evaluate(t=>document.documentElement.dataset.theme=t,theme)
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),section+' overflow')
        await page.screenshot({path:`../../artifacts/verification/core-${section}-${width}-${theme}.png`,animations:'disabled'})
      }
    }
    await page.close()
    const chat=await browser.newPage({viewport:{width,height:1000}})
    chat.on('pageerror',e=>errors.push(e.message))
    const conversation={id:'failed-probe',title:'模型连接诊断',knowledgeBaseId:null,activeRunId:null,createdAt:'',updatedAt:''}
    await chat.route('**/api/v1/**',route=>{
      const url=new URL(route.request().url()).pathname
      let json={}
      if(url.endsWith('/auth/session'))json={user:{username:'verify',role:'USER',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(url.endsWith('/capabilities'))json={ragAvailable:false,reasoningToggle:false}
      else if(url.endsWith('/knowledge-bases'))json=[]
      else if(url.endsWith('/conversations'))json=[conversation]
      else if(url.endsWith('/conversations/failed-probe'))json=conversation
      else if(url.endsWith('/messages'))json=[{id:'q',role:'USER',status:'COMPLETED',content:'模型连接测试',citations:[]},
        {id:'a',role:'ASSISTANT',status:'FAILED',content:'',citations:[],errorCode:'TIMEOUT',processEvents:[{stage:'AGENT_THINKING',elapsedMsTotal:200},{stage:'PROCESS_FAILED',status:'FAILED',elapsedMsTotal:120500}]}]
      return route.fulfill({json})
    })
    await chat.goto(base)
    if(width<600)await chat.getByRole('button',{name:'打开对话导航',exact:true}).click()
    await chat.locator('.conversation-open').filter({hasText:conversation.title}).click()
    await chat.getByText('等待模型响应超时，请稍后重试。',{exact:true}).waitFor()
    assert.ok(await chat.getByRole('button',{name:'重新回答',exact:true}).isEnabled())
    assert.ok((await chat.locator('.work-summary').innerText()).includes('2 分'))
    await chat.locator('.work-summary').click()
    assert.equal(await chat.locator('.work-row.is-failed').count(),2)
    assert.ok(!(await chat.locator('.work-history').innerText()).includes('已分析问题'))
    assert.equal(await chat.locator('.retrieval-meta').count(),0)
    for(const theme of ['light','dark']){
      await chat.evaluate(t=>document.documentElement.dataset.theme=t,theme)
      assert.ok(await chat.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      await chat.screenshot({path:`../../artifacts/verification/chat-failure-${width}-${theme}.png`,animations:'disabled'})
    }
    assert.deepEqual(errors,[])
    console.log(JSON.stringify({width,corePages:6,themes:true,failedHistory:true,elapsedTime:true,retry:true,errors}))
    await chat.close()
  }
}finally{await browser.close()}
