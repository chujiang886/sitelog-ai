const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{PNG}=require('pngjs'),jsQR=require('jsqr');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('仅允许隔离工程测试');let browser;
async function login(page){await page.goto(base+'/sitelog/');await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill('Test-admin-initial-12345');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).draftOwner===1)}
const results=[];
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true}),page=await context.newPage();page.on('dialog',d=>d.accept());const errors=[];page.on('pageerror',e=>errors.push(e.message));await login(page);
 const ids=await page.evaluate(async()=>{const a=Alpine.$data(document.body);return (await a.accountJSON('/list')).items.filter(x=>x.kind==='legacy').map(x=>x.id)});
 assert.equal(ids.length,2);
 for(let index=0;index<ids.length;index++){
  const id=ids[index];const before=await page.evaluate(async id=>{const r=(await Alpine.$data(document.body).accountJSON('/legacy/'+id)).record;return {html:r.html,snapshot:sitelogLegacy.convert(r)}},id);
  const groups=['images','arrivalImages','finishImages','sopImages'],count=groups.reduce((n,g)=>n+before.snapshot[g].length,0);assert.ok(count>0);
  await page.getByRole('button',{name:'分享管理',exact:false}).first().click();await page.getByRole('button',{name:'复制为新工程',exact:true}).first().waitFor();
  await page.evaluate(id=>Alpine.$data(document.body).copyLegacyProject(id),id);
  assert.equal(await page.evaluate(()=>Alpine.$data(document.body).allPhotos().length),count);
  assert.equal(await page.locator('#report-content img').count(),count);
  assert.equal(await page.evaluate(()=>Alpine.$data(document.body).cloudProjectId),'');
  const after=await page.evaluate(()=>Alpine.$data(document.body).snapshot());
  for(const group of groups)assert.deepEqual(after[group].map(p=>[p.title,p.desc,p.highlights,p.dataUrl]),before.snapshot[group].map(p=>[p.title,p.desc,p.highlights,p.dataUrl]));
  // 历史内容不能作为活动 HTML 执行；不支持的外部图片必须拒绝。
  const safety=await page.evaluate(html=>{const convert=html=>sitelogLegacy.convert({html,project:'安全测试'});let refused=false;try{convert(html.replace(/src="data:image[^\"]+"/,'src="https://example.invalid/x.jpg"'))}catch{refused=true}const snapshot=convert(html+'<script>window.legacyInjected=1</script>');const clean=sitelogEditor.sanitizeReport(snapshot.report);return {refused,script:clean.includes('<script>')}},before.html);assert.deepEqual(safety,{refused:true,script:false});
  let ai='未调用';
  if(process.env.TEST_REAL_AI==='1'||(process.env.TEST_REAL_AI==='second'&&index===1)){
    const original=await page.locator('#images-container .node-card-desc').first().innerText();await page.getByRole('button',{name:'重分析',exact:true}).first().click();
    await page.waitForFunction(()=>{const a=Alpine.$data(document.body);return a.aiCandidate||(!a.aiChecking&&!a.images.some(p=>p.analyzing)&&a.toast.msg.includes('识别失败'))},{},{timeout:150000});
    const state=await page.evaluate(()=>{const a=Alpine.$data(document.body);return {candidate:!!a.aiCandidate,error:a.toast.msg}});assert.ok(state.candidate,state.error);
    assert.equal(await page.locator('#images-container .node-card-desc').first().innerText(),original);
    await page.getByRole('button',{name:'保留当前内容',exact:true}).click();ai=process.env.TEST_AI_SOURCE==='replay'?'已捕获响应重放成功，原文未被覆盖':'真实照片单张识别成功，原文未被覆盖';
  }
  const first=page.locator('#images-container .node-card-desc').first();const manual=(await first.innerText())+'\n隔离测试补记';await first.fill(manual);
  await page.getByRole('button',{name:'保存云端工程',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).cloudMessage.startsWith('云端已保存'),{},{timeout:90000});
  const pid=await page.evaluate(()=>Alpine.$data(document.body).cloudProjectId);
  const device=await browser.newContext({viewport:{width:390,height:844},isMobile:true}),second=await device.newPage();second.on('dialog',d=>d.accept());await login(second);await second.evaluate(pid=>Alpine.$data(document.body).openCloudProject(pid),pid);
  assert.equal(await second.locator('#report-content img').count(),count);assert.equal(await second.locator('#images-container .node-card-desc').first().innerText(),manual);
  await page.getByRole('button',{name:'项目工作区',exact:true}).click();await page.getByRole('button',{name:'提交审核',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).cloudStatus==='review');await page.getByRole('button',{name:'审核通过',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).cloudStatus==='approved');await page.getByRole('button',{name:'发布分享码',exact:true}).click();await page.getByLabel('分享范围',{exact:true}).selectOption('code');await page.getByLabel('分享访问码',{exact:true}).fill('Trial123');await page.getByRole('button',{name:'✅ 确认完成，生成分享码',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).shareCardReady,{},{timeout:90000});
  const share=await page.evaluate(()=>Alpine.$data(document.body).shareResult);const download=page.waitForEvent('download');await page.getByRole('button',{name:'💾 保存分享卡',exact:true}).click();const card=await download,file=path.join(out,'工程'+(index+1)+'分享卡.png');await card.saveAs(file);const png=PNG.sync.read(fs.readFileSync(file)),qr=jsQR(new Uint8ClampedArray(png.data),png.width,png.height);assert.ok(qr);assert.equal(qr.data,share.url);
  const guest=await browser.newContext({viewport:{width:390,height:844},isMobile:true}),view=await guest.newPage();await view.goto(qr.data);await view.locator('#code').fill('Trial123');await view.getByRole('button',{name:'查看档案'}).click();await view.locator('#document').waitFor({state:'visible'});await view.frameLocator('#document').locator('img').first().waitFor({state:'attached'});assert.equal(await view.frameLocator('#document').locator('img').count(),count);
  const frame=view.frames().find(f=>f.url().includes('/document'));const loaded=await frame.evaluate(async()=>{const imgs=[...document.images];for(const im of imgs)im.loading='eager';return (await Promise.all(imgs.map(im=>im.decode().then(()=>true,()=>false)))).filter(Boolean).length});assert.equal(loaded,count);
  await page.evaluate(()=>{const a=Alpine.$data(document.body);a.shareDialogOpen=false;a.projectPanel=false;window.trialPrintHtml='';const append=document.body.appendChild.bind(document.body);document.body.appendChild=function(n){const result=append(n);if(n.tagName==='IFRAME')n.contentWindow.print=()=>{window.trialPrintHtml=n.contentDocument.documentElement.outerHTML};return result}});
  if(process.env.TEST_PDF==='1'){
    await page.getByRole('button',{name:'导出 PDF',exact:false}).first().click();await page.evaluate(()=>Alpine.$data(document.body).generatePDF());const html=await page.evaluate(()=>window.trialPrintHtml);assert.ok(html.includes('隔离测试补记'));
    const print=await context.newPage();await print.setContent(html);await print.emulateMedia({media:'print'});await print.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>{i.loading='eager';return i.decode()}))});await print.pdf({path:path.join(out,'工程'+(index+1)+'导出.pdf'),format:'A4',printBackground:true,preferCSSPageSize:true});
  }
  await page.evaluate(async sid=>Alpine.$data(document.body).accountJSON('/publication/'+sid+'/revoke',{}),share.id);await view.reload();await view.getByText('分享链接已失效',{exact:true}).waitFor();
  const originalHtml=await page.evaluate(async id=>(await Alpine.$data(document.body).accountJSON('/legacy/'+id)).record.html,id);assert.equal(originalHtml,before.html);
  results.push({sample:index+1,photos:count,groups:Object.fromEntries(groups.map(g=>[g,before.snapshot[g].length])),legacy_unchanged:true,qr_decoded:true,guest_photos_loaded:loaded,cloud_reopened:true,revocation:true,ai});console.log('工程 '+(index+1)+' 通过：'+count+' 张照片，复制、改稿、云端恢复、二维码、访客照片与撤回。');
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'历史工程流程验收.json'),JSON.stringify({passed:true,results,errors},null,2));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
