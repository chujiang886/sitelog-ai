const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const html=fs.readFileSync('index.html','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
for(const source of scripts)new vm.Script(source[1]);
function makeApp(fetch){
 const context={window:{},fetch,console:{...console,error(){}},confirm:()=>true,setTimeout,clearTimeout};
 vm.createContext(context);vm.runInContext(fs.readFileSync('auth-client.js','utf8'),context);vm.runInContext(scripts.at(-1)[1],context);
 const app=context.siteLogApp();app.showToast=()=>{};return app;
}

test('推理区中的示例 JSON 不能覆盖模型最终结果',()=>{
 const app=makeApp();const example=JSON.stringify({title:'推理中的草稿',category:'框架施工',desc:'短草稿',highlights:[]});
 const final=JSON.stringify({title:'玻扇安装记录',category:'玻扇施工',desc:'玻扇位于框体内，边缘压线和接缝可见；实际尺寸及紧固状态需要结合现场测量核实。',highlights:['接缝待核实']});
 const result=app.extractJSONRobust('<think>'+example+'</think>'+final);
 assert.equal(result.title,'玻扇安装记录');assert.ok(result.desc.includes('现场测量核实'));assert.ok(!result._raw.includes('短草稿'));
 assert.equal(app.extractJSONRobust('<think>'+example)._noJson,true);
});

test('截断返回即使包含完整 JSON 也不能当作完成结果',async()=>{
 const app=makeApp();app.runAIJob=async()=>({choices:[{finish_reason:'length',message:{content:'{"desc":"这是一个看似完整但整条结果被截断的工程记录。"}'}}]});
 await assert.rejects(app.callVisionAPI('data:image/png;base64,AA==','测试'),/截断/);
});

test('识别失败期间的人工编辑不会被错误占位文字覆盖',async()=>{
 const app=makeApp();app.ensureCompanyAI=async()=>true;app.syncToReport=()=>{};
 app.images=[{id:'a',title:'原始节点',desc:'待整理',highlights:[]}];
 app.analyzeImage=async()=>{app.images[0].desc='识别等待期间人工输入的记录';app.images[0]._manual={desc:true};throw Error('上游中断')};
 await app.aiOrganizeAll();assert.equal(app.images[0].desc,'识别等待期间人工输入的记录');assert.equal(app.images[0].title,'原始节点');assert.equal(app.images[0].aiError,'上游中断');
});
test('分享请求使用同站点会话和 CSRF，不发送旧分享凭据',async()=>{
 let request;const app=makeApp(async(url,options)=>{request={url,options};return{status:200}});app.csrf='test-csrf';
 await app.shareRequest('',{method:'POST',body:'{}'});
 assert.equal(request.url,'/api/share');assert.equal(request.options.credentials,'same-origin');assert.equal(request.options.headers['X-CSRF-Token'],'test-csrf');assert.equal(request.options.headers['X-Share-Token'],undefined);
});
test('会话过期打开登录面板并保留人工审核内容',async()=>{
 const app=makeApp(async()=>({status:401}));app.images=[{desc:'已审核'}];app.accountUser={id:1};
 await assert.rejects(app.shareRequest('/list'),/重新登录/);assert.equal(app.showLogin,true);assert.equal(app.images[0].desc,'已审核');
});
test('已审核版本发布成功且绘制完成后才报告成功',async()=>{
 const calls=[];const app=makeApp(async(url,options)=>{calls.push(url);return{status:200,ok:true,json:async()=>({ok:true,id:'ABC234',url:'https://cj-az.cn/s/ABC234'})}});
 app.images=[{}];app.syncCoverMeta=()=>{};app.buildSharePayload=async()=>({html:'<p>审核记录</p>'});app.$nextTick=async()=>{};
 app.publishCloudProject=()=>app.accountJSON('/projects/test/publish',{});
 let drawn;app.drawShareCard=(url)=>drawn=url;await app.doShare();assert.deepEqual(calls,['/api/share/projects/test/publish']);assert.equal(drawn,'https://cj-az.cn/s/ABC234');assert.equal(app.shareCardReady,true);
});
// 注意 retryShareCard / drawShareCard 是 async：必须 await，否则断言跑在置位之前。
// 2026-09-21 把它们从同步改成 async（doShare 需要 await 绘制结果）时漏改了这里的 await，
// 导致 CI 从那天起一直红。加 await 前请先确认产品代码里这两个方法还是 async。
test('二维码失败保留链接，重绘不会再次上传',async()=>{
 let posts=0;const app=makeApp(async(url,options)=>{if(options.method==='POST')posts++;return{status:200,ok:true,json:async()=>({ok:true,id:'ABC234',url:'https://cj-az.cn/s/ABC234'})}});
 app.images=[{}];app.syncCoverMeta=()=>{};app.buildSharePayload=async()=>({html:'<p>审核记录</p>'});app.$nextTick=async()=>{};app.drawShareCard=()=>{throw Error('绘制失败')};
 app.publishCloudProject=()=>app.accountJSON('/projects/test/publish',{});
 await app.doShare();assert.equal(app.shareCardReady,false);assert.match(app.shareError,/链接已创建/);app.drawShareCard=()=>{};await app.retryShareCard();assert.equal(app.shareCardReady,true);assert.equal(posts,1);
});
test('员工页面不包含分享配置导入和直接 AI 密钥请求',()=>{
 assert.ok(!html.includes('importShareConfig'));assert.ok(!html.includes('X-Share-Token'));assert.ok(!html.includes("authHeader: 'Bearer '"));
});

test('已打开的员工页面在配置完成后即时恢复，保留照片和人工审核内容',async()=>{
 const app=makeApp(async()=>({status:200,ok:true,json:async()=>({ok:true,user:{id:3,display_name:'员工'},csrf:'fresh-csrf',ai:{configured:true,provider:'tencent'}})}));
 app.accountUser={id:3};app.aiConfigured=false;app.images=[{desc:'人工审核内容',_analyzed:true}];app.reportHtml='<p>未保存的报告</p>';
 await app.aiOrganizeAll();
 assert.equal(app.aiConfigured,true);assert.equal(app.apiProvider,'tencent');assert.equal(app.csrf,'fresh-csrf');
 assert.equal(app.images[0].desc,'人工审核内容');assert.equal(app.reportHtml,'<p>未保存的报告</p>');assert.equal(app.showLogin,false);
});

test('公司状态网络异常不清空内容、不误报退出登录，也不继续发送识别请求',async()=>{
 let requests=0;const app=makeApp(async()=>{requests++;throw Error('网络中断')});
 app.accountUser={id:3};app.aiConfigured=true;app.images=[{desc:'保留'}];
 await app.aiOrganizeAll();assert.equal(requests,1);assert.equal(app.showLogin,false);assert.equal(app.images[0].desc,'保留');assert.equal(app.aiChecking,false);
});

test('配置变更期间的重复点击只触发一次状态检查',async()=>{
 let resolve,requests=0;const app=makeApp(()=>{requests++;return new Promise(r=>resolve=r)});app.accountUser={id:3};
 const first=app.aiOrganizeAll();await app.aiOrganizeAll();assert.equal(requests,1);
 resolve({status:200,ok:true,json:async()=>({ok:true,user:{id:3},csrf:'fresh',ai:{configured:true,provider:'tencent'}})});await first;
});
