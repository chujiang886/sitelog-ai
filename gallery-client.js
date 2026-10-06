/* ================================================================
 * 三组「手动上传画廊」：班组进场 / 班组离场 SOP / 完工照片
 *
 * 从 app-main.js 原样搬来（904–1208 行，15 个方法，305 行）。三者是
 * **同一套机制的三份实例**：每个都是
 *     syncXxxGallery()          渲染画廊 + 手工绑 DOM 事件
 *     handleXxxFileSelect/Drop  收文件
 *     processXxxFiles()         读成 dataUrl 入队（10MB 上限）
 *     removeXxxImage()          删除（并清理 frames 里的悬空引用）
 * 所以放同一个文件；分开只是把同一段代码抄三遍。
 *
 * 【为什么单独一个文件】
 * 与 frame-client / address-client 等同理：index.html 里是一个巨大的
 * Alpine 组件字面量，塞在里面的逻辑无法被单测加载。拆出来之后
 * test-gallery-client.cjs 可以在 vm 里直接跑 processArrivalFiles()，
 * 不必起浏览器 —— 而这一块恰恰是「不报错但会静默丢照片」的高危区。
 *
 * 【为什么成员缩进是 8 空格】
 * 刻意保持原样、逐字节搬移，由 test-app-main-splits.cjs 用 sha256 守护。
 * 不要为了「好看」重排缩进：块里有多行模板字符串（gallery.innerHTML = `
 * ... `），整体加/减缩进会真的改掉字符串内容，而 HTML 里看不出来。
 *
 * 【依赖】只引用合并后的组件状态（this.arrivalImages / sopImages /
 * finishImages / frames / escapeHtml / fileToDataUrl / showToast /
 * dupWarnHtml / isFramedTemplate / syncFrames），全部定义在同一个
 * 合并对象上，因此本文件与 app-main.js 的加载顺序**不影响** this.* 解析；
 * 但 index.html 里仍排在 app-main.js 之前，保持与其它 mixin 一致。
 */

