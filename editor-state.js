// 编辑内容以数据为准；正文输入即时回写，渲染不再读取旧 DOM 覆盖新数据。
(() => {
  const collections = ['images', 'arrivalImages', 'finishImages', 'sopImages'];
  const metadata = ['projectName', 'siteLocation', 'archiveDate', 'archivePerson', 'templateType', 'reportTitle', 'pdfFilename', 'pdfFilenameTouched', 'documentId'];
  const databases = new Map();
  async function database() {
    if (!databases.has('drafts')) databases.set('drafts', new Promise((resolve, reject) => {
      const request = indexedDB.open('sitelog-drafts-v1', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('drafts', { keyPath: 'key' });
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    }).catch(error => { databases.delete('drafts'); throw error; }));
    return databases.get('drafts');
  }
  async function transaction(mode, action) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('drafts', mode);const req = action(tx.objectStore('drafts'));
      tx.oncomplete = () => resolve(req.result);tx.onerror = () => reject(tx.error);tx.onabort = () => reject(tx.error || Error('草稿保存被中止'));
    });
  }
  function localDate() { return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
  function sanitizeReport(html) {
    return DOMPurify.sanitize(html, { ADD_ATTR: ['contenteditable'], FORBID_TAGS: ['script','iframe','object','embed','form','input','button','style','link','meta','svg','math','video','audio','source'], FORBID_ATTR: ['srcset','src','href','style'], ALLOW_DATA_ATTR: true });
  }
  function validateSnapshot(snapshot) {
    if (!snapshot || snapshot.format !== 'sitelog-project' || snapshot.schema !== 1 || typeof snapshot.report !== 'string' || !snapshot.meta) throw Error('不是受支持的施格归档工程包');
    if(!['框架施工','玻扇施工','五金安装','离场自检'].includes(snapshot.meta.templateType))throw Error('工程模板不受支持');
    for (const name of collections) {
      if (!Array.isArray(snapshot[name]) || snapshot[name].length > 300) throw Error('工程包照片数量无效');
      for (const img of snapshot[name]) {
        if (!img || typeof img.id !== 'string' || !/^[\w-]{1,100}$/.test(img.id) || typeof img.dataUrl !== 'string' || !/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$/.test(img.dataUrl)) throw Error('工程包包含不支持的照片');
        for (const field of ['title','desc','category','stage','time']) if (img[field] != null && typeof img[field] !== 'string') throw Error('工程包文字格式无效');
        if (img.highlights && (!Array.isArray(img.highlights) || img.highlights.some(x => typeof x !== 'string'))) throw Error('工程包要点格式无效');
      }
    }
    return snapshot;
  }
  // data URL 是内存中的照片，不能使用 fetch（生产 connect-src 仅允许同源网络请求）。
  function photoBlob(dataUrl) {
    if (typeof dataUrl !== 'string') throw Error('照片数据无法读取，请保留页面并导出工程包');
    const match = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\s]+)$/.exec(dataUrl);
    if (!match) throw Error('照片数据格式无效，请保留页面并导出工程包');
    const binary = atob(match[2]), bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: match[1] });
  }
  window.sitelogEditor = { collections, metadata, localDate, sanitizeReport, validateSnapshot, transaction, photoBlob };
  window.editorFeatures = {
    draftStatus: '登录后自动保存本机草稿', draftSavedAt: '', draftDirty: false, draftOwner: null, draftLoading: false,
    draftRevision: 0, draftConflict: false, draftRestored: false, draftTimer: null, draftWriting: false,
    activeTemplate: '框架施工', documentId: '', undoSnapshot: null, aiCandidate: null, aiCandidateId: null,
    aiPrevious: null, editorReady: false, backgroundSyncError: '',
    draftStorageKey:'',localDraftItems:[],draftHydrating:false,draftLastError:'',

    async initializeEditor() {
      if (this.editorReady) return;
      this.editorReady = true;
      const report = document.getElementById('report-content');
      report.addEventListener('input', event => {
        const block = event.target.closest('.node-block');
        if (block) {
          const id = block.dataset.imgId || block.dataset.arrivalId || block.dataset.finishId;
          const img = this.allPhotos().find(item => item.id === id);
          if (img) {
            img._manual = img._manual || {};
            if (event.target.closest('h3')) { img.title = event.target.closest('h3').innerText.trim(); img._manual.title = true; }
            else if (event.target.closest('.node-card-desc')) { img.desc = event.target.closest('.node-card-desc').innerText.trim(); img._manual.desc = true; }
            else { const edit = event.target.closest('[contenteditable]'); if (edit) { img.highlights = edit.innerText.split(/\n|✦/).map(x => x.trim()).filter(Boolean); img._manual.highlights = true; } }
          }
        }
        this.markDraftDirty();
      });
      report.addEventListener('paste', event => {
        if (!event.target.closest('[contenteditable]')) return;
        event.preventDefault(); document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
      });
      for (const key of [...collections, ...metadata]) this.$watch(key, () => this.markDraftDirty());
      window.addEventListener('beforeunload', event => { if (this.draftDirty || this.draftWriting) { event.preventDefault(); event.returnValue = ''; } });
      document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden' && this.draftDirty) this.saveLocalDraft(); });
      await this.activateDraftAccount();
    },
    allPhotos() { return collections.flatMap(key => this[key]); },
    hasWork() {
      return this.allPhotos().length > 0 || !!this.projectName || this.draftDirty;
    },
    markDraftDirty() {
      if (!this.editorReady || this.draftLoading || !this.draftOwner) return;
      this.draftDirty = true;
      if (this.draftConflict) return;
      this.draftStatus = '有更改，正在保存…';clearTimeout(this.draftTimer);
      this.draftTimer = setTimeout(() => this.saveLocalDraft(), 800);
    },
    draftKey() { if(!this.draftStorageKey)this.draftStorageKey='account:'+this.draftOwner+':project:'+crypto.randomUUID();return this.draftStorageKey; },
    async listLocalDrafts(){const rows=await transaction('readonly',store=>store.getAll());this.localDraftItems=rows.filter(r=>r.snapshot&&r.key.startsWith('account:'+this.accountUser.id+':')||r.snapshot&&r.key==='account:'+this.accountUser.id).map(r=>({key:r.key,title:r.snapshot.meta.projectName||'未命名工程',savedAt:r.savedAt})).reverse()},
    async openLocalDraft(key){
      if(!this.accountUser||!(key.startsWith('account:'+this.accountUser.id+':')||key==='account:'+this.accountUser.id))return;
      if(this.draftDirty&&!await this.saveLocalDraft())return;
      const stored=await transaction('readonly',store=>store.get(key));if(!stored)return;
      const snapshot=stored.snapshot;for(const group of collections)for(const photo of snapshot[group])if(photo.blob){photo.dataUrl=await this.fileToDataUrl(photo.blob);delete photo.blob;}
      this.undoSnapshot=this.snapshot();await this.restoreSnapshot(snapshot);this.draftStorageKey=stored.key;this.draftRevision=stored.revision;this.draftConflict=false;this.draftStatus='已恢复本机草稿';this.projectPanel=false;
      await transaction('readwrite',store=>store.put({key:'active:'+this.draftOwner,activeKey:key}));
    },
    async activateDraftAccount() {
      if (!this.editorReady || !this.accountUser || this.showPassword || this.draftOwner === this.accountUser.id) return;
      const next = this.accountUser.id;
      if (this.draftOwner && this.draftOwner !== next) {
        if (this.draftDirty && !await this.saveLocalDraft()) { this.showLogin = true; this.showToast('上个账号的草稿尚未保存，请先导出工程包', 'error'); return; }
        await this.clearEditorForAccount();
      }
      this.draftHydrating=true;this.draftOwner = next;this.draftRevision = 0;this.draftConflict = false;
      try {
        const pointer=await transaction('readonly',store=>store.get('active:'+next));
        const stored = await transaction('readonly', store => store.get(pointer?.activeKey||'account:'+next));
        if (this.accountUser?.id !== next) return;
        if (stored) {
          const snapshot = stored.snapshot;
          for (const key of collections) for (const img of snapshot[key]) if (img.blob) {
            img.dataUrl = await this.fileToDataUrl(img.blob);delete img.blob;
          }
          this.draftStorageKey=stored.key;await this.restoreSnapshot(snapshot);this.draftRevision = stored.revision;
          this.draftSavedAt = stored.savedAt;this.draftRestored = true;
          this.draftStatus = '已恢复本机草稿';
        } else { this.draftStatus = '本机自动保存已就绪'; if (this.allPhotos().length || this.projectName) this.markDraftDirty(); }
      } catch (error) { this.draftStatus = '本机草稿不可用，请导出工程包留底';this.showToast(this.draftStatus, 'error'); } finally {this.draftHydrating=false;}
    },
    snapshot() {
      this.syncCoverMeta();
      if(this.syncFieldReport)this.syncFieldReport();
      const clone = document.getElementById('report-content').cloneNode(true);
      clone.querySelectorAll('button,input,details.debug-panel').forEach(node => node.remove());
      for (const img of clone.querySelectorAll('img')) {
        const photo = this.allPhotos().find(p => p.dataUrl === img.getAttribute('src'));
        if (photo) { img.removeAttribute('src'); img.dataset.photoRef = photo.id; }
      }
      const result = { format: 'sitelog-project', schema: 1, savedAt: new Date().toISOString(), meta: {}, report: clone.innerHTML };
      result.css = [...document.querySelectorAll('style')].map(s => s.textContent).join('\n');
      for (const key of metadata) result.meta[key] = this[key];
      for (const key of collections) result[key] = this[key].map(photo => {
        const { file, analyzing, _debug, ...rest } = photo;
        return JSON.parse(JSON.stringify({ ...rest, analyzing: false, filename: file?.name || photo.filename || '施工照片' }));
      });
      if (this.projectSnapshotExtras) result.project = this.projectSnapshotExtras();
      if (this.fieldSnapshot) result.field = this.fieldSnapshot();
      if(this.legacyOrigin)result.origin={legacy:this.legacyOrigin};
      return result;
    },
    async restoreSnapshot(snapshot) {
      validateSnapshot(snapshot);this.draftLoading = true;this.legacyOrigin=snapshot.origin?.legacy||'';
      try {
        for (const key of metadata) if (['string','boolean'].includes(typeof snapshot.meta[key])) this[key] = snapshot.meta[key];
        for (const key of collections) this[key] = snapshot[key].map(photo => ({ ...photo, analyzing: false, file: { name: photo.filename || '施工照片' } }));
        this.activeTemplate = this.templateType;
        this.reportHtml = sanitizeReport(snapshot.report);
        await this.$nextTick();
        for (const node of document.querySelectorAll('#report-content img[data-photo-ref]')) {
          const photo = this.allPhotos().find(p => p.id === node.dataset.photoRef);if (photo) node.src = photo.dataUrl;
        }
        this.syncToReport();
        if (this.restoreProjectExtras) this.restoreProjectExtras(snapshot.project);
        if (this.restoreField) this.restoreField(snapshot.field);
        if (this.syncFieldReport) this.syncFieldReport();
        await this.$nextTick();this.draftDirty = false;
      } finally { this.draftLoading = false; }
    },
    async saveLocalDraft(force = false) {
      clearTimeout(this.draftTimer);this.draftTimer = null;
      if (!this.draftOwner || this.draftLoading) return false;
      if (!this.draftDirty && this.draftRevision > 0) return true;
      if (this.draftWriting) { this.markDraftDirty();return false; }
      if (this.draftConflict && !force) return false;
      this.draftWriting = true;
      let success = false;
      try {
        const owner = this.draftOwner, key = this.draftKey(), snapshot = this.snapshot();
        this.draftDirty = false;
        for (const group of collections) for (const img of snapshot[group]) {
          img.blob = photoBlob(img.dataUrl);delete img.dataUrl;
        }
        const db = await database();
        const savedAt = new Date().toLocaleString('zh-CN', { hour12: false });
        const revision = await new Promise((resolve, reject) => {
          const tx = db.transaction('drafts', 'readwrite'), store = tx.objectStore('drafts'), request = store.get(key);
          let next;
          request.onsuccess = () => {
            if (!force && (request.result?.revision || 0) !== this.draftRevision) { tx.abort();return; }
            next = (request.result?.revision || 0) + 1;store.put({ key, snapshot, revision: next, savedAt });store.put({key:'active:'+owner,activeKey:key});
          };
          tx.oncomplete = () => resolve(next);
          tx.onabort = () => reject(tx.error || Error('另一个窗口已修改草稿，请先导出当前工程包，再恢复最新草稿'));
          tx.onerror = () => reject(tx.error);
        });
        if (owner === this.draftOwner) { this.draftRevision = revision;this.draftSavedAt = savedAt;this.draftConflict = false;this.draftStatus = '本机已保存 · ' + savedAt; }
        this.draftLastError = '';success = true;
      } catch (error) {
        this.draftDirty = true;this.draftConflict = /另一个窗口/.test(error.message);
        this.draftStatus = this.draftConflict ? error.message
          : error.name === 'QuotaExceededError' ? '本机存储空间不足，请先导出工程包留底'
          : error.name === 'SecurityError' ? '浏览器未允许本机草稿存储，请先导出工程包留底'
          : '本机草稿未保存，请保留页面并导出工程包留底';
        // 同一次持续故障只提示一次；保留未保存标记，用户仍可保存或导出重试。
        if (this.draftLastError !== this.draftStatus) this.showToast(this.draftStatus, 'error');
        this.draftLastError = this.draftStatus;
      } finally { this.draftWriting = false; if (success && this.draftDirty) this.markDraftDirty(); }
      return success;
    },
    async exportProjectPackage() {
      const snapshot = this.snapshot();
      const blob = new Blob([JSON.stringify(snapshot)], { type: 'application/json' });
      const anchor = document.createElement('a');anchor.href = URL.createObjectURL(blob);
      anchor.download = (this.projectName || '未命名工程').replace(/[\\/:*?"<>|]/g,'_') + '.sitelog.json';anchor.click();
      setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);this.showToast('工程包已导出，可在其他设备导入继续整理');
    },
    async importProjectPackage(event) {
      const file = event.target.files[0];event.target.value = '';if (!file) return;
      try {
        if (file.size > 150 * 1024 * 1024) throw Error('工程包超过 150MB，请分项目整理');
        const snapshot = validateSnapshot(JSON.parse(await file.text()));
        delete snapshot.project;for(const group of collections)for(const photo of snapshot[group])delete photo.mediaId;
        if (this.hasWork() && !confirm('导入将替换当前页面内容。已保存草稿或导出当前工程包后再继续，是否导入？')) return;
        if(this.draftDirty&&!await this.saveLocalDraft())throw Error('当前草稿尚未保存，请先导出工程包');
        this.undoSnapshot = this.snapshot();await this.restoreSnapshot(snapshot);this.draftStorageKey='';this.draftRevision=0;this.draftConflict=false;this.markDraftDirty();
        this.showToast('工程包已导入，内容可继续编辑');
      } catch (error) { this.showToast('导入失败：' + error.message, 'error'); }
    },
    async clearEditorForAccount() {
      clearTimeout(this.draftTimer);this.draftLoading = true;
      for (const key of collections) this[key] = [];
      this.legacyOrigin='';this.projectName = '';this.siteLocation = '';this.archivePerson = '';this.pdfFilename = '';this.documentId = '';
      this.draftOwner = null;this.undoSnapshot = null;this.aiCandidate = null;
      this.draftStorageKey='';this.draftRevision=0;this.draftConflict=false;this.draftLastError='';
      this.reportHtml = this.getTemplateHtml();await this.$nextTick();this.syncToReport();await this.$nextTick();
      this.draftLoading = false;this.draftDirty = false;
      if (this.resetProjectContext) this.resetProjectContext();
      if (this.restoreField) this.restoreField(null);
    },
    async undoLastAction() {
      if (!this.undoSnapshot) return;
      const target = this.undoSnapshot;this.undoSnapshot = this.snapshot();await this.restoreSnapshot(target);this.markDraftDirty();
    },
    proposeAI(img, result) {
      this.aiCandidateId = img.id;this.aiCandidate = Object.fromEntries(['title','desc','category','stage','highlights','uncertainties','aiConfirmed','_analyzed','aiError','aiSource'].filter(key=>result[key]!==undefined).map(key=>[key,result[key]]));
      img.aiBaseline={title:result.title,desc:result.desc,category:result.category,highlights:[...(result.highlights||[])],source:result.aiSource||{},capturedAt:new Date().toISOString()};this.markDraftDirty();
      this.aiPrevious = { title: img.title || '', desc: img.desc || '', highlights: [...(img.highlights || [])] };
    },
    acceptAICandidate() {
      const img = this.allPhotos().find(x => x.id === this.aiCandidateId);if (!img || !this.aiCandidate) return;
      this.undoSnapshot = this.snapshot();
      Object.assign(img, this.aiCandidate, { _manual: {}, aiConfirmed: false });
      this.aiCandidate = null;this.syncToReport();this.markDraftDirty();this.showToast('已采用新建议，可用“撤销上次操作”恢复');
    },
    keepManualText() { this.aiCandidate = null;this.showToast('已保留当前定稿，未覆盖人工内容'); },
  };
})();
