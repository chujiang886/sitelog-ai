const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function app(){
 const ctx={window:{},setTimeout,clearTimeout,AbortController,Date,console};vm.createContext(ctx);
 for(const file of ['auth-client.js','project-client.js','ai-vision-client.js'])vm.runInContext(fs.readFileSync(file,'utf8'),ctx);
 return {...ctx.window.accountFeatures,...ctx.window.projectFeatures,...ctx.window.aiVisionFeatures,
  aiWaitTimeoutMs:55,aiRequestTimeoutMs:15,aiPollIntervalMs:1};
}
test('永久排队和永久运行都有总等待上限，取消并清理忙碌标识',async()=>{
 for(const status of ['queued','running']){
  const a=app();let submits=0,cancels=0;
  a.accountJSON=async(path,payload)=>{if(path.endsWith('/cancel')){cancels++;return {status:'cancelled'}}if(payload){submits++;return {id:'job',status}}return {id:'job',status}};
  await assert.rejects(a.runAIBatch(['photo'],'prompt','model'),/等待超时/);
  assert.equal(a.aiJobId,'');assert.equal(a.aiJobStatus,'');assert.equal(submits,1);assert.equal(cancels,1);
 }
});
test('单次提交卡住也会超时并中止网络请求，不会自动重复提交',async()=>{
 const a=app();let submits=0,signal;
 a.accountJSON=(path,payload,options)=>{submits++;signal=options?.signal;return new Promise(()=>{})};
 await assert.rejects(a.runAIJob('photo','prompt','model'),/请求超时/);
 assert.equal(submits,1);assert.equal(signal.aborted,true);assert.equal(a.aiJobId,'');
});
test('取消请求也卡住时仍能结束等待',async()=>{
 const a=app();a.accountJSON=async(path,payload)=>path.endsWith('/cancel')?new Promise(()=>{}):{id:'job',status:'queued'};
 await assert.rejects(a.runAIJob('photo','prompt','model'),/等待超时/);
 assert.equal(a.aiJobId,'');
});
test('超时停止剩余批次并保留照片和人工内容',async()=>{
 const a=app();a.ensureCompanyAI=async()=>true;a.showToast=()=>{};a.syncToReport=()=>{};a.buildAnalysisPrompt=()=>'';let calls=0;
 a.arrivalImages=[];a.finishImages=[];
 a.images=Array.from({length:9},(_,i)=>({id:String(i),dataUrl:'data:image/png;base64,AA',title:'原题',desc:'原始内容',highlights:[]}));
 a.runAIBatch=async()=>{calls++;a.images[0].desc='等待期间人工编辑';a.images[0]._manual={desc:true};const e=Error('识别等待超时');e.code='AI_WAIT_TIMEOUT';throw e};
 await a.aiOrganizeAll();assert.equal(calls,1);assert.equal(a.processing,false);assert.equal(a.images.length,9);
 assert.equal(a.images[0].desc,'等待期间人工编辑');assert.equal(a.images[8].desc,'原始内容');assert.ok(a.images.every(p=>!p.analyzing));
});
test('成功结果只采用一次，正常服务不触发取消',async()=>{
 const a=app();a.accountJSON=async(path,payload)=>{assert.ok(!path.endsWith('/cancel'));return payload?{id:'job',status:'queued'}:{id:'job',status:'succeeded',result:{items:[{desc:'ok'}]}}};
 assert.equal((await a.runAIBatch(['photo'],'prompt','model')).items[0].desc,'ok');assert.equal(a.aiJobId,'');
});
test('accountJSON 将 AbortSignal 传给会话请求',async()=>{
 const a=app();const controller=new AbortController();let options;
 a.sessionRequest=async(path,o)=>{options=o;return {ok:true,json:async()=>({ok:true})}};
 await a.accountJSON('/ai/jobs',{}, {signal:controller.signal});assert.equal(options.signal,controller.signal);
});
test('轮询卡住会超时，保留任务取消机会且不重复提交',async()=>{
 const a=app();let posts=0,cancels=0;
 a.accountJSON=(path,payload)=>{if(path.endsWith('/cancel')){cancels++;return Promise.resolve({})}if(payload){posts++;return Promise.resolve({id:'job',status:'queued'})}return new Promise(()=>{})};
 await assert.rejects(a.runAIJob('photo','prompt','model'),/请求超时/);
 assert.equal(posts,1);assert.equal(cancels,1);assert.equal(a.aiJobId,'');
});
test('AbortSignal 导致 fetch 拒绝时仍报告明确超时',async()=>{
 const a=app();a.accountJSON=(p,b,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))));
 await assert.rejects(a.runAIJob('photo','prompt','model'),e=>e.code==='AI_REQUEST_TIMEOUT');
});
test('AI 配置预检查网络卡住时结束检查并保留照片',async()=>{
 const a=app();a.accountUser={id:1};a.images=[{desc:'人工内容'}];a.showToast=()=>{};
 a.accountJSON=()=>new Promise(()=>{});
 await a.aiOrganizeAll();assert.equal(a.aiChecking,false);assert.equal(a.images[0].desc,'人工内容');
});
