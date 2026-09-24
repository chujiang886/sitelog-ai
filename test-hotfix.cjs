const {chromium}=require('playwright'),{PNG}=require('pngjs'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
(async()=>{
 const base=process.env.TEST_BASE;if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('仅允许隔离验收服务');
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let old=true;
  await page.route(base+'/sitelog/',r=>old?r.fulfill({contentType:'text/html',body:execFileSync('git',['show','58900dd24eb70d8e5c83012e12fcf2c1a1900408:index.html'],{encoding:'utf8',maxBuffer:2e6})}):r.continue());
  await page.route('**/sitelog/auth-client.js',r=>old?r.fulfill({contentType:'application/javascript',body:execFileSync('git',['show','58900dd24eb70d8e5c83012e12fcf2c1a1900408:auth-client.js'],{encoding:'utf8'})}):r.continue());
  await page.goto(base+'/sitelog/');
  await page.waitForFunction(()=>window.Alpine && Alpine.$data(document.body).showLogin);
  const password = process.env.TEST_ADMIN_PASSWORD || 'Test-admin-initial-12345';
  await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill(password);
  const loginRequests = [];
  page.on('request', request => { if (request.url().endsWith('/auth/login')) loginRequests.push(request.postData()); });
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.waitForTimeout(1000);
  if (await page.locator('#login-user').isVisible()) {
    const alert = await page.locator('[role=alert]').allInnerTexts();
    throw Error('旧页面登录失败: requests=' + JSON.stringify(loginRequests) + ' alerts=' + JSON.stringify(alert) + ' errors=' + JSON.stringify(errors));
  }
  await page.locator('#login-user').waitFor({state:'hidden'});
  const img=new PNG({width:128,height:128});img.data.fill(255);
  await page.locator('input[type=file]').first().setInputFiles({name:'保留照片.png',mimeType:'image/png',buffer:PNG.sync.write(img)});
  await page.locator('#report-content img').first().waitFor();await page.locator('#report-content [contenteditable=true]').first().fill('旧页面审核文字不得丢失');
  await page.evaluate(()=>{Alpine.$data(document.body).aiConfigured=false});
  const before=await page.locator('#report-content').innerHTML();old=false;
  await page.addScriptTag({path:'hotfix-ai.js'});await page.getByText('AI 已恢复，照片和审核文字均已保留，请点击 AI 一键整理。',{exact:true}).waitFor();
  assert.equal(await page.locator('#report-content').innerHTML(),before);
  const state=await page.evaluate(()=>{const a=Alpine.$data(document.body);return{configured:a.aiConfigured,provider:a.apiProvider,images:a.images.length,login:a.showLogin}});
  assert.deepEqual(state,{configured:true,provider:'tencent',images:1,login:false});assert.deepEqual(errors,[]);
  console.log('通过：真实 v5.0.0 旧页面无刷新更新，报告 DOM 完全相同，照片及登录保留，AI 在线恢复。');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
