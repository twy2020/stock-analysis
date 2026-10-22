import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'

const base=process.env.CORE_LOGIN_URL||'http://127.0.0.1:18210'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
  for(const width of [1440,390]){
    const context=await browser.newContext({viewport:{width,height:1000}})
    const page=await context.newPage(),errors=[]
    page.on('pageerror',error=>errors.push(error.message))
    await page.goto(base+'/admin')
    await page.getByLabel('密码',{exact:true}).fill('admin123')
    await page.getByRole('button',{name:'登录',exact:true}).click()
    await page.getByRole('heading',{name:'修改初始密码',exact:true}).waitFor()
    const status=await context.request.get(base+'/admin/api/status')
    assert.equal(status.status(),403)
    assert.equal((await status.json()).code,'ADMIN_PASSWORD_CHANGE_REQUIRED')
    await page.reload()
    await page.getByRole('heading',{name:'修改初始密码',exact:true}).waitFor()
    await page.getByLabel('当前密码',{exact:true}).fill('admin123')
    await page.getByLabel('新密码',{exact:true}).fill('mismatch-fixture-password')
    await page.getByLabel('确认新密码',{exact:true}).fill('different-fixture-password')
    await page.getByRole('button',{name:'保存密码',exact:true}).click()
    assert.equal(await page.locator('#password-error').textContent(),'两次输入的新密码不一致')
    for(const theme of ['light','dark']){
      await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme)
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      await page.screenshot({path:`F:/my_projects/stock_analizer/.stock-private/core-login-${width}-${theme}.png`,fullPage:true})
    }
    await page.getByRole('button',{name:'退出登录',exact:true}).click()
    await page.getByRole('heading',{name:'管理员登录',exact:true}).waitFor()
    assert.equal((await context.request.get(base+'/admin/api/status')).status(),401)
    assert.deepEqual(errors,[])
    console.log(JSON.stringify({width,firstLogin:true,passwordGate:true,refreshRestoresSession:true,confirmationValidation:true,logout:true}))
    await context.close()
  }
}finally{await browser.close()}
