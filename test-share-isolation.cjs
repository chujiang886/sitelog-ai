const {chromium}=require('playwright'),{PNG}=require('pngjs'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('仅允许隔离测试');let browser;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext(),page=await context.newPage();await page.goto(base+'/sitelog/');await page.locator('#login-user').fill('staff');await page.locator('#login-pass').fill('Test-admin-initial-12345');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForFunction(()=>{const a=window.Alpine&&Alpine.$data(document.body);return a?.draftOwner&&!a.draftHydrating});
 const api=(url,body)=>page.evaluate(({url,body})=>Alpine.$data(document.body).accountJSON(url,body),{url,body});
 const restored=await page.evaluate(()=>{const a=Alpine.$data(document.body);a.restoreField({customerTimeline:true});a.customerTimeline=true;return a.fieldSnapshot()});assert.equal(restored.customerTimeline,false);
 const project=await api('/projects',{title:'客户甲'}),versions=[];
 for(const [i,title] of ['客户甲','客户乙','客户丙'].entries()){
  const png=new PNG({width:64,height:64});png.data.fill(50+i*70);for(let n=3;n<png.data.length;n+=4)png.data[n]=255;
  const media=await api('/projects/'+project.id+'/media',{dataUrl:'data:image/png;base64,'+PNG.sync.write(png).toString('base64'),filename:'合成施工照片.png'});
  const body={format:'sitelog-project',schema:1,meta:{projectName:title,templateType:'玻扇施工'},report:'<h1>'+title+'</h1><p>'+title+'已确认内容</p><img data-photo-ref="photo">',css:'',images:[{id:'photo',mediaId:media.id}],arrivalImages:[],finishImages:[],sopImages:[],field:{customerTimeline:true}};
  await api('/projects/'+project.id+'/draft',{revision:i,body});for(const decision of ['submit','approve'])await api('/projects/'+project.id+'/review',{revision:i+1,decision});
  const share=await api('/projects/'+project.id+'/publish',{revision:i+1,idempotency:'isolation-customer-'+i,audience:'public',html:body.report});versions.push({share,media,title});
 }
 const guest=await browser.newContext({viewport:{width:390,height:844},isMobile:true,deviceScaleFactor:2}),view=await guest.newPage();const errors=[];view.on('pageerror',e=>errors.push(e.message));
 for(const item of versions){
  await view.goto(item.share.url);await view.locator('#document').waitFor({state:'visible'});await view.frameLocator('#document').getByText(item.title+'已确认内容',{exact:true}).waitFor();
  assert.equal(await view.locator('nav').count(),0);assert.equal(await view.locator('a[href^="/s/"]').count(),0);
  const root=base+'/api/share/publication/'+item.share.id,metadata=await(await guest.request.get(root)).json();assert.equal(metadata.title,item.title);assert.equal('stages' in metadata,false);
  const document=await(await guest.request.get(root+'/document')).text();
  for(const other of versions.filter(x=>x!==item)){assert.equal(JSON.stringify(metadata).includes(other.share.id),false);assert.equal(document.includes(other.title),false);assert.equal((await guest.request.get(root+'/media/'+other.media.id)).status(),403)}
  const f=view.frames().find(f=>f.url().includes('/document'));assert.equal(await f.evaluate(async()=>{await Promise.all([...document.images].map(i=>i.decode()));return document.images[0].naturalWidth>0}),true);
 }
 for(const suffix of ['/projects','/projects/'+project.id,'/archives','/list'])assert.equal((await guest.request.get(base+'/api/share'+suffix)).status(),401);
 assert.equal((await api('/projects/'+project.id)).versions.length,3);assert.deepEqual(errors,[]);
 await view.screenshot({path:path.join(out,'客户扫码单版本.png')});fs.writeFileSync(path.join(out,'扫码隔离验收.json'),JSON.stringify({passed:true,customers:3,legacyTimelineTrue:true,noHistoryLinks:true,noRelatedIdsInAPI:true,foreignMediaBlocked:true,internalHistoryRetained:true,errors},null,2));console.log('通过：三个不同客户复用工程，旧时间线开启时仍仅展示当前二维码内容，接口与照片权限隔离。');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});

