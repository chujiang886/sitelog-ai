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
