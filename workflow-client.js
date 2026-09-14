// 保存检查点与冲突选择都保留在当前账号范围；不自动覆盖另一设备的修改。
(() => {
 const clone=value=>JSON.parse(JSON.stringify(value));
 const canonical=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
 const cloudBody=value=>{const body=clone(value);delete body.savedAt;delete body.project;for(const g of sitelogEditor.collections)for(const p of body[g]){delete p.dataUrl;delete p.file;delete p._debug;}return body};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 async function pool(items,limit,action){let next=0;await Promise.all(Array.from({length:Math.min(limit,items.length)},async()=>{while(next<items.length)await action(items[next++])}))}
 function differences(local,remote){
   const rows=[];const add=(path,label,a,b)=>{if(canonical(a)!==canonical(b))rows.push({key:rows.length,path,label,local:a,remote:b,choice:''})};
   for(const key of new Set([...Object.keys(local.meta),...Object.keys(remote.meta)]))add(['meta',key],({projectName:'项目名称',siteLocation:'施工部位',archivePerson:'归档人',archiveDate:'归档日期',templateType:'施工阶段'}[key]||key),local.meta[key],remote.meta[key]);
   for(const g of sitelogEditor.collections){
     const a=new Map(local[g].map(p=>[p.id,p])),b=new Map(remote[g].map(p=>[p.id,p]));
     for(const id of new Set([...a.keys(),...b.keys()])){
       const x=a.get(id),y=b.get(id),title=x?.title||y?.title||'照片';
       if(!x||!y)add([g,id],title+'（新增或移除）',x,y);
       else for(const key of new Set([...Object.keys(x),...Object.keys(y)]))if(!['analyzing'].includes(key))add([g,id,key],title+' · '+({title:'标题',desc:'说明',highlights:'要点',mediaId:'照片文件',category:'类别',stage:'阶段',time:'时间',aiBaseline:'AI 原建议',_manual:'人工修改标记',aiConfirmed:'核对状态'}[key]||key),x[key],y[key]);
     }
     add([g,'$order'],'照片顺序 · '+({images:'施工节点',arrivalImages:'进场',finishImages:'完工',sopImages:'离场'}[g]),local[g].map(p=>p.id),remote[g].map(p=>p.id));
   }
   for(const key of ['report','field','origin','css'])add([key],({report:'自由正文与章节布局',field:'现场事实与核对记录',origin:'历史来源',css:'文档样式'}[key]),local[key],remote[key]);
   return rows;
 }
 function merge(local,remote,rows){
   if(rows.some(r=>!['local','remote'].includes(r.choice)))throw Error('请逐项选择需要保留的内容');
   const result=clone(remote);
   for(const r of rows){const value=r[r.choice],path=r.path;
     if(sitelogEditor.collections.includes(path[0])){
       if(path[1]==='$order')continue;
       const list=result[path[0]],i=list.findIndex(p=>p.id===path[1]);
       if(path.length===2){if(value===undefined){if(i>=0)list.splice(i,1)}else if(i>=0)list[i]=clone(value);else list.push(clone(value));}
       else if(i>=0){if(value===undefined)delete list[i][path[2]];else list[i][path[2]]=clone(value)}
     }else if(path.length===1){if(value===undefined)delete result[path[0]];else result[path[0]]=clone(value)}
     else{if(value===undefined)delete result[path[0]][path[1]];else result[path[0]][path[1]]=clone(value)}
   }
   for(const r of rows.filter(r=>r.path[1]==='$order')){const ids=r[r.choice],list=result[r.path[0]];list.sort((a,b)=>{const x=ids.indexOf(a.id),y=ids.indexOf(b.id);return (x<0?ids.length:x)-(y<0?ids.length:y)})}
   return result;
 }
 window.sitelogWorkflow={differences,merge,cloudBody,canonical,pool};
 window.workflowFeatures={
  uploadKey:'',uploadPaused:false,uploadProgress:{done:0,total:0,reused:0},uploadPending:false,
  archiveStage:'',archivePersonFilter:'',archiveAfter:'',archiveBefore:'',archiveKind:'',archiveGallery:[],archiveGalleryOpen:false,
  cloudConflict:null,changeItems:[],feedbackPanel:false,feedbackItems:[],feedbackPhoto:'',feedbackReason:'',feedbackEvidence:'',feedbackNotes:{},feedbackBusy:false,
  projectSnapshotExtras(){return {id:this.cloudProjectId,revision:this.cloudRevision,status:this.cloudStatus,uploadKey:this.uploadKey,uploadPending:this.uploadPending}},
  restoreProjectExtras(value){this.cloudProjectId=value?.id||'';this.cloudRevision=value?.revision||0;this.cloudStatus=value?.status||'draft';this.uploadKey=value?.uploadKey||'';this.uploadPending=value?.uploadPending===true;this.cloudConflict=null;this.cloudMessage=this.cloudProjectId?'云端修订 '+this.cloudRevision+' · 本机恢复，可继续同步':'尚未保存云端';this.projectDetail=null;this.publicationAttempt=null},
  async durableDraft(){for(let n=0;this.draftWriting&&n<100;n++)await sleep(50);this.markDraftDirty();if(!await this.saveLocalDraft())throw Error('本机草稿尚未保存，请先导出工程包后重试')},
  async transferJSON(path,payload){
    for(let attempt=0;;attempt++){
      if(this.uploadPaused)throw Error('同步已暂停，已成功照片会在继续时复用');
      try{return await this.accountJSON(path,payload)}catch(e){
        if(attempt>=2||(![408,429,500,502,503,504].includes(e.status)&&!(e instanceof TypeError)))throw e;
        this.cloudMessage='连接暂时中断，正在重试当前步骤 '+(attempt+1)+'/2';await sleep(600*(attempt+1));
      }
    }
  },
  async saveCloudProject(){
    if(this.draftHydrating)throw Error('正在恢复本机草稿，请稍候');if(this.cloudBusy)throw Error('正在保存工程，请稍候');if(!this.projectName.trim())throw Error('请先填写项目名称');
    const owner=this.accountUser?.id;if(!owner)throw Error('请先登录');const same=()=>{if(this.accountUser?.id!==owner)throw Error('账号已切换，本次同步停止')};
    this.cloudBusy=true;this.uploadPaused=false;this.uploadPending=true;
    try{
      if(!this.uploadKey)this.uploadKey=crypto.randomUUID();await this.durableDraft();same();
      const key='upload:'+owner+':'+this.uploadKey;
      let checkpoint=await sitelogEditor.transaction('readonly',store=>store.get(key))||{key,receipts:{}};same();
      if(!this.cloudProjectId){const created=await this.transferJSON('/projects',{title:this.projectName,request_key:this.uploadKey});same();this.cloudProjectId=created.id;this.cloudRevision=0;for(const p of this.allPhotos())delete p.mediaId;}
      checkpoint.pid=this.cloudProjectId;await sitelogEditor.transaction('readwrite',store=>store.put(checkpoint));await this.durableDraft();same();
      const snapshot=this.snapshot();const photos=sitelogEditor.collections.flatMap(g=>snapshot[g]);this.uploadProgress={done:0,total:photos.length,reused:0};
      for(const photo of photos){
        same();if(this.uploadPaused)throw Error('同步已暂停，点击继续同步即可恢复');
        if(!photo.mediaId){
          const bytes=await (await fetch(photo.dataUrl)).arrayBuffer();const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
          // 即便上传成功响应丢失或本机检查点没写入，也能通过服务端散列查询恢复。
          const lookup=await this.transferJSON('/projects/'+this.cloudProjectId+'/media-lookup?sha256='+hash);same();
          const uploaded=lookup.found?lookup.media:await this.transferJSON('/projects/'+this.cloudProjectId+'/media',{dataUrl:photo.dataUrl,filename:photo.filename});same();
          photo.mediaId=uploaded.id;checkpoint.receipts[photo.id]={sha256:hash,id:uploaded.id};
          await sitelogEditor.transaction('readwrite',store=>store.put(checkpoint));same();
          const original=this.allPhotos().find(p=>p.id===photo.id);if(original&&original.dataUrl===photo.dataUrl)original.mediaId=uploaded.id;
          if(lookup.found)this.uploadProgress.reused++;
        }else this.uploadProgress.reused++;
        this.uploadProgress.done++;this.cloudMessage='正在同步照片 '+this.uploadProgress.done+'/'+photos.length+' · 已复用 '+this.uploadProgress.reused+' 张';
      }
      const saved=await this.transferJSON('/projects/'+this.cloudProjectId+'/draft',{revision:this.cloudRevision,body:cloudBody(snapshot),acknowledge_unchanged:true});same();
      this.cloudRevision=saved.revision;this.cloudStatus=saved.status;this.uploadPending=false;this.cloudMessage='云端已保存 · 修订 '+saved.revision;await this.durableDraft();return saved;
    }catch(error){same();this.cloudMessage=error.message;if(error.status===409)await this.prepareConflict();throw error}finally{if(this.accountUser?.id===owner)this.cloudBusy=false}
  },
  async hydrateSnapshot(snapshot){
    const cached=new Map(this.allPhotos().filter(p=>p.mediaId).map(p=>[p.mediaId,p.dataUrl]));
    await pool(sitelogEditor.collections.flatMap(g=>snapshot[g]),3,async photo=>{
      if(photo.dataUrl)return;if(cached.has(photo.mediaId)){photo.dataUrl=cached.get(photo.mediaId);return}
      const response=await this.sessionRequest('/media/'+photo.mediaId);if(!response.ok)throw Error('照片读取失败，当前工程仍保留');photo.dataUrl=await this.fileToDataUrl(await response.blob());
    });return snapshot;
  },
  async openCloudProject(pid){
    if(this.cloudBusy)return;if(this.hasWork()&&!confirm('打开云端工程前会保存当前本机草稿，是否继续？'))return;
    const owner=this.accountUser?.id;this.cloudBusy=true;
    try{await this.durableDraft();const data=await this.accountJSON('/projects/'+pid);if(!data.revision)throw Error('此工程还没有保存正文');
      const snapshot=await this.hydrateSnapshot(data.body);if(this.accountUser?.id!==owner)throw Error('账号已切换');snapshot.project={id:pid,revision:data.revision,status:data.status};
      this.undoSnapshot=this.snapshot();await this.restoreSnapshot(snapshot);this.projectDetail=data;this.draftStorageKey='account:'+owner+':cloud:'+pid;const previous=await sitelogEditor.transaction('readonly',store=>store.get(this.draftStorageKey));this.draftRevision=previous?.revision||0;this.draftConflict=false;await this.durableDraft();this.projectPanel=false;this.showToast('已打开云端工程 · 修订 '+data.revision);
    }catch(error){this.showToast(error.message,'error',8000)}finally{this.cloudBusy=false}
  },
  async loadProjects(){const params=new URLSearchParams({q:this.projectQuery,page:this.projectPage,stage:this.archiveStage,person:this.archivePersonFilter,after:this.archiveAfter,before:this.archiveBefore,kind:this.archiveKind});const data=await this.accountJSON('/archives?'+params);this.projectItems=data.items;this.projectTotal=data.total},
  async previewArchive(item){this.archiveGallery=[];this.archiveGalleryOpen=true;await this.projectAction(async()=>{if(item.kind==='legacy')throw Error('历史档案可通过原分享查看，复制后可使用云端缩略图');const data=await this.accountJSON('/projects/'+item.id);this.archiveGallery=sitelogEditor.collections.flatMap(g=>data.body[g]||[]).map(p=>({id:p.id,title:p.title,src:'/api/share/media/'+p.mediaId+'/thumbnail'}))})},
  async prepareConflict(){const remote=await this.accountJSON('/projects/'+this.cloudProjectId);this.changeItems=(await this.accountJSON('/projects/'+this.cloudProjectId+'/changes')).items;const local=cloudBody(this.snapshot());this.cloudConflict={pid:this.cloudProjectId,revision:remote.revision,remote:remote.body,local,rows:differences(local,remote.body)}},
  differenceText(value){if(value===undefined)return '（此项不存在）';if(typeof value==='string'){const holder=document.createElement('template');holder.innerHTML=sitelogEditor.sanitizeReport(value);return holder.content.textContent||value}return JSON.stringify(value,null,2)},
  async resolveConflict(){
    if(this.cloudBusy||!this.cloudConflict)return;this.cloudBusy=true;
    try{const conflict=this.cloudConflict,result=merge(conflict.local,conflict.remote,conflict.rows);await this.durableDraft();
      // 保存合并前副本，关闭页面或再次冲突后仍可在本机草稿列表找回。
      const backupKey='account:'+this.accountUser.id+':merge-backup:'+crypto.randomUUID();await sitelogEditor.transaction('readwrite',store=>store.put({key:backupKey,snapshot:this.snapshot(),revision:1,savedAt:new Date().toLocaleString('zh-CN')}));
      await this.hydrateSnapshot(result);result.project={id:conflict.pid,revision:conflict.revision,status:'draft',uploadKey:this.uploadKey};this.undoSnapshot=this.snapshot();await this.restoreSnapshot(result);await this.durableDraft();this.cloudConflict=null;
    }catch(e){this.showToast(e.message,'error');return}finally{this.cloudBusy=false}
    await this.projectAction(()=>this.saveCloudProject());
  },
  async openFeedback(){this.feedbackPanel=true;await this.projectAction(async()=>{if(!this.cloudProjectId)throw Error('请先保存云端工程');this.feedbackItems=(await this.accountJSON('/projects/'+this.cloudProjectId+'/feedback')).items})},
  async submitFeedback(){if(this.feedbackBusy)return;this.feedbackBusy=true;try{await this.projectAction(async()=>{await this.saveCloudProject();await this.accountJSON('/projects/'+this.cloudProjectId+'/feedback',{revision:this.cloudRevision,photo_id:this.feedbackPhoto,reason:this.feedbackReason,evidence:this.feedbackEvidence});this.feedbackReason='';this.feedbackEvidence='';await this.openFeedback();this.showToast('反馈已提交，独立审核后才进入评测集')})}finally{this.feedbackBusy=false}},
  async reviewFeedback(item,action){await this.projectAction(async()=>{await this.accountJSON('/projects/'+this.cloudProjectId+'/feedback',{id:item.id,action,note:this.feedbackNotes[item.id]||''});await this.openFeedback()})},
  async exportFeedback(){await this.projectAction(async()=>{const data=await this.accountJSON('/projects/'+this.cloudProjectId+'/feedback-export');const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));link.download='已审核AI反馈集.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)})},
 };
})();
