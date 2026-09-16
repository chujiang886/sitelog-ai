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
