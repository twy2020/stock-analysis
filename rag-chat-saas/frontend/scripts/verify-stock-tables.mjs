import { chromium } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const base=process.env.STOCK_VERIFY_URL??'http://127.0.0.1:18110'
const out=path.resolve('artifacts/verification');await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
const report=[]
const directory={version:'1',datasetRef:'ds_'+'a'.repeat(32),title:'股票目录',rowCount:53,
  summary:{totalResultRows:53,coverage:{limitReached:false}},warnings:[],charts:[],
  provenance:{dataAsOf:'2026-09-30',query:{task:'query',source:'stocks'}},
  table:Array.from({length:53},(_,i)=>({code:String(i+1).padStart(6,'0'),name:`验证股票 ${i+1}`,board:i%2?'深市':'沪市'}))}
const aggregate={...directory,datasetRef:'ds_'+'b'.repeat(32),title:'分组统计',rowCount:2,
  summary:{aggregates:[{board:'沪市',meanClose:12.5},{board:'深市',meanClose:16.2}]},
  table:[{board:'沪市',meanClose:12.5},{board:'深市',meanClose:16.2}]}
const line={...directory,datasetRef:'ds_'+'c'.repeat(32),title:'价格趋势',rowCount:2,
  provenance:{dataAsOf:'2026-09-30',query:{task:'analyze'}},summary:{},
  charts:[{kind:'line',title:'价格趋势',unit:'CNY',fields:['close'],rows:[{date:'2026-09-29',close:10},{date:'2026-09-30',close:12}]}],
  table:[{date:'2026-09-29',close:10},{date:'2026-09-30',close:12}]}
const artifacts=[directory,aggregate,line]
try{
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
    const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[]
    page.on('pageerror',e=>errors.push(e.message))
    const conversation={id:'tables',title:'数据视图验证',knowledgeBaseId:null,activeRunId:null,createdAt:'',updatedAt:''}
    await page.route('**/api/v1/**',async route=>{
      const url=new URL(route.request().url()).pathname;let json={}
      if(url.endsWith('/auth/session'))json={user:{username:'verify',role:'USER',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(url.endsWith('/capabilities'))json={ragAvailable:false,reasoningToggle:true}
      else if(url.endsWith('/knowledge-bases'))json=[]
      else if(url.endsWith('/conversations'))json=[conversation]
      else if(url.endsWith('/conversations/tables'))json=conversation
      else if(url.endsWith('/messages'))json=[{id:'q',role:'USER',content:'查看股票目录和统计结果',status:'COMPLETED',citations:[]},{id:'a',role:'ASSISTANT',content:'查询结果。',status:'COMPLETED',citations:[],stockArtifacts:artifacts}]
      else if(url.includes('/artifacts/'))json=artifacts.find(a=>url.endsWith(a.datasetRef))??{}
      await route.fulfill({json})
    })
    await page.goto(base)
    if(viewport.width<600)await page.getByRole('button',{name:'打开对话导航',exact:true}).click()
    await page.locator('.conversation-item').filter({hasText:conversation.title}).click()
    const first=page.locator('#'+directory.datasetRef)
    await first.locator('tbody tr').first().waitFor()
    if(await first.getByRole('tab',{name:'图表',exact:true}).count())throw new Error('Directory has an unsupported chart tab')
    if(await first.getByRole('button',{name:'导出图表 PNG',exact:true}).count())throw new Error('Directory has PNG export')
    if(await first.locator('tbody tr').count()!==20)throw new Error('Pagination failed')
    await first.getByRole('button',{name:'下一页',exact:true}).click()
    if(!(await first.locator('tbody tr').first().innerText()).includes('000021'))throw new Error('Second page failed')
    await first.getByRole('searchbox',{name:'筛选已加载数据'}).fill('验证股票 53')
    await first.getByRole('button',{name:'记录详情模式'}).click()
    if(!(await first.locator('.data-records').innerText()).includes('000053'))throw new Error('Record details failed')
    await first.getByRole('button',{name:'全屏分析',exact:true}).click()
    const workspace=page.getByRole('region',{name:'全屏图表分析'})
    const primary=workspace.locator('.analysis-table-primary')
    await primary.locator('tbody tr').first().waitFor()
    if(await workspace.locator('canvas').count())throw new Error('Table rendered as a chart')
    if(await workspace.getByRole('button',{name:'导出图表 PNG',exact:true}).count())throw new Error('Fullscreen table has PNG export')
    for(const theme of ['light','dark']){
      if(theme==='dark')await workspace.getByRole('button',{name:'切换到夜间模式',exact:true}).click()
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Horizontal page overflow')
      const box=await primary.boundingBox()
      if(!box||box.height<100)throw new Error('Main table area collapsed')
      await page.screenshot({path:path.join(out,`tables-${viewport.width}-${theme}.png`)})
    }
    await workspace.getByRole('button',{name:'关闭全屏分析'}).click()
    const chart=page.locator('#'+line.datasetRef)
    await chart.locator('canvas').waitFor()
    const pixels=await chart.locator('canvas').evaluate(canvas=>{
      const bytes=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data
      let n=0;for(let i=3;i<bytes.length;i+=4)if(bytes[i])n++;return n
    })
    if(pixels<100)throw new Error('Existing chart rendering is blank')
    if(errors.length)throw new Error(errors.join('\n'))
    report.push({width:viewport.width,tableDefault:true,recordDetails:true,pagination:true,fullscreenTable:true,lightDark:true,chartPixels:pixels,errors})
    await context.close()
  }
  console.log(JSON.stringify(report))
}finally{await browser.close()}
