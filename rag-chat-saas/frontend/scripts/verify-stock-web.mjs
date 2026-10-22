import { chromium } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs/promises'

const base=process.env.STOCK_VERIFY_URL??'http://127.0.0.1:18110'
const out=path.resolve('artifacts/verification')
await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
const report=[]
try {
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
    const context=await browser.newContext({viewport})
    const page=await context.newPage();const errors=[];let available=true;let sent=null
    page.on('pageerror',error=>errors.push(error.message))
    const conversation={id:'web',title:'联网验证',knowledgeBaseId:null,activeRunId:null,createdAt:'',updatedAt:''}
    await page.route('**/api/v1/**',async route=>{
      const url=new URL(route.request().url()).pathname;let json={}
      if(url.endsWith('/auth/session'))json={user:{username:'verify',role:'USER',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(url.endsWith('/capabilities'))json={ragAvailable:false,reasoningToggle:true,webAvailable:available}
      else if(url.endsWith('/knowledge-bases'))json=[]
      else if(url.endsWith('/conversations'))json=route.request().method()==='POST'?conversation:[]
      else if(url.endsWith('/messages'))json=[]
      else if(url.endsWith('/runs')&&route.request().method()==='POST'){
        sent=route.request().postDataJSON();json={id:'web-run',conversationId:'web',status:'QUEUED'}
      }else if(url.endsWith('/events')){
        await route.fulfill({contentType:'text/event-stream',body:'event: complete\ndata: {"content":"联网选项已记录","citations":[]}\n\n'});return
      }
      await route.fulfill({json})
    })
    await page.goto(base)
    const toggle=page.getByRole('checkbox',{name:'联网搜索与浏览',exact:true})
    await toggle.waitFor();if(await toggle.isChecked())throw new Error('Web must default off')
    await toggle.check()
    await page.getByRole('textbox',{name:'问题',exact:true}).fill('验证联网选项')
    await page.screenshot({path:path.join(out,`stock-web-${viewport.width}.png`)})
    const messagesResponse=page.waitForResponse(r=>r.url().endsWith('/messages'))
    await page.getByRole('button',{name:'发送',exact:true}).click()
    await messagesResponse
    if(sent?.webEnabled!==true)throw new Error('Web opt-in missing from run payload')
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)
    if(overflow||errors.length)throw new Error(JSON.stringify({overflow,errors}))
    available=false;await page.reload()
    await page.getByRole('textbox',{name:'问题',exact:true}).waitFor()
    if(await toggle.count())throw new Error('Administrator-closed feature must be hidden')
    report.push({width:viewport.width,optInForwarded:true,defaultOff:true,closedHidden:true,overflow:false})
    await context.close()
  }
  await fs.writeFile(path.join(out,'stock-web-report.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify(report))
}finally{await browser.close()}
