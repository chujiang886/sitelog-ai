const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('仅允许隔离监控验收');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/sitelog/');
  async function login(password){await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click()}
  await login('Test-admin-initial-12345');
  await page.locator('#password-current').fill('Test-admin-initial-12345');
  await page.locator('#password-next').fill('Test-monitor-ready-12345');
  await page.locator('#password-confirm').fill('Test-monitor-ready-12345');
  await page.getByRole('button',{name:'保存新密码',exact:true}).click();
  await login('Test-monitor-ready-12345');
  await page.locator('#login-user').waitFor({state:'hidden'});
  await page.evaluate(()=>Alpine.$data(document.body).openAdmin());
  const panel=page.getByRole('region',{name:'运行监控与告警'});
  await panel.getByText('网站就绪检查通过',{exact:true}).waitFor();
  await panel.getByText('未配置外部通知，仅在后台显示告警',{exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'监控正常-桌面.png')});
  const changed={ok:true,checked_at:1,level:'critical',metrics:{},notification:{configured:false,status:'未配置外部通知'},events:[],checks:[{id:'monitor',label:'监控采集',level:'critical',summary:'监控结果已过期，请检查采集任务'},{id:'xss',label:'安全显示',level:'warning',summary:'<img src=x onerror="window.monitorXss=true">'}]};
  await page.route('**/api/share/admin/operations',route=>route.fulfill({json:changed}));
  await page.getByRole('button',{name:'刷新运行状态',exact:true}).click();
  await panel.getByText('监控结果已过期，请检查采集任务',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.monitorXss),undefined);
  assert.equal(await panel.locator('img').count(),0);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(out,'监控异常-手机.png')});
  assert.equal(await panel.evaluate(e=>e.scrollWidth<=e.clientWidth+2),true);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'监控浏览器验收.json'),JSON.stringify({passed:true,normal:true,staleAlert:true,safeText:true,mobile:true},null,2));
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
