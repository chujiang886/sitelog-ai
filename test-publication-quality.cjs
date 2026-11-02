const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const ctx={window:{}};vm.createContext(ctx);
// 生产模块必须真实执行，不以搜索源码代替行为验证。
const source=fs.existsSync(__dirname+'/publication-quality.js')?fs.readFileSync(__dirname+'/publication-quality.js','utf8'):'';
vm.runInContext(source,ctx);
test('未知拍摄时间不能用旧整理时间冒充',()=>{
 assert.ok(ctx.window.sitelogPublication);
 const text=ctx.window.sitelogPublication.photoDate({time:'2026/10/15 16:40:54'});
 assert.match(text,/拍摄时间：未提供/);assert.match(text,/整理时间.*2026\/10\/15/);
});
test('人工确认绑定标题正文亮点，任一修改后失效',()=>{
 const q=ctx.window.sitelogPublication,p={title:'基面处理',desc:'喷水湿润',stage:'准备',highlights:['喷水']};
 q.confirmPhoto(p);assert.equal(q.reviewCurrent(p),true);
 p.desc='吹风清理';assert.equal(q.reviewCurrent(p),false);
});
test('阶段成果不等于整体验收或结清',()=>{
 const q=ctx.window.sitelogPublication;
 assert.equal(q.finishLabel('框架施工'),'框架施工 · 本阶段成果照片');
 assert.equal(q.finishLabel('售后保养'),'售后保养 · 本阶段成果照片');
});
test('AI确定性结论不直接写入照片正文',()=>{
 vm.runInContext(fs.readFileSync(__dirname+'/ai-vision-client.js','utf8'),ctx);
 const photo={title:'人工标题',desc:'人工原记录',highlights:['人工要点']};
 ctx.window.aiVisionFeatures.applyAnalysisResult.call({},photo,{title:'填充完成',desc:'腔体全断面填充，符合标准',highlights:['增强结构强度']},'test');
 assert.equal(photo.desc,'人工原记录');
 assert.match(photo.aiError,/人工核实/);
});

test('真实模板发布清理仅移除内部指导与空照片分区，保留施工信息和照片',async()=>{
 const {chromium}=require('playwright');
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME || (fs.existsSync(chromium.executablePath()) ? chromium.executablePath() : undefined),channel:!process.env.TEST_CHROME&&!fs.existsSync(chromium.executablePath())?'chrome':undefined});
 try{
  const page=await browser.newPage();
  await page.addScriptTag({path:__dirname+'/templates.js'});
  await page.addScriptTag({path:__dirname+'/publication-quality.js'});
  const results=await page.evaluate(()=>Object.entries(TEMPLATES).map(([name,template])=>{
   if(typeof template!=='function')return null;
   const root=document.createElement('div');root.innerHTML=template();
   const record=document.createElement('div');record.innerHTML='<p>建议100-200字标识牌重新固定，现场状态待核实</p><p>[待核实：窗框连接]</p><section class="pdf-section"><div class="pdf-section-header">班组离场 SOP</div><div class="pdf-sop-gallery"><p>电箱状态待核实</p></div></section><figure><img src="data:image/png;base64,AA=="><figcaption>施工照片（待补充说明）</figcaption></figure>';
   root.append(record);const original=root.innerHTML;
   sitelogPublication.clean(root);const once=root.innerHTML;sitelogPublication.clean(root);
   return {name,text:root.textContent,html:root.innerHTML,original,stable:once===root.innerHTML,empty:[...root.querySelectorAll('.pdf-section')].filter(s=>/班组进场|班组离场 SOP/.test(s.querySelector('.pdf-section-header')?.textContent||'')&&!s.querySelector('img')&&!s.querySelector('.pdf-sop-gallery')?.textContent.trim()).length};
  }).filter(Boolean));
  for(const r of results){
   assert.doesNotMatch(r.text,/建议\s*100-200\s*字[。.]|\[请(?:编辑|填写)|施工照片（待补充说明）/,r.name);
   assert.match(r.text,/建议100-200字标识牌重新固定，现场状态待核实/,r.name);
   assert.match(r.text,/\[待核实：窗框连接\]/,r.name);assert.match(r.text,/电箱状态待核实/,r.name);
   if(r.name==='frame')assert.match(r.text,/定期检查/,r.name);
   if(r.name==='glass')assert.match(r.text,/玻扇的日常使用与维护建议/,r.name);
   assert.match(r.html,/<img /,r.name);assert.equal(r.empty,0,r.name);assert.equal(r.stable,true,r.name);
   assert.match(r.original,/施工照片（待补充说明）/,r.name);
  }
 }finally{await browser.close()}
});
