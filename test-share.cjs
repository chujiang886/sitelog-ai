const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const html=fs.readFileSync('index.html','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
for(const source of scripts)new vm.Script(source[1]);
function makeApp(fetch){
 const context={window:{},fetch,console:{...console,error(){}},confirm:()=>true,setTimeout,clearTimeout};
 vm.createContext(context);vm.runInContext(fs.readFileSync('auth-client.js','utf8'),context);vm.runInContext(scripts.at(-1)[1],context);
 const app=context.siteLogApp();app.showToast=()=>{};return app;
}
test('分享请求使用同站点会话和 CSRF，不发送旧分享凭据',async()=>{
 let request;const app=makeApp(async(url,options)=>{request={url,options};return{status:200}});app.csrf='test-csrf';
 await app.shareRequest('',{method:'POST',body:'{}'});
 assert.equal(request.url,'/api/share');assert.equal(request.options.credentials,'same-origin');assert.equal(request.options.headers['X-CSRF-Token'],'test-csrf');assert.equal(request.options.headers['X-Share-Token'],undefined);
});
test('会话过期打开登录面板并保留人工审核内容',async()=>{
 const app=makeApp(async()=>({status:401}));app.images=[{desc:'已审核'}];app.accountUser={id:1};
 await assert.rejects(app.shareRequest('/list'),/重新登录/);assert.equal(app.showLogin,true);assert.equal(app.images[0].desc,'已审核');
});
test('分享先检查会话，再上传，绘制完成后才报告成功',async()=>{
 const calls=[];const app=makeApp(async(url,options)=>{calls.push(url);return{status:200,ok:true,json:async()=>({ok:true,id:'ABC234',url:'https://cj-az.cn/s/ABC234'})}});
 app.images=[{}];app.syncCoverMeta=()=>{};app.buildSharePayload=async()=>({html:'<p>审核记录</p>'});app.$nextTick=async()=>{};
 let drawn;app.drawShareCard=(url)=>drawn=url;await app.doShare();assert.deepEqual(calls,['/api/share/list','/api/share']);assert.equal(drawn,'https://cj-az.cn/s/ABC234');assert.equal(app.shareCardReady,true);
});
test('二维码失败保留链接，重绘不会再次上传',async()=>{
 let posts=0;const app=makeApp(async(url,options)=>{if(options.method==='POST')posts++;return{status:200,ok:true,json:async()=>({ok:true,id:'ABC234',url:'https://cj-az.cn/s/ABC234'})}});
 app.images=[{}];app.syncCoverMeta=()=>{};app.buildSharePayload=async()=>({html:'<p>审核记录</p>'});app.$nextTick=async()=>{};app.drawShareCard=()=>{throw Error('绘制失败')};
 await app.doShare();assert.equal(app.shareCardReady,false);assert.match(app.shareError,/链接已创建/);app.drawShareCard=()=>{};app.retryShareCard();assert.equal(app.shareCardReady,true);assert.equal(posts,1);
});
test('员工页面不包含分享配置导入和直接 AI 密钥请求',()=>{
 assert.ok(!html.includes('importShareConfig'));assert.ok(!html.includes('X-Share-Token'));assert.ok(!html.includes("authHeader: 'Bearer '"));
});