window.galleryFeatures = {
        // ===== 班组进场照片手动上传画廊（与 SOP 同源机制）=====
        syncArrivalGallery() {
          const gallery = document.getElementById('arrival-gallery');
          if (!gallery) return;
          const self = this;
          const bindZone = (zone, input) => {
            if (!zone || !input) return;
            zone.addEventListener('click', () => input.click());
            zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('sop-drag-over'); });
            zone.addEventListener('dragleave', () => zone.classList.remove('sop-drag-over'));
            zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('sop-drag-over'); self.handleArrivalDrop(e); });
            input.addEventListener('change', e => self.handleArrivalFileSelect(e));
          };
          if (this.arrivalImages.length === 0) {
            gallery.innerHTML = `
              <div class="sop-upload-zone" id="arrival-zone-empty">
                <div class="sop-upload-icon">📤</div>
                <p class="sop-upload-text">点击或拖拽上传进场照片</p>
                <p class="sop-upload-hint">人员到位 · 材料到场 · 安全交底</p>
                <input type="file" id="arrival-input-empty" accept="image/*" multiple class="hidden">
              </div>`;
            bindZone(gallery.querySelector('#arrival-zone-empty'), gallery.querySelector('#arrival-input-empty'));
            return;
          }
          let cards = '';
          this.arrivalImages.forEach((img, idx) => {
            const highlights = (img.highlights || []).map(h => `<span class="highlight-badge">✦ ${this.escapeHtml(h)}</span>`).join('');
            cards += `
              <div class="node-card node-block" data-arrival-id="${img.id}">
                <button class="sop-remove-btn" data-id="${img.id}" title="删除">×</button>
                <div class="node-card-header">
                  <span class="node-card-num">${String(idx + 1).padStart(2, '0')}</span>
                  <span class="node-card-meta">班组进场 · ${this.escapeHtml(img.time || '')}</span>
                </div>
                <h3 class="text-base font-bold text-[#1F3D2A] mb-2 editable-block" contenteditable="true" style="padding:0 18px;">${this.escapeHtml(img.title || '进场照片')}</h3>
                ${img.stage ? `<div style="padding:0 18px 10px"><span class="node-card-stage-badge">📍 ${this.escapeHtml(img.stage)}</span></div>` : ''}
                <div class="node-card-body">
                  <div class="node-card-image">
                    <img src="${img.dataUrl}" alt="${this.escapeHtml(img.title || '进场照片')}" loading="lazy">
                  </div>
                  <div class="node-card-detail">
                    <p class="node-card-desc editable-block" contenteditable="true">${this.escapeHtml(img.desc || '') || '<span style="color:#bbb">[请填写说明]</span>'}</p>
                    ${this.dupWarnHtml(img)}
                    ${highlights ? `<div class="node-card-highlights-label">✦ 工艺亮点</div><div class="editable-block" contenteditable="true">${highlights}</div>` : ''}
                  </div>
                </div>
              </div>`;
          });
          gallery.innerHTML =
            '<div class="pdf-sop-gallery-title">📸 班组进场 · 人员到位 / 材料到场 / 安全交底</div>' +
            '<div class="sop-grid-top-row">' +
            '<div class="sop-upload-zone sop-upload-small" id="arrival-zone-add">+ 添加照片</div>' +
            '<input type="file" id="arrival-input-add" accept="image/*" multiple class="hidden">' +
            '</div>' +
            '<div class="node-cards-container">' + cards + '</div>';
          bindZone(gallery.querySelector('#arrival-zone-add'), gallery.querySelector('#arrival-input-add'));
          gallery.querySelectorAll('.sop-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => self.removeArrivalImage(btn.dataset.id));
          });
        },

        async handleArrivalFileSelect(event) {
          const files = Array.from(event.target.files);
          event.target.value = '';
          await this.processArrivalFiles(files);
        },

        async handleArrivalDrop(event) {
          const el = event.target.closest('.sop-upload-zone');
          if (el) el.classList.remove('sop-drag-over');
          const files = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/'));
          await this.processArrivalFiles(files);
        },

        async processArrivalFiles(files, frameId) {
          if (files.length === 0) return;
          const added = [];
          for (const file of files) {
            if (file.size > 10 * 1024 * 1024) {
              this.showToast(`⚠️ ${file.name} 超过 10MB，已跳过`, 'error');
              continue;
            }
            const dataUrl = await this.fileToDataUrl(file);
            const photo = {
              id: Date.now() + '_' + Math.random().toString(36).slice(2, 8),
              file: file,
              dataUrl: dataUrl,
              title: '',
              desc: '',
              highlights: [],
              stage: '',
              category: '班组进场',
              section: 'arrival',
              time: new Date().toLocaleString('zh-CN', { hour12: false }),
              aiConfirmed: false,
              _analyzed: false,
              analyzing: false
            };
            this.arrivalImages.push(photo);added.push(photo.id);
          }
          if (frameId) {
            const frame = this.frames.find(f => f.id === frameId);
            if (frame) frame.arrivalIds.push(...added);
          }
          this.showToast(`✅ 进场照片已添加 ${files.length} 张，可点「AI 一键整理」分析`);
          if (this.isFramedTemplate()) this.syncFrames(); else this.syncArrivalGallery();
        },

        removeArrivalImage(id) {
          this.arrivalImages = this.arrivalImages.filter(i => i.id !== id);
          // 与 removeImage 同理：悬空引用会被后端拒绝，删除时同步清掉。
          (this.frames || []).forEach(frame => { frame.arrivalIds = frame.arrivalIds.filter(x => x !== id); });
          if (this.isFramedTemplate()) this.syncFrames(); else this.syncArrivalGallery();
        },

        syncSopGallery() {
          const gallery = document.getElementById('sop-gallery');
          if (!gallery) return;
          const self = this;
          // ── 纯 DOM 事件绑定（不走 Alpine 指令，避免 x-html/innerHTML 不初始化指令的坑）──
          const bindZone = (zone, input) => {
            if (!zone || !input) return;
            zone.addEventListener('click', () => input.click());
            zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('sop-drag-over'); });
            zone.addEventListener('dragleave', () => zone.classList.remove('sop-drag-over'));
            zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('sop-drag-over'); self.handleSopDrop(e); });
            input.addEventListener('change', e => self.handleSopFileSelect(e));
          };
          if (this.sopImages.length === 0) {
            gallery.innerHTML = `
              <div class="sop-upload-zone" id="sop-zone-empty">
                <div class="sop-upload-icon">📤</div>
                <p class="sop-upload-text">点击或拖拽上传离场自检照片</p>
                <p class="sop-upload-hint">关水 · 关电 · 关门 · 清场</p>
                <input type="file" id="sop-input-empty" accept="image/*" multiple class="hidden">
              </div>`;
            bindZone(gallery.querySelector('#sop-zone-empty'), gallery.querySelector('#sop-input-empty'));
            return;
          }
          let cards = '';
          this.sopImages.forEach(img => {
            cards += `
              <div class="sop-photo-card">
                <button class="sop-remove-btn" data-id="${img.id}" title="删除">×</button>
                <img src="${img.dataUrl}" alt="${this.escapeHtml(img.title || '离场自检')}" loading="lazy">
                <div class="sop-photo-caption">${this.escapeHtml(img.title || '离场自检')}</div>
              </div>`;
          });
          gallery.innerHTML =
            '<div class="pdf-sop-gallery-title">📸 离场自检 · 关水 / 关电 / 关门 / 清场</div>' +
            '<div class="sop-grid-top-row">' +
            '<div class="sop-upload-zone sop-upload-small" id="sop-zone-add">+ 添加照片</div>' +
            '<input type="file" id="sop-input-add" accept="image/*" multiple class="hidden">' +
            '</div>' +
            '<div class="pdf-sop-grid">' + cards + '</div>';
          bindZone(gallery.querySelector('#sop-zone-add'), gallery.querySelector('#sop-input-add'));
          gallery.querySelectorAll('.sop-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => self.removeSopImage(btn.dataset.id));
          });
        },

        async handleSopFileSelect(event) {
          const files = Array.from(event.target.files);
          event.target.value = '';
          await this.processSopFiles(files);
        },

        async handleSopDrop(event) {
          const el = event.target.closest('.sop-upload-zone');
          if (el) el.classList.remove('sop-drag-over');
          const files = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/'));
          await this.processSopFiles(files);
        },

        async processSopFiles(files) {
          if (files.length === 0) return;
          for (const file of files) {
            if (file.size > 10 * 1024 * 1024) {
              this.showToast(`⚠️ ${file.name} 超过 10MB，已跳过`, 'error');
              continue;
            }
            const dataUrl = await this.fileToDataUrl(file);
            this.sopImages.push({
              id: Date.now() + '_' + Math.random().toString(36).slice(2, 8),
              file: file,
              dataUrl: dataUrl,
              title: file.name.replace(/\.[^.]+$/, ''),  // 用文件名作标题
              time: new Date().toLocaleString('zh-CN', { hour12: false })
            });
          }
          this.showToast(`✅ SOP 已添加 ${files.length} 张照片`);
          this.syncSopGallery();
        },

        removeSopImage(id) {
          this.sopImages = this.sopImages.filter(i => i.id !== id);
          this.syncSopGallery();
        },

        // ===== 完工照片 手动上传画廊（与 SOP 同源机制）=====
        syncFinishGallery() {
          const gallery = document.getElementById('finish-gallery');
          if (!gallery) return;
          const self = this;
          const bindZone = (zone, input) => {
            if (!zone || !input) return;
            zone.addEventListener('click', () => input.click());
            zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('sop-drag-over'); });
            zone.addEventListener('dragleave', () => zone.classList.remove('sop-drag-over'));
            zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('sop-drag-over'); self.handleFinishDrop(e); });
            input.addEventListener('change', e => self.handleFinishFileSelect(e));
          };
          if (this.finishImages.length === 0) {
            gallery.innerHTML = `
              <div class="sop-upload-zone" id="finish-zone-empty">
                <div class="sop-upload-icon">📤</div>
                <p class="sop-upload-text">点击或拖拽上传完工照片</p>
                <p class="sop-upload-hint">最终交付 · 整体效果 · 细部特写</p>
                <input type="file" id="finish-input-empty" accept="image/*" multiple class="hidden">
              </div>`;
            bindZone(gallery.querySelector('#finish-zone-empty'), gallery.querySelector('#finish-input-empty'));
            return;
          }
          let cards = '';
          this.finishImages.forEach((img, idx) => {
            const highlights = (img.highlights || []).map(h => `<span class="highlight-badge">✦ ${this.escapeHtml(h)}</span>`).join('');
            cards += `
              <div class="node-card node-block" data-finish-id="${img.id}">
                <button class="sop-remove-btn" data-id="${img.id}" title="删除">×</button>
                <div class="node-card-header">
                  <span class="node-card-num">${String(idx + 1).padStart(2, '0')}</span>
                  <span class="node-card-meta">完工照片 · ${this.escapeHtml(img.time || '')}</span>
                </div>
                <h3 class="text-base font-bold text-[#1F3D2A] mb-2 editable-block" contenteditable="true" style="padding:0 18px;">${this.escapeHtml(img.title || '完工照片')}</h3>
                ${img.stage ? `<div style="padding:0 18px 10px"><span class="node-card-stage-badge">📍 ${this.escapeHtml(img.stage)}</span></div>` : ''}
                <div class="node-card-body">
                  <div class="node-card-image">
                    <img src="${img.dataUrl}" alt="${this.escapeHtml(img.title || '完工照片')}" loading="lazy">
                  </div>
                  <div class="node-card-detail">
                    <p class="node-card-desc editable-block" contenteditable="true">${this.escapeHtml(img.desc || '') || '<span style="color:#bbb">[请填写说明]</span>'}</p>
                    ${this.dupWarnHtml(img)}
                    ${highlights ? `<div class="node-card-highlights-label">✦ 工艺亮点</div><div class="editable-block" contenteditable="true">${highlights}</div>` : ''}
                  </div>
                </div>
              </div>`;
          });
          gallery.innerHTML =
            '<div class="pdf-sop-gallery-title">📸 完工实景 · 最终交付照片</div>' +
            '<div class="sop-grid-top-row">' +
            '<div class="sop-upload-zone sop-upload-small" id="finish-zone-add">+ 添加照片</div>' +
            '<input type="file" id="finish-input-add" accept="image/*" multiple class="hidden">' +
            '</div>' +
            '<div class="node-cards-container">' + cards + '</div>';
          bindZone(gallery.querySelector('#finish-zone-add'), gallery.querySelector('#finish-input-add'));
          gallery.querySelectorAll('.sop-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => self.removeFinishImage(btn.dataset.id));
          });
        },

        async handleFinishFileSelect(event) {
          const files = Array.from(event.target.files);
          event.target.value = '';
          await this.processFinishFiles(files);
        },

        async handleFinishDrop(event) {
          const el = event.target.closest('.sop-upload-zone');
          if (el) el.classList.remove('sop-drag-over');
          const files = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/'));
          await this.processFinishFiles(files);
        },

        async processFinishFiles(files) {
          if (files.length === 0) return;
          for (const file of files) {
            if (file.size > 10 * 1024 * 1024) {
              this.showToast(`⚠️ ${file.name} 超过 10MB，已跳过`, 'error');
              continue;
            }
            const dataUrl = await this.fileToDataUrl(file);
            this.finishImages.push({
              id: Date.now() + '_' + Math.random().toString(36).slice(2, 8),
              file: file,
              dataUrl: dataUrl,
              title: '',
              desc: '',
              highlights: [],
              stage: '',
              category: '完工照片',
              section: 'finish',
              time: new Date().toLocaleString('zh-CN', { hour12: false }),
              aiConfirmed: false,
              _analyzed: false,
              analyzing: false
            });
          }
          this.showToast(`✅ 完工照片已添加 ${files.length} 张`);
          this.syncFinishGallery();
        },

        removeFinishImage(id) {
          this.finishImages = this.finishImages.filter(i => i.id !== id);
          this.syncFinishGallery();
        },
};
