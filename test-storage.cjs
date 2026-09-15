const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
function context(){const c={window:{},atob,Blob,Uint8Array,clearTimeout,setTimeout,crypto:require('node:crypto').webcrypto,fetch(){throw Error('禁止网络读取照片')}};vm.createContext(c);vm.runInContext(fs.readFileSync('editor-state.js','utf8'),c);return c;}
test('本地照片转换不发网络请求并保持字节及类型',async()=>{
 const c=context(),bytes=Buffer.from(Array.from({length:4096},(_,i)=>i%256));
 for(const type of ['png','jpeg','webp']){const blob=c.window.sitelogEditor.photoBlob('data:image/'+type+';base64,'+bytes.toString('base64'));assert.equal(blob.type,'image/'+type);assert.deepEqual(Buffer.from(await blob.arrayBuffer()),bytes);}
 assert.throws(()=>c.window.sitelogEditor.photoBlob('https://example.com/photo.jpg'),/照片数据格式/);
});
test('持续保存失败只提示一次，保留脏标记且明确显示容量错误',async()=>{
 const c=context();c.indexedDB={open(){const req={};setTimeout(()=>{req.error=Object.assign(Error('quota'),{name:'QuotaExceededError'});req.onerror()},0);return req;}};
 const app={...c.window.editorFeatures,draftOwner:1,draftDirty:true,draftStorageKey:'test',snapshot(){return {images:[],arrivalImages:[],finishImages:[],sopImages:[]}},showToast(){this.toasts=(this.toasts||0)+1}};
 assert.equal(await app.saveLocalDraft(),false);assert.equal(await app.saveLocalDraft(),false);assert.equal(app.toasts,1);assert.equal(app.draftDirty,true);assert.equal(app.draftWriting,false);assert.match(app.draftStatus,/空间不足/);
});
