// 历史发布档案转换为独立草稿；原档案和分享链接保持原样。
(() => {
  function convert(record) {
    if (!record || typeof record.html !== 'string') throw Error('历史档案格式无效');
    // template 内容保持惰性，解析时不执行脚本或请求外部图片。
    const holder=document.createElement('template');holder.innerHTML=record.html;
    const root=holder.content, title=root.querySelector('.pdf-cover-main-title')?.textContent.trim()||'';
    const type=['框架施工','玻扇施工','五金安装','离场自检'].find(x=>title.includes(x));
    if(!type)throw Error('此历史档案版式暂不支持自动转换，原记录保持完整');
    root.querySelectorAll('[id]').forEach(n=>n.removeAttribute('id'));
    const values={};root.querySelectorAll('.pdf-meta-item').forEach(item=>{
      const label=item.querySelector('.pdf-meta-label')?.textContent||'';
      for(const key of ['项目名称','施工部位','归档日期','归档人'])if(label.includes(key))values[key]=item.querySelector('.pdf-meta-value')?.textContent.trim()||'';
    });
    const snapshot={format:'sitelog-project',schema:1,meta:{projectName:(record.project||values['项目名称']||'历史工程')+'（副本）',siteLocation:values['施工部位']||'',archiveDate:values['归档日期']||sitelogEditor.localDate(),archivePerson:values['归档人']||'',templateType:type,reportTitle:title,pdfFilename:title,pdfFilenameTouched:false,documentId:''},images:[],arrivalImages:[],finishImages:[],sopImages:[]};
    const mapping={'班组进场':['arrivalImages','arrival-gallery'],'施工节点':['images','images-container'],'完工照片':['finishImages','finish-gallery'],'班组离场 SOP':['sopImages','sop-gallery']};
    const assigned=new Set(),seen=new Set();
    for(const section of root.querySelectorAll('.pdf-section')){
      const label=section.querySelector('.pdf-section-title')?.textContent.trim(),spec=mapping[label];
      if(!spec)continue;
      if(seen.has(label))throw Error('历史档案含重复照片章节，暂不能自动转换');seen.add(label);
      const [group,id]=spec;const gallery=section.querySelector(group==='images'?'.node-cards-container':'.pdf-sop-gallery');
      if(!gallery&&section.querySelector('img'))throw Error('历史照片结构无法完整识别');
      if(gallery)gallery.id=id;
      else {const empty=document.createElement('div');empty.id=id;section.appendChild(empty);}
      for(const image of section.querySelectorAll('img')){
        const dataUrl=image.getAttribute('src')||'';
        if(!/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$/.test(dataUrl))throw Error('历史档案有外部或不支持的照片，未创建不完整副本');
        const card=image.closest('.node-card,.sop-photo-card');
        if(!card||card.querySelectorAll('img').length!==1)throw Error('历史照片与说明无法一一对应');
        const text=s=>card.querySelector(s)?.textContent.trim()||'';
        const metadata=text('.node-card-meta').split('·');const photoId=crypto.randomUUID();
        snapshot[group].push({id:photoId,dataUrl,filename:'历史照片-'+(assigned.size+1)+'.jpg',title:text('h3')||text('.sop-photo-caption')||'历史照片',desc:text('.node-card-desc'),category:metadata[0]?.trim()||type,time:metadata.slice(1).join('·').trim(),stage:text('.node-card-stage-badge').replace(/^📍\s*/,''),highlights:[...card.querySelectorAll('.highlight-badge')].map(n=>n.textContent.replace(/^✦\s*/,'').trim()),_manual:{title:true,desc:true,highlights:true},_analyzed:false,aiConfirmed:false});
        image.dataset.photoRef=photoId;assigned.add(image);
      }
    }
    if(root.querySelectorAll('img').length!==assigned.size)throw Error('有照片不属于可识别章节，未创建不完整副本');
    if(!seen.has('施工节点'))throw Error('缺少可编辑施工章节，暂不能自动转换');
    root.querySelectorAll('.pdf-editable-box,.node-card-desc,.node-card h3').forEach(n=>n.setAttribute('contenteditable','true'));
    snapshot.report=holder.innerHTML;snapshot.origin={legacy:record.id||''};
    return sitelogEditor.validateSnapshot(snapshot);
  }
  window.sitelogLegacy={convert};
  window.legacyFeatures={legacyBusy:false,
    async copyLegacyProject(id){
      if(this.legacyBusy||this.cloudBusy)return;
      if(this.hasWork()&&!confirm('将历史档案复制为新工程。当前内容会先保存为本机草稿，原分享链接不变。是否继续？'))return;
      this.legacyBusy=true;
      try{
        if(this.draftDirty&&!await this.saveLocalDraft())throw Error('当前草稿尚未保存，请先导出工程包');
        const result=await this.accountJSON('/legacy/'+encodeURIComponent(id));const snapshot=convert(result.record);
        this.undoSnapshot=this.snapshot();await this.restoreSnapshot(snapshot);this.draftStorageKey='';this.draftRevision=0;this.draftConflict=false;this.markDraftDirty();
        const saved=await this.saveLocalDraft();this.shareManageOpen=false;
        this.showToast(saved?'历史档案已复制为新草稿，请核对后保存云端并重新审核':'副本已打开，但本机保存失败，请立即导出工程包',saved?'info':'error',8000);
      }catch(error){this.showToast('复制失败：'+error.message,'error',8000)}finally{this.legacyBusy=false}
    }
  };
})();
