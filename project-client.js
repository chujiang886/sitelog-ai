// 云端工作区：保存修订与发布快照分离，服务器始终执行权限及冲突检查。
window.projectFeatures = {
  cloudProjectId:'',cloudRevision:0,cloudStatus:'draft',cloudBusy:false,cloudMessage:'尚未保存云端',
  projectPanel:false,projectItems:[],projectQuery:'',projectPage:1,projectTotal:0,projectDetail:null,
  colleagues:[],memberUser:'',memberRole:'editor',reviewNote:'',shareAudience:'public',shareDays:30,shareCode:'',
  publicationAttempt:null,
  aiJobId:'',aiJobStatus:'',aiCancelRequested:false,aiUsage:null,aiBudget:{user_daily:100,company_daily:500},
  async cancelAIJob(){this.aiCancelRequested=true;if(this.aiJobId)await this.projectAction(()=>this.accountJSON('/ai/jobs/'+this.aiJobId+'/cancel',{}));this.aiJobStatus='已请求取消；已提交的上游请求可能仍计费'},
  async loadAIUsage(){await this.projectAction(async()=>{this.aiUsage=await this.accountJSON('/ai/usage');this.aiBudget={...this.aiUsage.limits}})},
  async saveAIBudget(){await this.projectAction(async()=>{await this.accountJSON('/admin/ai-budget',{user_daily:Number(this.aiBudget.user_daily),company_daily:Number(this.aiBudget.company_daily)});await this.loadAIUsage();this.showToast('识别次数预算已保存')})},
  async runAIJob(image,prompt,model){
    this.aiCancelRequested=false;let job=await this.accountJSON('/ai/jobs',{image,prompt,model});this.aiJobId=job.id;this.aiJobStatus='识别任务已排队';
    try{while(['queued','running'].includes(job.status)){if(this.aiCancelRequested)await this.accountJSON('/ai/jobs/'+job.id+'/cancel',{});await new Promise(resolve=>setTimeout(resolve,1000));job=await this.accountJSON('/ai/jobs/'+job.id);this.aiJobStatus=job.status==='queued'?'识别排队中':job.status==='running'?'正在识别…':'';}if(job.status!=='succeeded')throw Error(job.error||'识别已取消');return job.result}
    finally{this.aiJobId='';this.aiJobStatus='';}
  },
  projectSnapshotExtras(){return {id:this.cloudProjectId,revision:this.cloudRevision,status:this.cloudStatus}},
  restoreProjectExtras(value){this.cloudProjectId=value?.id||'';this.cloudRevision=value?.revision||0;this.cloudStatus=value?.status||'draft';this.cloudMessage=this.cloudProjectId?'云端修订 '+this.cloudRevision+' · 本机恢复':'尚未保存云端';this.projectDetail=null;this.publicationAttempt=null},
  resetProjectContext(){this.restoreProjectExtras(null)},
  statusLabel(status){return {draft:'整理中',review:'待审核',approved:'已审核'}[status]||status},
  async projectAction(action){try{return await action()}catch(error){this.cloudMessage=error.message;this.showToast(error.message,'error',8000);return null}},
  async openProjects(){this.projectPanel=true;await this.projectAction(async()=>{await this.loadProjects();await this.listLocalDrafts();this.colleagues=(await this.accountJSON('/colleagues')).items;if(this.cloudProjectId)await this.loadProjectDetails()})},
  async loadProjects(){const data=await this.accountJSON('/projects?q='+encodeURIComponent(this.projectQuery)+'&page='+this.projectPage);this.projectItems=data.items;this.projectTotal=data.total},
  async loadProjectDetails(){this.projectDetail=await this.accountJSON('/projects/'+this.cloudProjectId);this.cloudStatus=this.projectDetail.status;return this.projectDetail},
  async newLocalProject(){if(this.cloudBusy)return;if(this.hasWork()&&!confirm('新建工程前请保存或导出当前内容。是否新建空白工程？'))return;if(!await this.saveLocalDraft())return;const previous=this.snapshot();await this.clearEditorForAccount();this.undoSnapshot=previous;this.draftOwner=this.accountUser.id;this.archivePerson=this.accountUser.display_name;this.archiveDate=sitelogEditor.localDate();this.resetProjectContext();this.projectPanel=false;this.markDraftDirty()},
  async openCloudProject(pid){
    if(this.cloudBusy)return;
    if(this.hasWork()&&!confirm('打开云端工程将替换当前页面。当前内容可先导出工程包，是否继续？'))return;
    this.cloudBusy=true;
    try{
      if(this.draftDirty&&!await this.saveLocalDraft())throw Error('当前草稿尚未保存，请先导出工程包');const data=await this.accountJSON('/projects/'+pid);if(!data.revision)throw Error('此工程尚无已保存内容');
      const snapshot=data.body;snapshot.project={id:pid,revision:data.revision,status:data.status};
      for(const group of sitelogEditor.collections)for(const photo of snapshot[group]){
        const response=await this.sessionRequest('/media/'+photo.mediaId);if(!response.ok)throw Error('照片读取失败，当前页面内容尚未替换');photo.dataUrl=await this.fileToDataUrl(await response.blob());
      }
      this.undoSnapshot=this.snapshot();await this.restoreSnapshot(snapshot);this.projectDetail=data;this.draftStorageKey='account:'+this.accountUser.id+':cloud:'+pid;const previous=await sitelogEditor.transaction('readonly',store=>store.get(this.draftStorageKey));this.draftRevision=previous?.revision||0;this.draftConflict=false;this.markDraftDirty();await this.saveLocalDraft();this.projectPanel=false;this.showToast('已打开云端工程 · 修订 '+data.revision);
    }catch(error){this.showToast(error.message,'error',8000)}finally{this.cloudBusy=false}
  },
  async saveCloudProject(){
    if(this.cloudBusy)throw Error('正在保存工程，请稍候');
    if(!this.projectName.trim())throw Error('请先填写项目名称');
    this.cloudBusy=true;
    try{
      await this.saveLocalDraft();const snapshot=this.snapshot();
      if(!this.cloudProjectId){const created=await this.accountJSON('/projects',{title:this.projectName});this.cloudProjectId=created.id;this.cloudRevision=0;for(const photo of this.allPhotos())delete photo.mediaId;for(const group of sitelogEditor.collections)for(const photo of snapshot[group])delete photo.mediaId;}
      let index=0;const total=this.allPhotos().length;
      for(const group of sitelogEditor.collections)for(const photo of snapshot[group]){
        this.cloudMessage='正在同步照片 '+(++index)+'/'+total;
        if(!photo.mediaId){const uploaded=await this.accountJSON('/projects/'+this.cloudProjectId+'/media',{dataUrl:photo.dataUrl,filename:photo.filename});photo.mediaId=uploaded.id;const original=this[group].find(p=>p.id===photo.id);if(original&&original.dataUrl===photo.dataUrl)original.mediaId=uploaded.id;}
        delete photo.dataUrl;delete photo.file;delete photo._debug;
      }
      const saved=await this.accountJSON('/projects/'+this.cloudProjectId+'/draft',{revision:this.cloudRevision,body:snapshot});
      this.cloudRevision=saved.revision;this.cloudStatus=saved.status;this.cloudMessage='云端已保存 · 修订 '+saved.revision;this.markDraftDirty();await this.saveLocalDraft();return saved;
    }catch(error){this.cloudMessage=error.message;throw error}finally{this.cloudBusy=false}
  },
  async reviewProject(decision){await this.projectAction(async()=>{if(decision==='submit')await this.saveCloudProject();const result=await this.accountJSON('/projects/'+this.cloudProjectId+'/review',{revision:this.cloudRevision,decision,note:this.reviewNote});this.cloudStatus=result.status;this.reviewNote='';await this.loadProjectDetails();this.markDraftDirty();this.showToast('审核状态：'+this.statusLabel(result.status))})},
  async updateProjectMember(){await this.projectAction(async()=>{await this.accountJSON('/projects/'+this.cloudProjectId+'/members',{user_id:Number(this.memberUser),role:this.memberRole});await this.loadProjectDetails();this.showToast('项目成员权限已更新')})},
  async changePublication(sid,revoked){await this.projectAction(async()=>{await this.accountJSON('/publication/'+sid+(revoked?'/revoke':'/restore'),{});await this.loadProjectDetails();this.showToast(revoked?'链接及照片访问已撤回':'分享已恢复；原有效期仍生效')})},
  async publishCloudProject(){
    // 失败重试先重放相同发布请求；避免网络响应丢失创建重复档案。
    if(this.publicationAttempt){const previous=this.publicationAttempt;return await this.accountJSON('/projects/'+previous.pid+'/publish',previous.payload)}
    await this.saveCloudProject();
    if(this.cloudStatus!=='approved')throw Error('请先在「项目工作区」提交审核并通过，再生成分享码');
    const clone=document.getElementById('report-content').cloneNode(true);
    clone.querySelectorAll('button,input,details.debug-panel,.sop-upload-zone,.sop-grid-top-row,.sop-remove-btn').forEach(el=>el.remove());clone.querySelectorAll('[contenteditable]').forEach(el=>el.removeAttribute('contenteditable'));
    for(const image of clone.querySelectorAll('img')){const photo=this.allPhotos().find(p=>p.dataUrl===image.getAttribute('src'));if(!photo?.mediaId)throw Error('有照片尚未保存，请重新保存云端工程');image.src='/api/share/media/'+photo.mediaId;}
    const payload={revision:this.cloudRevision,idempotency:crypto.randomUUID(),audience:this.shareAudience,expires:Number(this.shareDays)>0?Date.now()/1000+Number(this.shareDays)*86400:null,code:this.shareCode,html:clone.innerHTML,css:[...document.querySelectorAll('style')].map(s=>s.textContent).join('\n')};
    this.publicationAttempt={pid:this.cloudProjectId,payload};
    return await this.accountJSON('/projects/'+this.cloudProjectId+'/publish',payload);
  }
};
