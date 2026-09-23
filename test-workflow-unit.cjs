const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const context={window:{},sitelogEditor:{collections:['images','arrivalImages','finishImages','sopImages']},URLSearchParams,setTimeout};vm.createContext(context);vm.runInContext(fs.readFileSync('workflow-client.js','utf8'),context);
const {differences,merge}=context.window.sitelogWorkflow;
const copy=x=>JSON.parse(JSON.stringify(x));
vm.runInContext(fs.readFileSync('project-client.js','utf8'),context);context.sitelogWorkflow=context.window.sitelogWorkflow;

test('保存期间继续编辑时停止审核发布，保留新文字',async()=>{
 const body={meta:{projectName:'原名称'},images:[],arrivalImages:[],finishImages:[],sopImages:[],report:'原正文'};let reviews=0;
 const app={...context.window.projectFeatures,accountUser:{id:1,role:'staff'},cloudProjectId:'project',cloudStatus:'draft',allPhotos:()=>[],markDraftDirty(){},loadProjectDetails:async()=>({owner:1}),snapshot:()=>copy(body),accountJSON:async()=>{reviews++},saveCloudProject:async()=>{const bodyKey=context.window.sitelogWorkflow.canonical(body);body.report='保存请求期间用户新输入';return {revision:1,bodyKey}}};
 await assert.rejects(app.prepareConfirmedProject(true),/内容有修改/);assert.equal(reviews,0);assert.equal(body.report,'保存请求期间用户新输入');
});

test('账号在保存等待期间切换时不得继续审核',async()=>{
 let calls=0;const app={...context.window.projectFeatures,accountUser:{id:1,role:'staff'},cloudProjectId:'project',allPhotos:()=>[],markDraftDirty(){},loadProjectDetails:async()=>({owner:1}),accountJSON:async()=>{calls++},saveCloudProject:async()=>{app.accountUser={id:2,role:'staff'};return {revision:1,bodyKey:''}}};
 await assert.rejects(app.prepareConfirmedProject(true),/账号或工程已切换/);assert.equal(calls,0);
});
test('合并要求逐项选择，保留两端不同修改和新增照片',()=>{
 const local={meta:{projectName:'本机名称'},images:[{id:'a',desc:'本机说明',mediaId:'m1'}],arrivalImages:[],finishImages:[],sopImages:[],report:'正文'},remote=copy(local);
 remote.meta.projectName='同事名称';remote.images[0].desc='同事说明';remote.images.push({id:'b',desc:'同事新增',mediaId:'m2'});
 const rows=differences(local,remote);assert.throws(()=>merge(local,remote,rows),/逐项选择/);
 for(const row of rows)row.choice=row.path[2]==='desc'?'local':'remote';
 const result=copy(merge(local,remote,rows));assert.equal(result.meta.projectName,'同事名称');assert.equal(result.images[0].desc,'本机说明');assert.equal(result.images[1].id,'b');assert.equal(remote.images[0].desc,'同事说明');
});
test('显式移除与顺序选择不生成重复照片，也不修改输入快照',()=>{
 const a={meta:{},images:[{id:'a'},{id:'b'}],arrivalImages:[],finishImages:[],sopImages:[],report:'A'},b=copy(a);b.images=[{id:'b'},{id:'c'}];b.report='B';const rows=differences(a,b);for(const row of rows)row.choice='remote';
 assert.deepEqual(copy(merge(a,b,rows)),b);assert.equal(a.images.length,2);
});
test('切换工程或账号时清除旧反馈和预览，迟到的旧账号查询不回填',async()=>{
 const features=context.window.workflowFeatures;
 const state={...features,feedbackItems:[{reason:'旧账号内容'}],archiveGallery:[{src:'旧照片'}],projectItems:[{title:'旧工程'}]};
 state.restoreProjectExtras(null);assert.equal(state.feedbackItems.length,0);assert.equal(state.archiveGallery.length,0);assert.equal(state.projectItems.length,0);
 let finish;state.accountUser={id:1};state.accountJSON=()=>new Promise(r=>finish=r);const pending=state.loadProjects();state.accountUser={id:2};finish({items:[{title:'迟到的旧工程'}],total:1});await pending;assert.equal(state.projectItems.length,0);
});

test('按门洞分组必须进冲突行，否则本地刚分好的框会被静默丢掉',()=>{
 // frames 原先不在 differences() 的比对范围内。冲突合并时 merge() 从远端整体
 // 克隆，于是本机刚把照片分好的门洞分组会被远端那份悄悄覆盖 —— 师傅看到的是
 // 「我明明分好了，怎么又乱回来了」。只对两个 1 对 1 阶段有意义，但一旦有意义
 // 就是整份留档的结构。
 const local={meta:{},images:[],arrivalImages:[],finishImages:[],sopImages:[],report:'正文',
   frames:[{id:'f1',label:'主卧窗',arrivalIds:[],nodeIds:['n1']}]};
 const remote=copy(local);remote.frames=[{id:'f1',label:'主卧窗',arrivalIds:[],nodeIds:[]}];
 const rows=differences(local,remote);
 const row=rows.find(r=>r.path[0]==='frames');
 assert.ok(row,'frames 不同必须产生一行，让用户明确选哪一份');
 assert.equal(row.label,'按门洞分组（1 对 1 阶段）');
 row.choice='local';
 const result=copy(merge(local,remote,rows));
 assert.deepEqual(result.frames,local.frames,'选本机时必须保留本机的分组');
 assert.equal(remote.frames[0].nodeIds.length,0,'不改远端入参');
});

test('老工程没有 frames 键时不产生冲突行（「键不存在」等同空数组）',()=>{
 // frames 是后加字段：老版本云端工程存下来的 body 里没有这个键，而新版本前端
 // 恒发空数组。若直接按 canonical 比对，师傅每次冲突都会多出一行「（此项不存在）
 // vs []」要选，纯属噪音。
 const local={meta:{},images:[],arrivalImages:[],finishImages:[],sopImages:[],report:'正文',frames:[]};
 const remote=copy(local);delete remote.frames;
 assert.equal(differences(local,remote).filter(r=>r.path[0]==='frames').length,0);
 assert.equal(differences(remote,local).filter(r=>r.path[0]==='frames').length,0);
 // 真有分组时两边都发数组，正常比对。
 const withFrames=copy(local);withFrames.frames=[{id:'f1',label:'主卧窗',arrivalIds:[],nodeIds:[]}];
 assert.equal(differences(withFrames,remote).filter(r=>r.path[0]==='frames').length,1);
});
