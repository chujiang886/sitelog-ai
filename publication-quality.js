// 归档只描述资料；工程完工、应收结清和实际到账由业务系统确认。
(() => {
  const filename = text => /^(?:[^<>\n]+\.(?:jpe?g|png|webp|heic)|[a-f0-9]{24,}(?:_origin)?(?:\(\d+\))?|(?:IMG|DSC|DSCN|PXL)[_-]?\d{4,})$/i.test(text);
  const fields = ['title','desc','highlights','stage'];
  const values = p => Object.fromEntries(fields.map(k=>[k,JSON.parse(JSON.stringify(p[k] ?? (k==='highlights'?[]:'')))]));
  const confirmPhoto = p => { p.textReview=values(p); if(p._analyzed)p.aiConfirmed=true; };
  const reviewCurrent = p => !!p.textReview && JSON.stringify(p.textReview)===JSON.stringify(values(p));
  const finishLabel = stage => (stage || '当前阶段')+' · 本阶段成果照片';
  const unsupportedClaim = result => /符合(?:工艺)?标准|符合规范|(?:完成|已做|已进行)安全交底|全断面填充|(?:提升|增强|增加).{0,8}(?:刚度|强度|热工性能)/.test(JSON.stringify(result));
  const photoDate = p => '拍摄时间：'+(p.capturedAt ? p.capturedAt+'（人工提供，待核对原图）' : '未提供')+'；'+(p.uploadedAt?'上传整理时间（系统）：'+p.uploadedAt:'历史整理时间（来源未核实）：'+(p.time||'未提供'));
  function clean(root) {
    root.querySelectorAll('button,input,select,textarea,[data-action],details.debug-panel,.sop-upload-zone,.sop-grid-top-row,.sop-remove-btn,.frame-add-row,.frame-move-row,[data-public-exclude],.no-print').forEach(el=>el.remove());
    root.querySelectorAll('[contenteditable]').forEach(el=>el.removeAttribute('contenteditable'));
    root.querySelectorAll('.pdf-meta-item,span,p').forEach(el=>{
      const text=el.textContent.replace(/\s+/g,'');
      if(/^(服务热线[:：]?待填写|🔒?分享范围[:：]?发布时确认|\[请填写[^\]]*\]|\[待补充\])$/.test(text))el.remove();
    });
    root.querySelectorAll('h3,figcaption,.sop-photo-caption').forEach(el=>{if(filename(el.textContent.trim()))el.textContent='施工照片（待补充说明）'});
    root.querySelectorAll('img').forEach(el=>{if(filename(el.alt||''))el.alt='施工照片'});
    return root;
  }
  window.sitelogPublication={clean,photoDate,finishLabel,confirmPhoto,reviewCurrent,unsupportedClaim};
})();
