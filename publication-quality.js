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
  // 精确匹配内置模板原文；不按“建议”或“待核实”等施工用语模糊删除。
  const guidance = new Set([
    "本次框架施工整体进度与实施概况：施工范围、阶段目标、已完成工序、当前状态、下一步计划及总体质量把控要点。建议 100-200 字。",
    "本次玻扇施工整体进度与实施概况：施工范围、阶段目标、已完成工序、当前状态、下一步计划及总体质量把控要点。建议 100-200 字。",
    "本次吊装施工整体情况：吊装部位与楼层、构件规格与重量、使用吊具与设备、作业人数与分工、当日天气与风力、起吊与就位时间、总体安全与质量控制要点。建议 100-200 字。",
    "本次售后保养情况：上门原因（定期保养 / 业主报修 / 竣工验收后回访）、保养范围与门窗数量、保养项目、更换配件、业主反馈与本阶段结论。建议 100-200 字。",
    "本次单扇（门洞）框架校正整体情况：校正部位与洞口编号、框体规格、校正前偏差、校正方法与工具、校正后指标、整体质量把控要点。建议 100-200 字。",
    "本次单扇（门洞）玻扇调试整体情况：调试部位与对应洞口编号、玻扇规格、入位与调缝方法、五金调试、开合复检结果、整体质量把控要点。建议 100-200 字。",
  ].map(text=>text.replace(/\s+/g,'')));
  function clean(root) {
    root.querySelectorAll('button,input,select,textarea,[data-action],details.debug-panel,.sop-upload-zone,.sop-grid-top-row,.sop-remove-btn,.frame-add-row,.frame-move-row,[data-public-exclude],.no-print').forEach(el=>el.remove());
    root.querySelectorAll('.pdf-editable-box,p,span').forEach(el=>{
      const text=el.textContent.replace(/\s+/g,'');
      if(!el.querySelector('img,video,audio,svg,canvas,table,iframe') && (guidance.has(text)||/^\[请(?:编辑|填写)[^\[\]]*\]$/.test(text)))el.remove();
    });
    root.querySelectorAll('[contenteditable]').forEach(el=>el.removeAttribute('contenteditable'));
    root.querySelectorAll('.pdf-meta-item,span,p').forEach(el=>{
      const text=el.textContent.replace(/\s+/g,'');
      if(!el.querySelector('img,video,audio,svg,canvas,table,iframe')&&/^(服务热线[:：]?待填写|🔒?分享范围[:：]?发布时确认|\[请填写[^\]]*\]|\[待补充\])$/.test(text))el.remove();
    });
    root.querySelectorAll('h3,figcaption,.sop-photo-caption').forEach(el=>{if(filename(el.textContent.trim())||el.textContent.trim()==='施工照片（待补充说明）')el.textContent='施工照片'});
    root.querySelectorAll('img').forEach(el=>{if(filename(el.alt||''))el.alt='施工照片'});
    // 只移除仅剩分区标题的空分区；有文字、媒体或表格的分区继续保留。
    root.querySelectorAll('.pdf-section').forEach(section=>{
      const content=section.cloneNode(true);
      content.querySelectorAll('.pdf-section-header').forEach(el=>el.remove());
      if(!content.textContent.trim()&&!section.querySelector('img,video,audio,svg,canvas,table,iframe'))section.remove();
    });
    return root;
  }
  window.sitelogPublication={clean,photoDate,finishLabel,confirmPhoto,reviewCurrent,unsupportedClaim};
})();
