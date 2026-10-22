import { chromium } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const root=path.resolve('../..')
const output=path.join(root,'artifacts/verification')
mkdirSync(output,{recursive:true})
const seed=JSON.parse(execFileSync('docker',['exec','-i','-e',`STOCK_VERIFY_SAVED=${process.env.STOCK_VERIFY_SAVED??'false'}`,'stock-analysis-backend-1','python','-'],{
  input:readFileSync(path.join(root,'scripts/seed_stock_verification.py')),encoding:'utf8',maxBuffer:1024*1024}))
const base=process.env.STOCK_VERIFY_URL??'http://127.0.0.1:18110'
const browser=await chromium.launch({channel:'msedge',headless:true})
const report={artifacts:seed.artifacts,viewports:[],errors:[]}
try{
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
    const context=await browser.newContext({viewport,deviceScaleFactor:1})
    await context.addInitScript(()=>{if(!localStorage.getItem('stock-lab-theme'))localStorage.setItem('stock-lab-theme','light')})
    await context.addCookies([{name:'stock_analysis_session',value:seed.cookie,url:base}])
    const page=await context.newPage()
    await page.route('**/api/v1/conversations/*/messages',async route=>{
      const response=await route.fetch(),messages=await response.json()
      for(const message of messages){
        if(message.role==='ASSISTANT'&&message.stockArtifacts?.length===3){
          message.stockArtifacts[0].charts=[]
          message.content='已保存的行情分析。历史数据集引用（数值需用stock_dataset在本轮复核）：'+JSON.stringify(message.stockArtifacts.map(a=>({datasetRef:a.datasetRef,title:a.title})))
        }
      }
      await route.fulfill({response,json:messages})
    })
    page.on('pageerror',error=>report.errors.push(error.message))
    await page.goto(base)
    const history=page.locator('.conversation-item').filter({hasText:'验证 · 平安银行研究'})
    if(viewport.width<600)await page.getByRole('button',{name:'打开对话导航',exact:true}).click()
    await history.first().click()
    const artifact=page.locator('.stock-artifact').first()
    await artifact.locator('canvas').waitFor({timeout:45000})
    const markdown=page.locator('.message-row.assistant .answer-markdown').first()
    if((await markdown.innerText()).includes('stock_dataset')||await markdown.locator('.inline-data-reference').count()!==3)throw new Error('Legacy reference rendering failed')
    await artifact.scrollIntoViewIfNeeded()
    const pixels=await artifact.locator('canvas').first().evaluate(canvas=>{
      const {data}=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height)
      let painted=0,colored=0
      for(let i=0;i<data.length;i+=4){if(data[i+3]>0)painted++;if(data[i+3]>0&&Math.max(data[i],data[i+1],data[i+2])-Math.min(data[i],data[i+1],data[i+2])>35)colored++}
      return {painted,colored,width:canvas.width,height:canvas.height}
    })
    if(pixels.colored<100)throw new Error('Chart canvas is blank')
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)
    if(overflow)throw new Error('Page overflows viewport')
    const label=viewport.width>600?'desktop':'mobile'
    await page.screenshot({path:path.join(output,`${label}-stock-chart.png`)})
    await artifact.getByRole('button',{name:'全屏分析',exact:true}).click()
    const workspace=page.getByRole('region',{name:'全屏图表分析'})
    await workspace.locator('canvas').waitFor({timeout:45000})
    for(const theme of ['light','dark']){
      if(theme==='dark')await workspace.getByRole('button',{name:'切换到夜间模式',exact:true}).click()
      await page.waitForTimeout(200)
      const palette=await page.evaluate(()=>({
        theme:document.documentElement.dataset.theme,
        analysis:getComputedStyle(document.querySelector('.chat-shell')).backgroundColor,
        user:getComputedStyle(document.querySelector('.message-row.user .message-content')).backgroundColor,
        surface:getComputedStyle(document.querySelector('.conversation-workspace')).getPropertyValue('--surface').trim(),
      }))
      if(palette.theme!==theme||palette.user!=='rgba(0, 0, 0, 0)')throw new Error('Theme or user message background invalid: '+JSON.stringify(palette))
      if(theme==='light'&&!palette.analysis.includes('247, 249, 250'))throw new Error('Light analysis background not applied')
      if(theme==='dark'&&!palette.analysis.includes('24, 26, 30'))throw new Error('Dark analysis background not applied')
      const pixels=await workspace.locator('canvas').first().evaluate(canvas=>{
        const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data
        let painted=0;for(let i=3;i<pixels.length;i+=4)if(pixels[i])painted++
        return painted
      })
      if(pixels<100)throw new Error('Theme chart canvas blank')
      await page.screenshot({path:path.join(output,`${label}-analysis-${theme}.png`)})
      const panelButton=workspace.getByRole('button',{name:'展开固定数据看板',exact:true})
      const panelStyle=await panelButton.evaluate(button=>{
        const box=button.getBoundingClientRect(),style=getComputedStyle(button)
        return {width:box.width,height:box.height,background:style.backgroundColor}
      })
      if(panelStyle.width!==28||panelStyle.height!==28||!panelStyle.background.endsWith('0.32)'))throw new Error('Panel button must be square and translucent: '+JSON.stringify(panelStyle))
      await panelButton.click()
      const pinnedButton=workspace.getByRole('button',{name:'恢复鼠标数据看板',exact:true})
      if(await pinnedButton.getAttribute('aria-pressed')!=='true')throw new Error('Fixed panel did not open')
      const canvasBox=await workspace.locator('canvas').first().boundingBox()
      await page.mouse.move(canvasBox.x+canvasBox.width*.6,canvasBox.y+canvasBox.height*.5)
      await page.waitForTimeout(250)
      await page.screenshot({path:path.join(output,`${label}-panel-${theme}.png`)})
      await pinnedButton.click()
      if(await panelButton.getAttribute('aria-pressed')!=='false')throw new Error('Floating panel did not restore')
    }
    const tabs=workspace.getByRole('tablist',{name:'生成的图表'}).getByRole('tab')
    if(await tabs.count()>4)throw new Error('Unrelated chart groups still share the top tab bar')
    const directory=workspace.locator('.analysis-catalog'),catalogEntries=workspace.locator('.analysis-catalog-entry')
    if(!await directory.isVisible())await workspace.getByRole('button',{name:'切换图表目录',exact:true}).click()
    const entryCount=await catalogEntries.count()
    if(entryCount<5)throw new Error('Conversation chart directory missing generated charts')
    for(let index=0;index<entryCount;index++){
      if(!await directory.isVisible())await workspace.getByRole('button',{name:'切换图表目录',exact:true}).click()
      await catalogEntries.nth(index).click()
      await workspace.locator('canvas').waitFor()
      await page.waitForTimeout(100)
      const visiblePixels=await workspace.locator('canvas').first().evaluate(canvas=>{
        const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data
        let painted=0;for(let i=3;i<pixels.length;i+=4)if(pixels[i])painted++
        return painted
      })
      if(visiblePixels<100)throw new Error('Fullscreen chart blank at directory entry '+index)
    }
    if(!await directory.isVisible())await workspace.getByRole('button',{name:'切换图表目录',exact:true}).click()
    await catalogEntries.first().click()
    await tabs.first().click()
    await workspace.getByRole('tab',{name:'指标与统计',exact:true}).click()
    await workspace.locator('.analysis-indicator-detail').waitFor()
    await workspace.getByRole('tab',{name:'来源',exact:true}).click()
    await workspace.locator('.analysis-provenance').waitFor()
    await workspace.getByRole('tab',{name:/^数据/}).click()
    await tabs.nth(1).click()
    await workspace.locator('canvas').waitFor()
    const imageDownload=page.waitForEvent('download')
    await workspace.getByRole('button',{name:'导出图表 PNG',exact:true}).click()
    const png=await imageDownload
    await png.saveAs(path.join(output,`${label}-export.png`))
    if(readFileSync(path.join(output,`${label}-export.png`)).length<1000)throw new Error('PNG export empty')
    const exportCorner=await page.evaluate(data=>new Promise((resolve,reject)=>{
      const image=new Image();image.onload=()=>{
        const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height
        const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0)
        resolve(Array.from(ctx.getImageData(0,0,1,1).data))
      };image.onerror=reject;image.src='data:image/png;base64,'+data
    }),readFileSync(path.join(output,`${label}-export.png`)).toString('base64'))
    if(JSON.stringify(exportCorner)!=='[32,35,40,255]')throw new Error('PNG background does not follow dark theme: '+JSON.stringify(exportCorner))
    const tableDownload=page.waitForEvent('download')
    await workspace.getByRole('button',{name:'导出查询数据 CSV',exact:true}).click()
    const csv=await tableDownload
    const csvPath=path.join(output,`${label}-export.csv`)
    await csv.saveAs(csvPath)
    if(readFileSync(csvPath,'utf8').trim().split(/\r?\n/).length<301)throw new Error('CSV did not export full saved dataset')
    await workspace.getByRole('button',{name:'引用此行',exact:true}).first().click()
    if(!(await page.getByRole('textbox',{name:'问题',exact:true}).inputValue()).includes('[data:ds_'))throw new Error('Fullscreen reference insertion failed')
    const layout=await workspace.boundingBox()
    const chatBox=await page.locator('.conversation-workspace').boundingBox()
    if(viewport.width>600&&(!layout||!chatBox||layout.width<viewport.width*.6||chatBox.x<layout.width))throw new Error('Fullscreen split layout invalid')
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Fullscreen overflows viewport')
    await page.screenshot({path:path.join(output,`${label}-fullscreen-analysis.png`)})
    await page.keyboard.press('Escape')
    await workspace.waitFor({state:'detached'})
    await page.locator('.stock-artifact canvas').first().waitFor()
    await artifact.getByRole('tab',{name:/数据/}).click()
    await page.screenshot({path:path.join(output,`${label}-table-before-reference.png`)})
    await artifact.getByRole('button',{name:'引用此行',exact:true}).first().click()
    const reference=await page.getByRole('textbox',{name:'问题',exact:true}).inputValue()
    if(!reference.includes('[data:ds_'))throw new Error('Data reference insertion failed')
    await page.screenshot({path:path.join(output,`${label}-stock-table.png`)})
    await artifact.getByRole('tab',{name:'图表',exact:true}).click()
    await page.reload()
    if(await page.evaluate(()=>document.documentElement.dataset.theme)!=='dark')throw new Error('Theme choice did not survive reload')
    if(viewport.width<600)await page.getByRole('button',{name:'打开对话导航',exact:true}).click()
    await page.locator('.conversation-item').filter({hasText:'验证 · 平安银行研究'}).first().click()
    await page.locator('.stock-artifact canvas').first().waitFor({timeout:45000})
    if(await page.locator('.stock-artifact').count()!==3)throw new Error('Message artifacts did not survive reload')
    if(viewport.width>600){
      for(const [index,name] of [[1,'events'],[2,'equity']]){
        const item=page.locator('.stock-artifact').nth(index);await item.scrollIntoViewIfNeeded()
        await item.locator('canvas').waitFor();await page.screenshot({path:path.join(output,`desktop-${name}.png`)})
      }
      if(process.env.STOCK_VERIFY_SEND==='true'){
        if(await page.locator('input[aria-label="RAG"]').count())throw new Error('RAG toggle remains in composer')
        const question='这是一条发送链路测试消息，请仅回复：收到。无需查询数据。'
        await page.getByRole('textbox',{name:'问题',exact:true}).fill(question)
        await page.getByRole('button',{name:'发送',exact:true}).click()
        await page.locator('.message-row.user').last().getByText(question,{exact:true}).waitFor({timeout:15000})
        await page.locator('.message-row.assistant').last().locator('.answer-markdown').filter({hasText:'收到'}).waitFor({timeout:120000})
        await page.waitForFunction(()=>!document.querySelector('button[aria-label="停止回复"]'),null,{timeout:120000})
        const answer=await page.locator('.message-row.assistant').last().innerText()
        if(!answer.includes('收到'))throw new Error('Core did not return expected send-test response: '+answer)
        report.sendVerified=true
        await page.screenshot({path:path.join(output,'desktop-stock-send.png')})
      }
    }
    report.viewports.push({viewport,pixels,referenceInserted:true,reloadPersisted:true,horizontalOverflow:false,fullscreen:true,pngExport:true,fullTableExport:true,legacyReferences:true,chartMetadataRecovered:true,lightDarkThemes:true,themePersisted:true,userActionBackgroundTransparent:true})
    await context.close()
  }
  if(report.errors.length)throw new Error(report.errors.join('; '))
  writeFileSync(path.join(output,'browser-report.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify(report))
}finally{
  await browser.close()
  execFileSync('docker',['exec','-i','stock-analysis-backend-1','python','-'],{input:
    "from app import create_app\nfrom app.extensions import database\nfrom app.models import User,Session\napp=create_app({'TESTING':True})\nwith app.app_context():\n user=database.session.query(User).filter_by(username='stock-verification').one()\n user.status='DISABLED'\n database.session.query(Session).filter_by(user_id=user.id).delete()\n database.session.commit()\n",encoding:'utf8'})
}
