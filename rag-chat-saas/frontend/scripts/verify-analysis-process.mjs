import { chromium } from '@playwright/test'
import path from 'node:path'

const base=process.env.STOCK_VERIFY_URL??'http://127.0.0.1:18110'
const browser=await chromium.launch({channel:'msedge',headless:true})
try {
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const context=await browser.newContext({viewport})
    const page=await context.newPage()
    const errors=[]
    page.on('pageerror',e=>errors.push(e.message))
    const conversation={id:'process',title:'分析层级验证',knowledgeBaseId:null,activeRunId:null,createdAt:'',updatedAt:''}
    await page.route('**/api/v1/**',async route=>{
      const url=new URL(route.request().url()).pathname
      let json={}
      if(url.endsWith('/auth/session'))json={user:{username:'verify',role:'USER',passwordChangeRequired:false},csrfToken:'fixture'}
      else if(url.endsWith('/capabilities'))json={ragAvailable:false,reasoningToggle:true}
      else if(url.endsWith('/knowledge-bases'))json=[]
      else if(url.endsWith('/conversations'))json=[conversation]
      else if(url.endsWith('/conversations/process'))json=conversation
      else if(url.endsWith('/messages'))json=[
        {id:'q',role:'USER',content:'比较趋势与风险',status:'COMPLETED',citations:[]},
        {id:'a',role:'ASSISTANT',content:'需要结合数据覆盖日期与统计样本解读分析结果。',status:'COMPLETED',citations:[],
          reasoningContent:'核对个股行情的实际截止日期，使用引擎返回的趋势和波动统计，并检查事件样本量与回测成本。',
          processEvents:[
            {stage:'MODEL_REASONING',elapsedMsTotal:0},
            {stage:'MODEL_NOTE',content:'I have the 300-day data. Now I need to analyze the Bollinger bands for different timeframes.\n\n300日布林带：先核对实际行情覆盖范围与预热，再读取数据引擎的统计结果。\n100日布林带：比较不同观察窗口的趋势、波动及样本覆盖。\n10日与5日：核对最新位置和带宽，区分指标周期与观察区间。'.repeat(3)},
            {stage:'TOOL_EXECUTING',tool:'stock_query',operationId:'q',status:'RUNNING'},
            {stage:'TOOL_COMPLETED',tool:'stock_query',operationId:'q',status:'COMPLETED',elapsedMs:320},
            {stage:'MODEL_NOTE',content:'行情已经取得，继续检查样本和风险指标。'},
            {stage:'TOOL_EXECUTING',tool:'stock_analyze',operationId:'a',status:'RUNNING'},
            {stage:'TOOL_COMPLETED',tool:'stock_analyze',operationId:'a',status:'COMPLETED',elapsedMs:180},
            {stage:'PROCESS_COMPLETED',elapsedMsTotal:1500},
          ]},
      ]
      await route.fulfill({json})
    })
    await page.goto(base)
    if(viewport.width<600)await page.getByRole('button',{name:'打开对话导航',exact:true}).click()
    await page.locator('.conversation-open').filter({hasText:'分析层级验证'}).click()
    await page.locator('.work-summary').click()
    await page.locator('.work-note').first().waitFor()
    if(await page.locator('.work-note').count()!==2)throw new Error('Missing analysis notes')
    const geometry=await page.locator('.work-note').first().evaluate(row=>{
      const paragraph=row.querySelector('p'),a=row.getBoundingClientRect(),b=paragraph.getBoundingClientRect(),next=row.nextElementSibling?.getBoundingClientRect()
      return {indent:b.left-a.left,inside:b.right<=a.right+1,nextClear:!next||next.top>=b.bottom}
    })
    if(geometry.indent<23||!geometry.inside||!geometry.nextClear)throw new Error('Timeline note overlaps: '+JSON.stringify(geometry))
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Viewport overflow')
    await page.screenshot({path:path.resolve(`../../artifacts/verification/analysis-process-${viewport.width}.png`)})
    if(errors.length)throw new Error(errors.join('; '))
    await context.close()
  }
  console.log('Analysis hierarchy verified on desktop and mobile')
} finally {await browser.close()}
