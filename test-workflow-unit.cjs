const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const context={window:{},sitelogEditor:{collections:['images','arrivalImages','finishImages','sopImages']},URLSearchParams,setTimeout};vm.createContext(context);vm.runInContext(fs.readFileSync('workflow-client.js','utf8'),context);
const {differences,merge}=context.window.sitelogWorkflow;
const copy=x=>JSON.parse(JSON.stringify(x));
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
