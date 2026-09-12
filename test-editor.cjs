const {chromium}=require('playwright'),{PNG}=require('pngjs'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.TEST_BASE;if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('只允许隔离测试');
const out=process.env.TEST_OUTPUT;let browser;
async function ready(page){await page.waitForFunction(()=>{if(!window.Alpine)return false;const a=Alpine.$data(document.body);return a.draftOwner===1&&!a.draftLoading&&/已恢复|已就绪/.test(a.draftStatus)})}
async function login(page,password){await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click()}
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/sitelog/');await login(page,'Test-admin-initial-12345');
 await page.locator('#password-current').fill('Test-admin-initial-12345');await page.locator('#password-next').fill('Test-admin-ready-12345');await page.locator('#password-confirm').fill('Test-admin-ready-12345');await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.locator('#login-user').waitFor({state:'visible'});await login(page,'Test-admin-ready-12345');await ready(page);
 const image=new PNG({width:128,height:128});image.data.fill(200);for(let i=3;i<image.data.length;i+=4)image.data[i]=255;
 const file={name:'验收照片.png',mimeType:'image/png',buffer:PNG.sync.write(image)};
 await page.locator('input[type=file][accept="image/*"]').first().setInputFiles(file);await page.locator('#images-container .node-block').waitFor();
 await page.getByPlaceholder('节点标题...').fill('侧栏标题确实保存');await page.waitForFunction(()=>document.querySelector('#images-container h3')?.innerText==='侧栏标题确实保存');
 await page.locator('#images-container .node-card-desc').fill('人工审核的说明必须保留。');
 await page.getByRole('button',{name:'重分析',exact:true}).click();await page.getByRole('dialog',{name:'比较 AI 新建议'}).waitFor();
 assert.equal(await page.locator('#images-container .node-card-desc').innerText(),'人工审核的说明必须保留。');
 await page.getByRole('button',{name:'采用新建议',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#images-container .node-card-desc')?.innerText.includes('新的识别建议'));
 await page.getByRole('button',{name:'撤销上次操作',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#images-container .node-card-desc')?.innerText==='人工审核的说明必须保留。');
 await page.getByPlaceholder('项目名称',{exact:true}).fill('草稿恢复验收项目');await page.getByRole('button',{name:'保存本机草稿',exact:true}).click();await page.waitForFunction(()=>{const a=Alpine.$data(document.body);return !a.draftDirty&&!a.draftWriting&&a.draftRevision>0});
 await page.reload();await ready(page);await page.getByText('已恢复本机草稿',{exact:true}).waitFor();assert.equal(await page.getByPlaceholder('项目名称',{exact:true}).inputValue(),'草稿恢复验收项目');assert.equal(await page.locator('#images-container .node-block').count(),1);assert.equal(await page.locator('#images-container .node-card-desc').innerText(),'人工审核的说明必须保留。');
 await context.setOffline(true);await page.getByPlaceholder('项目名称',{exact:true}).fill('断网仍保存');await page.waitForFunction(()=>{const a=Alpine.$data(document.body);return !a.draftDirty&&!a.draftWriting});await context.setOffline(false);await page.reload();await ready(page);assert.equal(await page.getByPlaceholder('项目名称',{exact:true}).inputValue(),'断网仍保存');
 const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'导出工程包',exact:true}).click();const download=await downloadPromise;const pack=path.join(out,'验收工程包.sitelog.json');await download.saveAs(pack);assert.equal(JSON.parse(fs.readFileSync(pack)).images.length,1);
 let dialogs=0;page.on('dialog',async d=>{dialogs++;await d.accept()});
 await page.locator('select[x-model="templateType"]').selectOption('玻扇施工');await page.waitForFunction(()=>Alpine.$data(document.body).activeTemplate==='玻扇施工');assert.equal(await page.locator('#images-container .node-block').count(),1);
 await page.getByRole('button',{name:'撤销上次操作',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).templateType==='框架施工');assert.equal(await page.locator('select[x-model="templateType"]').inputValue(),'框架施工');
 await page.locator('input[type=file][accept=".json"]').setInputFiles(pack);await page.waitForFunction(()=>Alpine.$data(document.body).templateType==='框架施工');
 // 仅有进场照片也必须确认，且切换后保留。
 await page.evaluate(()=>{const a=Alpine.$data(document.body);a.arrivalImages=a.images.map(x=>({...x,section:'arrival'}));a.images=[];a.syncToReport()});
 const before=dialogs;await page.locator('select[x-model="templateType"]').selectOption('五金安装');await page.waitForFunction(()=>Alpine.$data(document.body).activeTemplate==='五金安装');assert.equal(dialogs,before+1);await page.locator('#arrival-gallery .node-block').waitFor();assert.equal(await page.locator('#arrival-gallery .node-block').count(),1);
 await page.getByRole('button',{name:'保存本机草稿',exact:true}).click();await page.waitForFunction(()=>!Alpine.$data(document.body).draftWriting);
 const second=await context.newPage();await second.goto(base+'/sitelog/');await ready(second);await second.getByPlaceholder('项目名称',{exact:true}).fill('第二窗口更新');await second.waitForFunction(()=>!Alpine.$data(document.body).draftDirty&&!Alpine.$data(document.body).draftWriting);
 await page.getByPlaceholder('项目名称',{exact:true}).fill('第一窗口旧版不能覆盖');await page.waitForFunction(()=>Alpine.$data(document.body).draftConflict);assert.ok((await page.getByRole('status').innerText()).includes('另一个窗口'));
 assert.deepEqual(errors,[]);await page.screenshot({path:path.join(out,'编辑草稿回归.png'),fullPage:false});
 fs.writeFileSync(path.join(out,'编辑回归结果.json'),JSON.stringify({passed:true,flows:['侧栏标题','正文编辑','AI候选与撤销','刷新恢复','断网保存','工程包往返','所有分区模板保护','多窗口冲突'],errors},null,2));console.log('通过：编辑一致性、AI新旧对比与撤销、本机草稿恢复、断网保存、工程包往返、模板保护、多窗口冲突。');
})().catch(async error=>{console.error(error);if(browser)for(const c of browser.contexts())for(const p of c.pages())try{await p.screenshot({path:path.join(out,'编辑失败-'+Date.now()+'.png')})}catch{}process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
