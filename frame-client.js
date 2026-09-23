// 「一框一记录」：两个 1 对 1 阶段的按框循环。
//
// 【为什么单独一个文件】
// 与 project-client / workflow-client / field-client / legacy-client / address-client 同理：
// 浏览器里 index.html 只是一个巨大的 Alpine 组件字面量，塞在里面的逻辑无法被单测加载。
// 拆出来之后 test-frame-client.cjs 可以用 vm 直接跑 normalizeFrames()，
// 不必起浏览器。分组逻辑（尤其「孤儿照片归并」）是最容易出静默错的地方——
// 错了不会报错，只会让业主看到的报告里少几张照片。
//
// 【数据结构】
// frames = [{ id, label, arrivalIds: [], nodeIds: [] }]
//
// 照片本体仍留在 images / arrivalImages / finishImages / sopImages 四个扁平数组里，
// frames 只记 id 归属。这不是图省事：后端 publish() 的 allowed / refs 都只遍历那四个
// 数组（projects.py 第 159/165 行），照片一旦搬进 frames 就会被判成
// 「报告含未同步的照片，请先保存云端草稿」。同理，后端 checked_body 新增的
// checked_frames 也只校验「id 是否存在于对应分组」，不搬运照片。
//
// 【为什么 1 对 1 要按框分组】
// 「1 对 1」是按门洞逐个建档：一套房子里有很多个门洞，每个门洞算一框，
// 各自一条从头到尾的记录。业主端用窗号（主卧窗 / 阳台推拉门）替代「第 N 次」——
// 否则业主看到的是一串「框架1对1 · 第 1/2/3 次」，根本不知道哪个是自己的主卧。
(function () {
  // 只有这两个阶段按框循环。其余阶段是整户一次，段落数固定。
  const FRAMED_TEMPLATES = ['框架1对1', '玻扇1对1'];

  // 段落序号用中文。超过 20 段在实际场景里不会出现（20 段 = 9 个门洞），
  // 真超了回落阿拉伯数字，免得拼出「二十一」这种读起来别扭的长串。
  const CN_NUM = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
    '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十'];
  function sectionNum(n) { return CN_NUM[n - 1] || String(n); }

  const FRAME_LIMIT = 50;

  /**
   * 框分组自愈。三种情况在这里收敛，保证「照片永远有归属、报告里永不丢图」：
   *   ① 老工程（P4 之前存的 1 对 1 报告）根本没有 frames；
   *   ② 删掉一个框，框内照片成了孤儿；
   *   ③ 照片被删，frames 里留下悬空引用。
   *
   * 纯函数：不改入参，返回新的 frames 数组。
   *
   * @param {Array}  frames      现有分组，可为空或非数组
   * @param {Array}  arrivalIds  arrivalImages 里全部照片 id
   * @param {Array}  nodeIds     images 里全部照片 id
   * @param {Function} makeId    生成新框 id（注入以便测试可复现）
   */
  function normalizeFrames(frames, arrivalIds, nodeIds, makeId) {
    const list = Array.isArray(frames) ? frames.map(frame => ({
      id: frame && typeof frame.id === 'string' ? frame.id : makeId(),
      label: frame && typeof frame.label === 'string' ? frame.label : '',
      arrivalIds: Array.isArray(frame && frame.arrivalIds) ? frame.arrivalIds.slice() : [],
      nodeIds: Array.isArray(frame && frame.nodeIds) ? frame.nodeIds.slice() : [],
    })) : [];
    const arrivals = new Set(arrivalIds || []);
    const nodes = new Set(nodeIds || []);
    // ③ 清掉悬空引用。留着会被后端 checked_frames 判「窗框照片与所属分组不匹配」
    //    而拒绝整份草稿——师傅只会看到一句读不懂的报错。
    list.forEach(frame => {
      frame.arrivalIds = frame.arrivalIds.filter(id => arrivals.has(id));
      frame.nodeIds = frame.nodeIds.filter(id => nodes.has(id));
    });
    // 同一张照片不能属于两个框，否则报告里会重复出图。保留先出现的那个框。
    const claimed = new Set();
    list.forEach(frame => {
      frame.arrivalIds = frame.arrivalIds.filter(id => claimed.has(id) ? false : (claimed.add(id), true));
      frame.nodeIds = frame.nodeIds.filter(id => claimed.has(id) ? false : (claimed.add(id), true));
    });
    if (!list.length) list.push({ id: makeId(), label: '', arrivalIds: [], nodeIds: [] });
    // ①② 孤儿照片一律并入第一框，不静默丢弃。想彻底删掉就在框内逐张删。
    const orphans = [...(arrivalIds || []), ...(nodeIds || [])].filter(id => !claimed.has(id));
    const first = list[0];
    orphans.forEach(id => {
      const target = arrivals.has(id) ? first.arrivalIds : first.nodeIds;
      if (!target.includes(id)) target.push(id);
    });
    return list.slice(0, FRAME_LIMIT);
  }

  window.sitelogFrames = { FRAMED_TEMPLATES, CN_NUM, FRAME_LIMIT, sectionNum, normalizeFrames };

  window.frameFeatures = {
    // 按框分组的状态。照片本体不在这里，见文件头说明。
    frames: [],

    isFramedTemplate() { return FRAMED_TEMPLATES.includes(this.templateType); },

    newFrameId() { return 'fr' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); },

    normalizeFrames() {
      this.frames = normalizeFrames(
        this.frames,
        (this.arrivalImages || []).map(photo => photo.id),
        (this.images || []).map(photo => photo.id),
        () => this.newFrameId()
      );
    },

    // 按 id 顺序取照片本体，id 顺序即用户在框内的排列顺序。
    framePhotos(ids, collection) {
      const pool = new Map((this[collection] || []).map(photo => [photo.id, photo]));
      return (ids || []).map(id => pool.get(id)).filter(Boolean);
    },

    // 框内的检查项卡片（4 张）。两个 1 对 1 阶段各一套，与原先模板里的静态卡片一致。
    frameCheckCards() {
      const cards = this.templateType === '玻扇1对1' ? [
        ['🪟', 'pdf-check-gold', '玻扇入位', '按洞口编号逐扇入位，框扇配合间隙均匀、无磕碰'],
        ['🔧', 'pdf-check-green', '五金调试', '执手、传动器、铰链逐一调试，开合顺畅、锁点咬合到位'],
        ['🌧️', 'pdf-check-green', '密封调缝', '胶条压合均匀、排水孔通畅，拼缝与内外侧密封面平整'],
        ['✅', 'pdf-check-neutral', '开合复检', '逐扇反复开合锁闭、气密水密复检，与现场确认无干涉'],
      ] : [
        ['📐', 'pdf-check-gold', '洞口尺寸复核', '逐洞复核宽高、对角线与墙体垂直度，偏差控制在规范范围内'],
        ['📏', 'pdf-check-green', '框体调直', '调直框体、校正扭曲与侧弯，保证四角方正、平面度达标'],
        ['🔩', 'pdf-check-green', '五金位校正', '按单扇逐一校正执手、锁点、铰链安装位，开合顺畅无干涉'],
        ['🔧', 'pdf-check-neutral', '缝隙调平', '调整框扇间隙与拼缝，内外侧均匀，密封面平整'],
      ];
      return cards.map(([icon, tone, title, desc]) =>
        '<div class="pdf-check-card ' + tone + '"><p class="pdf-check-title"><span>' + icon + '</span>' + title + '</p>' +
        '<p class="pdf-check-desc">' + desc + '</p></div>').join('');
    },

    // 框内某个分区的照片卡 + 上传入口。data 属性名与 captureDomEdits 的选择器对应。
    frameGalleryHtml(frameIdx, zone, photos) {
      const isArrival = zone === 'arrival';
      const metaPrefix = isArrival ? (this.templateType === '玻扇1对1' ? '扇位核对' : '洞口确认') : '单扇校正';
      // 放错框时能改。只有一个框就没有「别的框」可移，不渲染这个下拉。
      const moveRow = photo => this.frames.length > 1
        ? '<div class="frame-move-row"><select class="frame-move-select" data-photo-id="' + photo.id +
          '" data-zone="' + zone + '" title="移到其他框"><option value="">移到其他框…</option>' +
          this.frames.map((frame, i) => '<option value="' + frame.id + '">' + (i + 1) + '. ' +
            this.escapeHtml(frame.label || '未命名框') + '</option>').join('') +
          '</select></div>'
        : '';
      const cards = photos.map((photo, idx) => {
        const highlights = (photo.highlights || []).map(h => '<span class="highlight-badge">✦ ' + this.escapeHtml(h) + '</span>').join('');
        return '\n              <div class="node-card node-block group" data-' + (isArrival ? 'arrival' : 'img') + '-id="' + photo.id + '">' +
          '\n                <button class="sop-remove-btn" data-id="' + photo.id + '" title="删除">×</button>' +
          '\n                <div class="node-card-header">' +
          '\n                  <span class="node-card-num">' + String(idx + 1).padStart(2, '0') + '</span>' +
          '\n                  <span class="node-card-meta">' + metaPrefix + ' · ' + this.escapeHtml(photo.time || '') + '</span>' +
          '\n                </div>' +
          '\n                ' + moveRow(photo) +
          '\n                <h3 class="text-base font-bold text-[#1F3D2A] mb-2 editable-block" style="padding:0 18px;">' + this.escapeHtml(photo.title || (isArrival ? '进场照片' : '未命名节点')) + '</h3>' +
          (photo.stage ? '\n                <div style="padding:0 18px 10px"><span class="node-card-stage-badge">📍 ' + this.escapeHtml(photo.stage) + '</span></div>' : '') +
          '\n                <div class="node-card-body">' +
          '\n                  <div class="node-card-image"><img src="' + photo.dataUrl + '" alt="' + this.escapeHtml(photo.title || '') + '" loading="lazy"></div>' +
          '\n                  <div class="node-card-detail">' +
          '\n                    <p class="node-card-desc editable-block" contenteditable="true">' + (this.escapeHtml(photo.desc || '') || '<span style="color:#bbb">[请填写说明]</span>') + '</p>' +
          '\n                    ' + this.dupWarnHtml(photo) +
          (highlights ? '\n                    <div class="node-card-highlights-label">✦ 工艺亮点</div><div class="editable-block" contenteditable="true">' + highlights + '</div>' : '') +
          '\n                  </div>' +
          '\n                </div>' +
          '\n              </div>';
      }).join('');
      const empty = isArrival
        ? ['📤', '点击或拖拽上传进场照片', '人员到位 · 材料到场 · 安全交底']
        : ['📤', '点击或拖拽上传施工节点照片', '校正过程 · 调平调直 · 五金位'];
      return '<div class="pdf-sop-gallery-title">📸 ' + (isArrival ? '进场留证' : '单扇校正节点') + '</div>' +
        '<div class="sop-grid-top-row"><div class="sop-upload-zone sop-upload-small">+ 添加照片</div>' +
        '<input type="file" accept="image/*" multiple class="hidden"></div>' +
        (cards ? '<div class="node-cards-container">' + cards + '</div>'
          : '<div class="sop-upload-zone frame-zone-empty"><div class="sop-upload-icon">' + empty[0] + '</div>' +
            '<p class="sop-upload-text">' + empty[1] + '</p><p class="sop-upload-hint">' + empty[2] + '</p></div>');
    },

    // 渲染全部框。每次增删框、增删照片都整体重渲染 —— 报告是数据驱动的，
    // 不做局部 DOM 补丁，避免「编号与实际框数不一致」这类静默错误。
    syncFrames() {
      const root = document.getElementById('frames-container');
      if (!root) return;
      this.normalizeFrames();
      const self = this;
      const isGlass = this.templateType === '玻扇1对1';
      root.innerHTML = this.frames.map((frame, idx) =>
        '\n            <section class="pdf-section frame-section" data-frame-id="' + frame.id + '">' +
        '\n              <div class="pdf-section-header">' +
        '\n                <span class="pdf-section-num">·</span>' +
        '\n                <span class="pdf-section-title">' + (isGlass ? '进场与扇位确认' : '进场与洞口确认') + '</span>' +
        '\n                <span class="pdf-section-line"></span>' +
        '\n                <button class="frame-remove-btn" data-frame-id="' + frame.id + '" title="删除此框">×</button>' +
        '\n              </div>' +
        '\n              <div class="frame-label-row">' +
        '\n                <span class="frame-label-tag">窗号</span>' +
        '\n                <span class="frame-label editable-block" contenteditable="true" data-frame-id="' + frame.id + '" data-placeholder="如：主卧窗 / 阳台推拉门">' + this.escapeHtml(frame.label) + '</span>' +
        '\n              </div>' +
        '\n              <div class="pdf-sop-gallery" id="arrival-gallery-f' + idx + '">' + this.frameGalleryHtml(idx, 'arrival', this.framePhotos(frame.arrivalIds, 'arrivalImages')) + '</div>' +
        '\n            </section>' +
        '\n            <section class="pdf-section frame-section" data-frame-id="' + frame.id + '">' +
        '\n              <div class="pdf-section-header">' +
        '\n                <span class="pdf-section-num">·</span>' +
        '\n                <span class="pdf-section-title">' + (isGlass ? '单扇调试节点' : '单扇校正节点') + '</span>' +
        '\n                <span class="pdf-section-line"></span>' +
        '\n              </div>' +
        '\n              <div id="images-container-f' + idx + '">' + this.frameGalleryHtml(idx, 'node', this.framePhotos(frame.nodeIds, 'images')) + '</div>' +
        '\n              <div class="pdf-grid-2 mt-6">' + this.frameCheckCards() + '</div>' +
        '\n            </section>').join('') +
        '\n            <div class="frame-add-row">' +
        '\n              <button class="frame-add-btn" id="frame-add-btn">＋ 增加一个框</button>' +
        '\n              <span class="frame-add-hint">每加一个框自动多一组「进场确认 + 单扇校正节点」，编号顺延</span>' +
        '\n            </div>';

      // ── 事件绑定：全部走原生监听器。x-html / innerHTML 渲染出的节点
      //    不会初始化 Alpine 指令，这是本项目踩过的坑。 ──
      this.frames.forEach((frame, idx) => {
        ['arrival', 'node'].forEach(zone => {
          const gallery = document.getElementById((zone === 'arrival' ? 'arrival-gallery' : 'images-container') + '-f' + idx);
          if (!gallery) return;
          const zoneEl = gallery.querySelector('.sop-upload-zone');
          const input = gallery.querySelector('input[type="file"]');
          const accept = files => zone === 'arrival' ? self.processArrivalFiles(files, frame.id) : self.processFiles(files, frame.id);
          if (zoneEl && input) {
            zoneEl.addEventListener('click', () => input.click());
            zoneEl.addEventListener('dragover', e => { e.preventDefault(); zoneEl.classList.add('sop-drag-over'); });
            zoneEl.addEventListener('dragleave', () => zoneEl.classList.remove('sop-drag-over'));
            zoneEl.addEventListener('drop', e => {
              e.preventDefault(); zoneEl.classList.remove('sop-drag-over');
              accept(Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/')));
            });
            input.addEventListener('change', e => { const files = Array.from(e.target.files); e.target.value = ''; accept(files); });
          }
          gallery.querySelectorAll('.sop-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => zone === 'arrival' ? self.removeArrivalImage(btn.dataset.id) : self.removeImage(btn.dataset.id));
          });
          gallery.querySelectorAll('.frame-move-select').forEach(select => {
            select.addEventListener('change', () => {
              const target = select.value; select.value = '';
              if (target) self.movePhoto(select.dataset.photoId, select.dataset.zone, target);
            });
          });
        });
      });
      root.querySelectorAll('.frame-label').forEach(el => {
        el.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); el.blur(); } });
        el.addEventListener('blur', () => {
          const frame = self.frames.find(f => f.id === el.dataset.frameId);
          if (!frame) return;
          const next = el.innerText.replace(/\s+/g, ' ').trim().slice(0, 200);
          if (next === frame.label) return;
          frame.label = next; self.markDraftDirty();
        });
      });
      root.querySelectorAll('.frame-remove-btn').forEach(btn => {
        btn.addEventListener('click', () => self.removeFrame(btn.dataset.frameId));
      });
      const addBtn = document.getElementById('frame-add-btn');
      if (addBtn) addBtn.addEventListener('click', () => self.addFrame());
      this.renumberSections();
    },

    // 段落编号按 DOM 顺序统一计算。这是「编号动态递增」的唯一实现点：
    // 模板里的编号只是默认值，真正的编号永远由这里决定，避免增删框后出现
    // 「一、二、三、三、四」这种重号。
    renumberSections() {
      const root = document.getElementById('report-content');
      if (!root) return;
      let n = 0;
      root.querySelectorAll('.pdf-section .pdf-section-num').forEach(el => { el.textContent = sectionNum(++n); });
    },

    addFrame() {
      this.undoSnapshot = this.snapshot();
      this.frames.push({ id: this.newFrameId(), label: '', arrivalIds: [], nodeIds: [] });
      this.syncFrames();
      this.markDraftDirty();
      const labels = document.querySelectorAll('#frames-container .frame-label');
      if (labels.length) labels[labels.length - 1].focus();
    },

    removeFrame(frameId) {
      const frame = this.frames.find(f => f.id === frameId);
      if (!frame) return;
      if (this.frames.length <= 1) { this.showToast('至少要保留一个框', 'error'); return; }
      const count = frame.arrivalIds.length + frame.nodeIds.length;
      if (count && !confirm('「' + (frame.label || '未命名框') + '」内有 ' + count + ' 张照片。\n' +
        '删除后这些照片会移到第一个框继续留档（不会丢）；要彻底删除请在框内逐张删。\n\n确定删除此框？')) return;
      this.undoSnapshot = this.snapshot();
      this.frames = this.frames.filter(f => f.id !== frameId);
      this.syncFrames();
      this.markDraftDirty();
    },

    // 把一张照片从当前框移到另一个框。一次只改归属，不动照片本体。
    movePhoto(photoId, zone, targetFrameId) {
      const key = zone === 'arrival' ? 'arrivalIds' : 'nodeIds';
      const target = this.frames.find(f => f.id === targetFrameId);
      if (!target) return;
      this.undoSnapshot = this.snapshot();
      this.frames.forEach(frame => { frame[key] = frame[key].filter(id => id !== photoId); });
      target[key].push(photoId);
      this.syncFrames();
      this.markDraftDirty();
    },
  };
})();
