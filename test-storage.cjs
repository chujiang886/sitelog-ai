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

// ────────────────────────────────────────────────────────────────
// 草稿的「模板模式」：合规版正文不得被阶段编辑器恢复
// ────────────────────────────────────────────────────────────────
// 2026-11-05 实测：打开过 ?template=compliance 后，再进 /sitelog/ 会恢复那份
// 合规版草稿 —— complianceMode=false 但报告仍是五段，switchTemplate() 也切不回来。
// 修法：草稿记录里存 mode，恢复时与当前入口不一致就跳过。

/** 最小可用的 IndexedDB 桩：只支持 drafts 单表 get/put/getAll */
function memoryIDB(c) {
  const store = new Map();
  const db = {
    createObjectStore() {},
    transaction() {
      const tx = {};
      tx.objectStore = () => ({
        get: (key) => { const r = {}; queueMicrotask(() => { r.result = store.get(key); r.onsuccess && r.onsuccess(); tx.oncomplete && tx.oncomplete(); }); return r; },
        getAll: () => { const r = {}; queueMicrotask(() => { r.result = [...store.values()]; r.onsuccess && r.onsuccess(); tx.oncomplete && tx.oncomplete(); }); return r; },
        put: (rec) => { store.set(rec.key, rec); const r = {}; queueMicrotask(() => { r.result = rec; r.onsuccess && r.onsuccess(); tx.oncomplete && tx.oncomplete(); }); return r; },
      });
      return tx;
    },
  };
  c.indexedDB = { open() { const req = {}; setTimeout(() => { req.result = db; req.onupgradeneeded && req.onupgradeneeded(); req.onsuccess && req.onsuccess(); }, 0); return req; } };
  return store;
}

test('draftMode：合规版与阶段模板互不匹配，老草稿按阶段模板处理', () => {
  const c = context();
  const stage = { ...c.window.editorFeatures, complianceMode: false };
  assert.equal(stage.draftMode(), 'stage');
  assert.equal(stage.draftModeMatches({}), true, '没有 mode 字段的老草稿必须仍能恢复');
  assert.equal(stage.draftModeMatches({ mode: 'stage' }), true);
  assert.equal(stage.draftModeMatches({ mode: 'compliance' }), false);
  const comp = { ...c.window.editorFeatures, complianceMode: true };
  assert.equal(comp.draftMode(), 'compliance');
  assert.equal(comp.draftModeMatches({ mode: 'compliance' }), true);
  assert.equal(comp.draftModeMatches({}), false);
});

test('saveLocalDraft：草稿记录里要带上当前模板模式', async () => {
  const c = context(), store = memoryIDB(c);
  const app = {
    ...c.window.editorFeatures, complianceMode: true, draftOwner: 1, draftDirty: true,
    draftStorageKey: 'k', draftRevision: 0, draftWriting: false, draftConflict: false,
    snapshot() { return { images: [], arrivalImages: [], finishImages: [], sopImages: [] }; },
    markDraftDirty() {},
  };
  assert.equal(await app.saveLocalDraft(), true);
  assert.equal(store.get('k').mode, 'compliance');
});

test('activateDraftAccount：模式不一致的草稿必须跳过，不能恢复正文', async () => {
  const c = context(), store = memoryIDB(c);
  store.set('account:1', {
    key: 'account:1', revision: 3, savedAt: '2026-11-05 16:00:00', mode: 'compliance',
    snapshot: { format: 'sitelog-project', schema: 1, meta: {}, report: '<section class="pdf-section">合规版正文</section>', images: [], arrivalImages: [], finishImages: [], sopImages: [] },
  });
  const restored = [];
  const app = {
    ...c.window.editorFeatures, editorReady: true, accountUser: { id: 1 }, showPassword: false,
    draftOwner: null, complianceMode: false, draftRevision: 0, draftConflict: false,
    async restoreSnapshot() { restored.push(1); }, allPhotos: () => [], showToast(m) { this.toast = m; },
  };
  await app.activateDraftAccount();
  assert.equal(restored.length, 0, '合规版草稿被恢复了，普通入口会显示五段结构');
  assert.match(app.draftStatus, /跳过/);
  assert.match(app.toast, /合规版/);
});

test('activateDraftAccount：模式一致的草稿照常恢复', async () => {
  const c = context(), store = memoryIDB(c);
  store.set('account:1', {
    key: 'account:1', revision: 2, savedAt: '2026-11-05 16:00:00', mode: 'stage',
    snapshot: { format: 'sitelog-project', schema: 1, meta: {}, report: '<p>阶段正文</p>', images: [], arrivalImages: [], finishImages: [], sopImages: [] },
  });
  const restored = [];
  const app = {
    ...c.window.editorFeatures, editorReady: true, accountUser: { id: 1 }, showPassword: false,
    draftOwner: null, complianceMode: false, draftRevision: 0, draftConflict: false,
    async restoreSnapshot() { restored.push(1); }, allPhotos: () => [], showToast() {},
  };
  await app.activateDraftAccount();
  assert.equal(restored.length, 1);
  assert.equal(app.draftRestored, true);
});
