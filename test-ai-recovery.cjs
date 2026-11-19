const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('仅允许隔离数据库测试');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/sitelog/');
  async function login(password){await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click()}
  await login('Test-admin-initial-12345');await page.locator('#password-current').fill('Test-admin-initial-12345');await page.locator('#password-next').fill('Test-admin-ready-12345');await page.locator('#password-confirm').fill('Test-admin-ready-12345');await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.locator('#login-user').waitFor({state:'visible'});await login('Test-admin-ready-12345');await page.waitForFunction(()=>Alpine.$data(document.body).draftOwner===1);
  let submitted=0,cancelled=0,polls=0; const ids=new Set();
  await page.route('**/api/share/ai/jobs**',async route=>{
   const req=route.request(),url=req.url();if(url.endsWith('/cancel'))cancelled++;else if(req.method()==='POST')submitted++;
   if(req.method()==='GET'){
    ids.add(url);polls++;
    if(polls===1)return route.abort('timedout');
    if(polls>15)return route.fulfill({json:{ok:true,id:'test-job',status:'succeeded',result:{items:Array.from({length:2},()=>({title:'现场记录',desc:'照片可见窗框'}))}}});
   }
   await route.fulfill({json:{ok:true,id:'test-job',status:'queued'}});
  });
  const result=await page.evaluate(async()=>{
   const a=Alpine.$data(document.body);a.aiWaitTimeoutMs=250;a.aiRequestTimeoutMs=100;a.aiPollIntervalMs=20;
   const canvas=document.createElement('canvas');canvas.width=20;canvas.height=20;const dataUrl=canvas.toDataURL();
   a.images=Array.from({length:2},(_,i)=>({id:'test-'+i,section:'construction',dataUrl,title:'施工节点',desc:'原内容',highlights:[]}));a.arrivalImages=[];a.finishImages=[];
   const pending=a.aiOrganizeAll();await new Promise(r=>setTimeout(r,100));a.images[0].desc='等待期间人工修改';a.images[0]._manual={desc:true};await pending;
   return {processing:a.processing,checking:a.aiChecking,job:a.aiJobId,photos:a.images.length,manual:a.images[0].desc,remaining:a.images[1].desc,analyzing:a.images.some(p=>p.analyzing),error:a.images[1].aiError,toast:a.toast.msg};
  });
  assert.equal(result.processing,false);assert.equal(result.checking,false);assert.equal(result.job,'');assert.equal(result.photos,2);assert.equal(result.manual,'等待期间人工修改');assert.equal(result.remaining,'照片可见窗框');assert.equal(result.analyzing,false);assert.equal(submitted,1);assert.equal(cancelled,0);assert.equal(ids.size,1);assert.ok([...ids][0].endsWith('/ai/jobs/test-job'));assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(out,'ai-timeout-recovery.png'),fullPage:true});fs.writeFileSync(path.join(out,'recovery.json'),JSON.stringify({result,submitted,cancelled,pageErrors:errors},null,2));console.log('通过：原页面查询遇到网络故障并跨过等待上限，原任务自动回填，保留人工修改。');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
