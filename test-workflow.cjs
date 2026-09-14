const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('只允许隔离测试');
let browser;
async function login(p,user='admin'){await p.goto(base+'/sitelog/');await p.locator('#login-user').fill(user);await p.locator('#login-pass').fill('Test-admin-initial-12345');await p.getByRole('button',{name:'登录',exact:true}).click();await p.waitForFunction(()=>Alpine.$data(document.body).draftOwner)}
const api=(p,url,payload)=>p.evaluate(async({url,payload})=>Alpine.$data(document.body).accountJSON(url,payload),{url,payload});
async function save(p){await p.getByRole('button',{name:'保存云端工程',exact:true}).click();await p.waitForFunction(()=>{const a=Alpine.$data(document.body);return !a.cloudBusy&&a.cloudMessage.startsWith('云端已保存')})}
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());await login(p);
 await p.evaluate(()=>Alpine.$data(document.body).copyLegacyProject('Legacy0'));assert.equal(await p.locator('#report-content img').count(),4);
 let createCalls=0,mediaCalls=0,blocked=true;
 await p.route('**/api/share/projects',async route=>{if(route.request().method()==='POST'&&createCalls++===0){await route.fetch();await route.abort('failed')}else await route.continue()});
 await p.route('**/api/share/projects/*/media',async route=>{mediaCalls++;if(blocked&&mediaCalls>=2)await route.abort('failed');else await route.continue()});
 await p.getByRole('button',{name:'保存云端工程',exact:true}).click();await p.waitForFunction(()=>{const a=Alpine.$data(document.body);return !a.cloudBusy&&a.uploadProgress.done>=1&&a.uploadPending});
 const pid=await p.evaluate(()=>Alpine.$data(document.body).cloudProjectId);assert.ok(pid);assert.equal((await api(p,'/projects')).total,1);
 // 刷新会丢失内存状态，保存点与服务器散列查询应恢复已完成照片。
 await p.reload();await p.waitForFunction(()=>Alpine.$data(document.body).draftRestored);assert.equal(await p.evaluate(()=>Alpine.$data(document.body).cloudProjectId),pid);
 blocked=false;await save(p);assert.equal((await api(p,'/projects')).total,1);assert.ok(await p.evaluate(()=>Alpine.$data(document.body).uploadProgress.reused>=1));
 const data=await api(p,'/projects/'+pid),media=data.body.images[0].mediaId;assert.equal(data.body.images.length+data.body.arrivalImages.length+data.body.finishImages.length+data.body.sopImages.length,4);
 const benchmark=await p.evaluate(async body=>{const a=Alpine.$data(document.body),sleep=ms=>new Promise(r=>setTimeout(r,ms));const photos=sitelogEditor.collections.flatMap(g=>body[g]);const request=async path=>{await sleep(100);return a.sessionRequest(path)};let start=performance.now();for(const photo of photos){const response=await request('/media/'+photo.mediaId);await a.fileToDataUrl(await response.blob())}const sequential=performance.now()-start;start=performance.now();const loaded=await a.hydrateSnapshot.call({allPhotos:()=>[],sessionRequest:request,fileToDataUrl:a.fileToDataUrl.bind(a)},JSON.parse(JSON.stringify(body)));const concurrent=performance.now()-start;return {photos:photos.length,injected_delay_ms:100,sequential_ms:Math.round(sequential),concurrent_ms:Math.round(concurrent),images_valid:sitelogEditor.collections.flatMap(g=>loaded[g]).every(p=>p.dataUrl.startsWith('data:image/'))}},data.body);assert.ok(benchmark.images_valid);fs.writeFileSync(path.join(out,'照片读取对照.json'),JSON.stringify(benchmark,null,2));
 const guest=await browser.newContext();assert.equal((await guest.request.get(base+'/api/share/media/'+media+'/thumbnail')).status(),401);
 const dctx=await browser.newContext({viewport:{width:390,height:844},isMobile:true}),other=await dctx.newPage();other.on('dialog',d=>d.accept());other.on('pageerror',e=>errors.push(e.message));await login(other,'reviewer');
 await other.evaluate(pid=>Alpine.$data(document.body).openCloudProject(pid),pid);await other.getByPlaceholder('项目名称',{exact:true}).fill('审核同事更新的项目名');await save(other);
 await p.locator('#images-container .node-card-desc').first().fill('本机核实后的说明');await p.getByRole('button',{name:'保存云端工程',exact:true}).click();await p.getByRole('dialog',{name:'修改冲突对比'}).waitFor();
 await p.evaluate(()=>{const a=Alpine.$data(document.body);for(const row of a.cloudConflict.rows)row.choice=row.path[0]==='images'&&row.path[2]==='desc'?'local':'remote'});
 await p.getByRole('button',{name:'保存选择后的新修订',exact:true}).click();await p.waitForFunction(()=>!Alpine.$data(document.body).cloudBusy&&!Alpine.$data(document.body).cloudConflict);
 const merged=await api(p,'/projects/'+pid);assert.equal(merged.body.meta.projectName,'审核同事更新的项目名');assert.equal(merged.body.images[0].desc,'本机核实后的说明');assert.ok((await api(p,'/projects/'+pid+'/changes')).items.length>=3);
 await p.evaluate(async()=>{const a=Alpine.$data(document.body);await a.listLocalDrafts();if(!a.localDraftItems.some(d=>d.key.includes('merge-backup')))throw Error('缺少合并前草稿')});
 // 使用合成 AI 候选，不产生上游费用；检查候选和人工修改分别留存。
 await p.evaluate(()=>{const a=Alpine.$data(document.body);a.proposeAI(a.images[0],{title:'AI 建议',desc:'照片说明需要现场核实',category:'框架施工',highlights:[],aiSource:{model:'合成模型'}});a.keepManualText()});await save(p);
 await p.getByRole('button',{name:'项目工作区',exact:true}).click();await p.getByRole('button',{name:'AI 质量反馈',exact:true}).click();await p.getByLabel('反馈照片',{exact:true}).selectOption(data.body.images[0].id);
 await p.getByPlaceholder('修改原因，例如将看不清的尺寸改为待核实').fill('AI 建议缺少现场细节');await p.getByPlaceholder('核实依据，例如实测记录、材料单据或现场复核').fill('合成验收依据，不用于事实评测');await p.getByRole('button',{name:'提交质量反馈',exact:true}).click();await p.waitForFunction(()=>Alpine.$data(document.body).feedbackItems.length===1);
 const feedback=(await api(p,'/projects/'+pid+'/feedback')).items[0];assert.equal((await api(p,'/projects/'+pid+'/feedback-export')).items.length,0);
 const self=await p.evaluate(async({pid,id})=>{try{await Alpine.$data(document.body).accountJSON('/projects/'+pid+'/feedback',{id,action:'approve',note:'自审'});return 200}catch(e){return e.status}},{pid,id:feedback.id});assert.equal(self,403);
 await other.evaluate(pid=>Alpine.$data(document.body).openCloudProject(pid),pid);await other.evaluate(()=>Alpine.$data(document.body).openFeedback());await other.getByPlaceholder('独立核实说明').fill('已核对合成测试的原建议与修改');await other.getByRole('button',{name:'核实通过',exact:true}).click();await other.waitForFunction(()=>Alpine.$data(document.body).feedbackItems[0]?.status==='approved');
 assert.equal((await api(p,'/projects/'+pid+'/feedback-export')).items.length,1);await other.screenshot({path:path.join(out,'手机独立审核.png')});
 await p.getByRole('button',{name:'关闭质量反馈',exact:true}).click();await p.getByPlaceholder('搜索项目、阶段或归档人').fill('审核同事');await p.getByRole('button',{name:'搜索工程',exact:true}).click();await p.waitForFunction(()=>Alpine.$data(document.body).projectItems.length===1);await p.getByRole('button',{name:'预览照片',exact:true}).click();await p.waitForFunction(()=>Alpine.$data(document.body).archiveGallery.length===4);await p.locator('[aria-label="照片预览"] img').first().evaluate(im=>im.decode());await p.screenshot({path:path.join(out,'档案照片预览.png')});
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'工作流验收.json'),JSON.stringify({passed:true,create_response_loss:true,interrupted_upload_refresh:true,no_duplicate_project:true,merge_both_devices:true,merge_backup:true,feedback_independent_review:true,archive_search:true,private_thumbnail:true,errors},null,2));console.log('通过：弱网刷新续传、响应丢失防重建、冲突选择、独立反馈审核、档案检索及缩略图权限。');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
