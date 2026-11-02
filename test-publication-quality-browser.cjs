const {chromium}=require('playwright');
const {PNG}=require('pngjs');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base||''))throw Error('仅允许隔离测试环境');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME});
 try{
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}}),page=await ctx.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.stack||e.message));
 await page.goto(base+'/sitelog/');
 await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill('Test-admin-initial-12345');
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('#login-user').waitFor({state:'hidden'});
 const png=new PNG({width:64,height:64});png.data.fill(255);const data='data:image/png;base64,'+PNG.sync.write(png).toString('base64');
 await page.evaluate(data=>{
  const a=Alpine.$data(document.body);a.projectName='专项回归合成工程';a.archiveDate='2026-10-13';a.templateType='框架施工';
  a.images=[{id:'quality1',dataUrl:data,title:'IMG_001.jpg',desc:'现场记录待核实',category:'框架施工',highlights:['可见框体'],time:'2026/10/15 16:40:54'}];
  a.finishImages=[{id:'quality2',dataUrl:data,title:'本阶段框体留底',desc:'本阶段可见状态留底',highlights:[],time:'2026/10/15 16:39:33'}];a.syncToReport();
 },data);
 await page.locator('#images-container .node-card-desc').fill('已完成安全交底，符合标准');
 await page.getByText('文字已修改，请同步核对标题、正文和工艺亮点后重新确认',{exact:false}).first().waitFor();
 const denied=await page.evaluate(async()=>{try{await Alpine.$data(document.body).publishCloudProject();return ''}catch(e){return e.message}});
 assert.match(denied,/核实依据/);
 const publication=await page.evaluate(async()=>{const a=Alpine.$data(document.body);a.reviewNote='合成测试人工核对记录：此文字仅验证门禁，不代表真实工程';return await a.publishCloudProject()});
 const doc=await ctx.newPage();await doc.goto(base+'/api/share/publication/'+publication.id+'/document');
 const text=await doc.locator('body').innerText();
 for(const bad of ['添加照片','服务热线：待填写','发布时确认','IMG_001.jpg','最终交付照片','建议 100-200 字','[请编辑','施工照片（待补充说明）','班组进场','班组离场 SOP'])assert.ok(!text.includes(bad),bad);
 for(const good of ['本阶段成果照片','拍摄时间：未提供','历史整理时间','审核通过时间','发布时间'])assert.ok(text.includes(good),good);
 assert.ok(text.includes('本阶段可见状态留底'));assert.equal(await doc.locator('img').count()>=2,true);
 assert.match(await doc.locator('.node-card-meta').first().innerText(),/拍摄时间：未提供/);
 assert.equal(await doc.locator('[contenteditable],input,button,.sop-upload-zone').count(),0);
 await doc.screenshot({path:path.join(out,'new-publication-desktop.png'),fullPage:true});await doc.pdf({path:path.join(out,'new-publication.pdf'),format:'A4',printBackground:true});
 // 真实生成PDF使用的克隆DOM也必须清理，不能只验证服务器正文。
 const exported=await page.evaluate(async()=>await Alpine.$data(document.body).buildSharePayload());
 assert.ok(!exported.html.includes('待填写'));assert.ok(!exported.html.includes('添加照片'));
 const exportedText=await page.evaluate(html=>new DOMParser().parseFromString(html,'text/html').body.textContent,exported.html);
 for(const bad of ['建议 100-200 字','[请编辑','施工照片（待补充说明）','班组进场','班组离场 SOP'])assert.ok(!exportedText.includes(bad),bad);
 assert.ok(exported.html.includes('本阶段可见状态留底'));assert.ok(exported.html.includes('<img'));
 // 页面中的草稿仍保留指导，发布与导出只能清理克隆，不能改历史或编辑正文。
 assert.ok((await page.locator('#report-content').innerText()).includes('建议 100-200 字'));
 await doc.setViewportSize({width:390,height:844});await doc.screenshot({path:path.join(out,'new-publication-mobile.png')});
 assert.ok(await doc.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'手机正文不得横向溢出');
 const aid=await page.evaluate(async sid=>{const a=Alpine.$data(document.body);const address=await a.accountJSON('/addresses',{label:'专项回归合成地址'});await a.accountJSON('/addresses/'+address.id+'/attach',{stage_key:'框架施工',publication_id:sid});return address.id},publication.id);
 const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.50'});
 const mp=await mobile.newPage();await mp.goto(base+'/a/'+aid);await mp.waitForFunction(()=>document.getElementById('rail-note').textContent.includes('已归档'));
 assert.match(await mp.locator('#rail-note').innerText(),/已归档 1 个阶段/);
 assert.equal(await mp.locator('.rail').isVisible(),false);
 await mp.screenshot({path:path.join(out,'address-mobile-wechat-ua.png'),fullPage:true});
 if(process.env.TEST_REVIEW_SAMPLE){
  const sample=JSON.parse(fs.readFileSync(process.env.TEST_REVIEW_SAMPLE));
  await page.evaluate(async sample=>{await Alpine.$data(document.body).restoreSnapshot(sample);await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame)},sample);
  assert.equal(await page.evaluate(()=>Alpine.$data(document.body).allPhotos().length),29);
  const imported=await page.evaluate(()=>Alpine.$data(document.body).allPhotos().map(p=>({id:p.id,title:p.title,desc:p.desc,highlights:p.highlights,stage:p.stage})));
  const expected=['arrivalImages','images','finishImages','sopImages'].flatMap(key=>sample[key]||[]).map(p=>({id:p.id,title:p.title,desc:p.desc,highlights:p.highlights,stage:p.stage}));
  assert.deepEqual(imported.sort((a,b)=>a.id.localeCompare(b.id)),expected.sort((a,b)=>a.id.localeCompare(b.id)),'候选导入必须保留逐照标题、正文、亮点和待核实状态');
  assert.match(await page.locator('#report-content').innerText(),/纠错候选版/);
  await page.screenshot({path:path.join(out,'candidate-import-editor.png')});
 }
 assert.equal(errors.length,0,errors.join('\n'));
 fs.writeFileSync(path.join(out,'quality-browser-result.json'),JSON.stringify({ok:true,publication:publication.id,address:aid,checks:['人工依据门禁','编辑联动提醒','发布清理','版本日期','导出清理','手机微信UA布局'],wechatNative:false},null,2));
 console.log('通过：专项发布、人工依据、日期、导出和手机微信 UA 回归');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
