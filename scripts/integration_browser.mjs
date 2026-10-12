// Real existing FE UI + installed Edge; no API interception or fake workflow.
import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { chromium } from './browser/node_modules/playwright/index.mjs'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const privateDir=path.join(root,'runtime/s411/private')
const accounts=JSON.parse(await fs.readFile(path.join(privateDir,'accounts.json'),'utf8'))
const manifest=JSON.parse(await fs.readFile(path.join(privateDir,'dataset.json'),'utf8'))
let ready=false
for(let attempt=0;attempt<50;attempt++){
  try{ready=(await fetch('http://localhost:18001/health',{signal:AbortSignal.timeout(1000)})).ok}catch{}
  if(ready)break
  await new Promise(resolve=>setTimeout(resolve,200))
}
assert(ready,'Native backend startup has no health completion evidence')
let report={status:'RUNNING',mode:'api',browser:'installed Microsoft Edge',gates:{},requests:[],missingUi:['PDF download'],unverifiedUi:['mapping/preview/confirm/commit']}
const remaining=process.argv.includes('--history-only')
const resumePlanning=process.argv.includes('--planning-history-only')
let retainedLocator=null
if(remaining||resumePlanning){
  report=JSON.parse(await fs.readFile(path.join(privateDir,'browser.json'),'utf8'))
  assert(report.gates.UI_analyze_seal_native_worker_polling==='PASS')
  if(resumePlanning){
    assert(report.gates.UI_C01_R01_planning_setup==='PASS')
    retainedLocator=report.requests.findLast(r=>/^\/api\/v1\/procurement-plans\/[^/]+$/.test(r.path))?.path.split('/').at(-1)
    assert(retainedLocator)
  }
  report.previousFailures=[...(report.previousFailures??[]),report.failure].filter(Boolean)
  delete report.failure;report.status='RUNNING'
}
const browser=await chromium.launch({channel:'msedge',headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true})
const page=await context.newPage()
page.setDefaultTimeout(20000)
page.on('response',r=>{
  if(r.url().startsWith('http://localhost:18001/'))report.requests.push({method:r.request().method(),path:new URL(r.url()).pathname,status:r.status()})
})
const errors=[]
page.on('pageerror',error=>errors.push(error.name))
async function passed(name){
  report.gates[name]='PASS'
  await fs.writeFile(path.join(privateDir,'browser.json'),JSON.stringify(report,null,2))
  console.log(`${name}: PASS`)
}
async function screenshot(name){await page.screenshot({path:path.join(privateDir,name+'.png'),fullPage:true})}
try{
  await page.goto('http://localhost:5173/login')
  await page.locator('#auth-email').fill(accounts.owner.email)
  await page.locator('#auth-password').fill(accounts.owner.password)
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click()
  await page.waitForURL('**/imports')
  await page.getByRole('link',{name:'Menu',exact:true}).waitFor()
  await page.locator('#import-data-date').waitFor()
  const cookies=await context.cookies('http://localhost:18001')
  const cookie=cookies.find(c=>c.name==='shelfcash_dev_session')
  assert(cookie?.httpOnly && cookie.sameSite==='Lax' && !cookie.secure)
  assert(report.requests.some(r=>r.path==='/api/v1/auth/login'&&r.status===200))
  assert(report.requests.some(r=>r.path==='/api/v1/auth/me'&&r.status===200))
  assert(report.requests.some(r=>r.path===`/api/v1/stores/${manifest.store_id}`&&r.status===200))
  await passed('UI_login_A03_Store_cookie_CORS')
  await page.goto('http://localhost:5173/store')
  const selector=page.locator('.store-page-selector select')
  await selector.waitFor()
  await selector.selectOption(manifest.store_id)
  assert.equal(await selector.inputValue(),manifest.store_id)
  const refreshStore=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/stores/${manifest.store_id}`&&r.status()===200)
  await page.getByRole('button',{name:'Đọc lại cửa hàng và quyền hiện hành',exact:true}).click()
  await refreshStore
  await passed('UI_Store_selector_current_T01_T02')
  await page.goto('http://localhost:5173/imports')
  await page.locator('#import-data-date').waitFor()
  if(!remaining&&!resumePlanning){
    await page.reload()
    await page.getByRole('link',{name:'Menu',exact:true}).waitFor()
    await passed('UI_reload_retains_session')
    await page.getByRole('link',{name:'Menu',exact:true}).click()
    await page.waitForURL('**/menu')
    await page.getByText('Cà phê demo 1',{exact:true}).waitFor()
    await screenshot('browser-menu')
    assert(report.requests.some(r=>r.path.endsWith('/products')&&r.status===200))
    await passed('UI_Menu_real_catalog')
    await page.getByRole('link',{name:'Kho',exact:true}).click()
    await page.waitForURL('**/inventory')
    await page.getByText('Sữa demo',{exact:true}).waitFor()
    await screenshot('browser-inventory')
    assert(report.requests.some(r=>r.path.endsWith('/inventory')&&r.status===200))
    await passed('UI_inventory_real_stock')
    await page.getByRole('link',{name:'Nhập dữ liệu',exact:true}).click()
    await page.waitForURL('**/imports')
    await page.locator('#import-data-date').fill(manifest.anchor_date)
    const csv=`sales.product_id,sales.sales_date,sales.quantity,sales.unit,sales.business_report_key\n${manifest.products[0]},${manifest.anchor_date},0,cup,S411-browser\n`
    await page.locator('input[type=file]').setInputFiles([
      {name:'browser-one.csv',mimeType:'text/csv',buffer:Buffer.from(csv)},
      {name:'browser-two.csv',mimeType:'text/csv',buffer:Buffer.from(csv.replace(manifest.products[0],manifest.products[1]))},
    ])
    await page.getByRole('button',{name:'Tạo lô và tải file',exact:true}).click()
    await page.getByRole('button',{name:'Xử lý dữ liệu',exact:true}).waitFor({state:'visible'})
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Xử lý dữ liệu'&&!b.disabled))
    await screenshot('browser-upload')
    assert(report.requests.some(r=>r.path.endsWith('/files')&&r.status===200))
    await passed('UI_multifile_upload_I01_I02_I04_CSRF')
    await page.getByRole('button',{name:'Xử lý dữ liệu',exact:true}).click()
    await page.getByRole('checkbox',{name:'Tôi đã xem các biên nhận bị từ chối và xác nhận phân tích toàn bộ file đã nhận.'}).check()
    await page.getByRole('button',{name:'Khóa tập file và phân tích',exact:true}).click()
    await page.getByText('Đã kết thúc bước phân tích.',{exact:false}).waitFor({timeout:90000})
    await screenshot('browser-analysis')
    assert(report.requests.some(r=>r.path.endsWith('/analyze')&&r.status===202))
    await passed('UI_analyze_seal_native_worker_polling')
  }
  if(!remaining){
    await page.goto('http://localhost:5173/forecast/planning'+(retainedLocator?'?plan_id='+retainedLocator:''))
    if(!resumePlanning){
    await page.getByRole('button',{name:'Tạo kế hoạch nhập hàng',exact:true}).waitFor()
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Tạo kế hoạch nhập hàng'&&!b.disabled))
    await passed('UI_C01_R01_planning_setup')
    await page.getByRole('button',{name:'Tạo kế hoạch nhập hàng',exact:true}).click()
    }
    await page.getByRole('button',{name:'Xem lý do từ engine',exact:true}).waitFor({timeout:180000})
    await page.getByRole('tab',{name:'Nguyên liệu',exact:true}).click()
    await page.locator('.sc-proc-ingredient-row').first().waitFor()
    await page.locator('.sc-proc-ingredient-row').first().click()
    await page.getByRole('tab',{name:'Tổng quan',exact:true}).click()
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Xem lý do từ engine'&&!b.disabled))
    await page.getByRole('button',{name:'Xem lý do từ engine',exact:true}).click()
    await page.getByText('Đang đọc…',{exact:true}).waitFor({state:'hidden'})
    await screenshot('browser-planning')
    assert(report.requests.some(r=>r.method==='POST'&&r.path.endsWith('/procurement-plans')&&r.status===202))
    for(const suffix of ['/ingredients','/ingredients/'+manifest.ingredient_id,'/explanation']){
      assert(report.requests.some(r=>r.path.endsWith(suffix)&&r.status===200))
    }
    await passed('UI_C02_C03_C04_C05_C08_planning_retained')
  }
  await page.goto('http://localhost:5173/imports/history')
  await page.locator('.history-calendar__day--active').first().waitFor()
  const date=manifest.anchor_date.split('-').reverse().join('/')
  await page.getByRole('link',{name:new RegExp('^'+date+',')}).click()
  await page.locator('.history-batch').first().waitFor()
  await screenshot('browser-history')
  assert(report.requests.some(r=>r.path.endsWith('/imports/calendar')&&r.status===200))
  await passed('UI_H01_H02_actual_uploaded_history')
  await page.getByRole('button',{name:'Đăng xuất',exact:true}).click()
  await page.waitForURL('**/login')
  assert(report.requests.some(r=>r.path==='/api/v1/auth/logout'&&r.status===204))
  await passed('UI_logout_real_204')
  await page.locator('#auth-email').fill(accounts.staff.email)
  await page.locator('#auth-password').fill(accounts.staff.password)
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click()
  await page.waitForURL(url=>url.pathname.startsWith('/imports'))
  const denied=page.waitForResponse(r=>r.url().includes('/inventory')&&r.status()===403)
  await page.goto('http://localhost:5173/inventory')
  await denied
  await screenshot('browser-staff-denied')
  await page.getByRole('link',{name:'Menu',exact:true}).click()
  await page.getByText('Cà phê demo 1',{exact:true}).waitFor()
  await passed('UI_Staff_granted_Menu_inventory_denied')
  assert.equal(errors.length,0)
  report.status='PARTIAL';report.completedAt=new Date().toISOString()
  await fs.writeFile(path.join(privateDir,'browser.json'),JSON.stringify(report,null,2))
  console.log('Current UI browser gates passed; mapping continuation remains unverified and PDF UI is absent. S4.11 PARTIAL.')
}catch(error){
  report.status='FAILED';report.failure={name:error.name,stage:Object.keys(report.gates).at(-1)??'login'}
  await screenshot('browser-failure').catch(()=>{})
  await fs.writeFile(path.join(privateDir,'browser.json'),JSON.stringify(report,null,2))
  console.error('Browser gate failed:',error.name,'after',report.failure.stage)
  process.exitCode=1
}finally{
  await context.close();await browser.close()
}
