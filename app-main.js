    function siteLogApp() {
      return {
        ...window.accountFeatures,
        ...window.editorFeatures,
        ...window.projectFeatures,
        ...window.addressFeatures,
        ...window.workflowFeatures,
        legacyOrigin:'',
        ...window.legacyFeatures,
        ...window.fieldFeatures,
        ...window.frameFeatures,
        ...window.galleryFeatures,
        ...window.aiVisionFeatures,
        // ===== 状态 =====
        apiProvider: 'qwen',
        templateType: '框架施工',
        images: [],             // 施工节点照片
        arrivalImages: [],      // 班组进场照片（人员到位、材料到场、安全交底）
        sopImages: [],          // 班组离场 SOP 手动上传照片（关水/关电/关门/清场）
        finishImages: [],       // 完工照片 手动上传（最终交付实景）
        // 「一框一记录」的 frames 状态与全部方法在 frame-client.js，
        // 由 ...window.frameFeatures 合并进来。
        // 三组手动上传画廊（班组进场 / SOP / 完工）的状态留在本文件，
        // 渲染与上传方法在 gallery-client.js，由 ...window.galleryFeatures 合并进来。
        reportHtml: '',
        reportTitle: '',
        pdfFilename: '',
        pdfFilenameTouched: false,
        // ===== 分享功能（v4.4：确认完成 → 二维码 → 业主扫码看）=====
        shareDialogOpen: false,      // 分享弹窗是否打开
        shareError: '',
        shareConnectionMessage: '',
        shareChecking: false,
        shareCardReady: false,
        shareBusy: false,            // 上传进行中
        shareResult: null,           // { id, url } 分享成功结果
        shareManageOpen: false,      // 分享管理面板（已分享清单）
        shareList: [],               // 已分享清单数据
        shareListLoading: false,
        // 客户 LOGO（可选加入报告封面）
        addClientLogo: false,
        clientLogoId: '',
        clientLogos: [],             // 管理员上传的客户 LOGO 库
        clientLogoName: '',
        clientLogoFiles: [],         // 支持一次多选多个文件
        clientLogoBusy: false,
        // 项目信息（用于 PDF 封面 / 归档抬头）
        projectName: '',
        siteLocation: '',
        archiveDate: new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()),
        archivePerson: '',
        processing: false,
        processedCount: 0,
        showSettings: false,
        exportGuideOpen: false,
        dragOver: false,
        testing: false,
        testResult: '',
        toast: { show: false, msg: '', type: 'info' },

        // ===== 初始化 =====
        async init() {
          this.switchTemplate();
          await this.refreshSession();
          await this.initializeEditor();
        },

        // 转义用户输入，避免注入到 x-html 报告时产生 XSS
        escapeHtml(str) {
          if (!str) return '';
          return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        },

        closeSettings() { this.showSettings = false; },
        openSettings() { this.showSettings = true; this.refreshCompanyStatus(); },

        // ===== 模板切换 =====
        switchTemplate() {
          if (this.editorReady && this.hasWork()) {
            if (!confirm('切换将采用新模板的正文，保留所有照片与照片说明；当前版式可撤销恢复。是否继续？')) {
              this.templateType = this.activeTemplate;return;
            }
            this.undoSnapshot = this.snapshot();
            this.undoSnapshot.meta.templateType = this.activeTemplate;
          }
          this.activeTemplate = this.templateType;
          this.reportHtml = this.getTemplateHtml();
          this.reportTitle = this.templateType + '归档';
          // x-html 渲染后再填充各手动上传区（否则初始为空白）
          this.$nextTick(() => { this.syncToReport();this.markDraftDirty?.(); });
        },

        getTemplateHtml() {
          let html = '';
          if (this.templateType === '吊装施工') html = TEMPLATES.lifting();
          else if (this.templateType === '框架施工') html = TEMPLATES.frame();
          else if (this.templateType === '框架1对1') html = TEMPLATES.frameOneOnOne();
          else if (this.templateType === '玻扇施工') html = TEMPLATES.glass();
          else if (this.templateType === '玻扇1对1') html = TEMPLATES.glassOneOnOne();
          else if (this.templateType === '五金安装') html = TEMPLATES.hardware();
          else if (this.templateType === '离场自检') html = TEMPLATES.departure();
          else if (this.templateType === '售后保养') html = TEMPLATES.aftercare();
          else html = TEMPLATES.frame();

          // 所有模板均保留照片分区，避免换版式后照片仍在数据中却不可见。
          // 1 对 1 模板的进场照片按框分区（arrival-gallery-f0、-f1…），没有总区；
          // 这里必须跳过，否则会多渲染一个空 section，把段落编号整体顶偏。
          const framed = html.includes('id="frames-container"');
          let missing = '';
          for (const [id, title] of [['arrival-gallery','班组进场照片'],['finish-gallery','完工照片'],['sop-gallery','离场留证']]) {
            if (framed && id === 'arrival-gallery') continue;
            if (!html.includes('id="' + id + '"')) missing += '<section class="pdf-section"><h2 class="pdf-section-header">' + title + '</h2><div class="pdf-sop-gallery" id="' + id + '"></div></section>';
          }
          html = html.includes('<footer') ? html.replace('<footer', missing + '<footer') : html + missing;

          // 注入项目信息到封面占位符（{{PROJECT_INFO}}）
          const docId = this.documentId || ('CJ-SL-' + new Date().getFullYear()
            + String(new Date().getMonth()+1).padStart(2,'0')
            + String(new Date().getDate()).padStart(2,'0')
            + '-' + String(Math.floor(Math.random()*9000)+1000));
          this.documentId = docId;
          const infoHtml = `
            <div class="pdf-meta-grid">
              <div class="pdf-meta-item"><span class="pdf-meta-label">📋 项目名称</span><span class="pdf-meta-value">${this.escapeHtml(this.projectName) || '未命名项目'}</span></div>
              <div class="pdf-meta-item"><span class="pdf-meta-label">📍 施工部位</span><span class="pdf-meta-value">${this.escapeHtml(this.siteLocation) || '—'}</span></div>
              <div class="pdf-meta-item"><span class="pdf-meta-label">📅 归档日期</span><span class="pdf-meta-value">${this.escapeHtml(this.archiveDate) || sitelogEditor.localDate()}</span></div>
              <div class="pdf-meta-item"><span class="pdf-meta-label">👤 归档人</span><span class="pdf-meta-value">${this.escapeHtml(this.archivePerson) || '—'}</span></div>
              <div class="pdf-meta-item"><span class="pdf-meta-label">📄 文档编号</span><span class="pdf-meta-value pdf-meta-mono">${docId}</span></div>
              <div class="pdf-meta-item"><span class="pdf-meta-label">🔒 分享范围</span><span class="pdf-meta-value">发布时确认</span></div>
            </div>`;
          return html.replace('{{PROJECT_INFO}}', infoHtml);
        },

        // ===== 文件处理 =====
        async handleFileSelect(event) {
          const files = Array.from(event.target.files);
          await this.processFiles(files);
          event.target.value = ''; // 重置以便重复上传
        },

        async handleDrop(event) {
          this.dragOver = false;
          const files = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/'));
          await this.processFiles(files);
        },

        // `frameId` 只在 1 对 1 阶段的按框上传时传入，用来把新照片登记到对应框。
        // 不传就是老行为：照片进全局数组，由所属模板的总区渲染。
        async processFiles(files, frameId) {
          if (files.length === 0) return;
          const added = [];
          for (const file of files) {
            if (file.size > 10 * 1024 * 1024) {
              this.showToast(`⚠️ ${file.name} 超过 10MB，已跳过`, 'error');
              continue;
            }
            const dataUrl = await this.fileToDataUrl(file);
            const img = {
              id: Date.now() + '_' + Math.random().toString(36).slice(2, 8),
              file: file,
              dataUrl: dataUrl,
              category: this.guessCategory(file.name),
              section: 'construction',
              time: new Date().toLocaleString('zh-CN', { hour12: false }),
              title: '',
              desc: '',
              highlights: [],
              analyzing: false,
              _analyzed: false   // 是否已被 AI 分析过（区分"AI真实结果"与"兜底默认值"）
            };
            this.images.push(img);added.push(img.id);
          }
          if (frameId) {
            const frame = this.frames.find(f => f.id === frameId);
            if (frame) frame.nodeIds.push(...added);
          }
          this.showToast(`✅ 已上传 ${files.length} 张照片`);
          this.syncToReport();
        },

        guessCategory(filename) {
          const f = filename.toLowerCase();
          // 「1 对 1」比通用阶段更具体，所以先匹配 1 对 1 再回落通用阶段。
          // 「1 对 1」是师傅口语——文件名里出现的关键词是「洞口 / 门洞 / 单扇 / 调缝 / 调校」。
          if (/框架|框体|立柱|横梁|电钻|打孔|水平/.test(f) && /洞口|门洞|单扇|调缝|调校|校缝|1对1|一对/.test(f)) return '框架1对1';
          if (/玻|玻璃|扇|合片|中空/.test(f) && /洞口|门洞|单扇|调缝|调校|校缝|1对1|一对/.test(f)) return '玻扇1对1';
          if (/框架|框体|立框|装框/.test(f)) return '框架施工';
          if (/玻|玻璃|玻扇|玻璃施工|合片|装玻璃|挂扇|扇/.test(f)) return '玻扇施工';
          if (/五金|把手|锁|铰链|合页|风撑/.test(f)) return '五金安装';
          if (/胶|密封|收口|打胶|注胶/.test(f)) return '密封收口';
          if (/保护|膜|覆盖|清场/.test(f)) return '成品保护';
          if (/关水|关电|关门|垃圾|离场|合规|留底|关阀/.test(f)) return '离场自检';
          return this.templateType; // 默认归到当前归档类型
        },

        fileToDataUrl(file) {
          return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
          });
        },

        removeImage(id) {
          this.images = this.images.filter(i => i.id !== id);
          // frames 里若还留着这个 id，后端 checked_frames 会判「窗框照片与所属分组不匹配」
          // 而拒绝整份草稿。删除时必须同步清掉引用。
          (this.frames || []).forEach(frame => { frame.nodeIds = frame.nodeIds.filter(x => x !== id); });
          this.syncToReport();
        },

        clearAllImages() {
          if (confirm('确定清空所有图片？')) {
            this.undoSnapshot = this.snapshot();
            this.images = [];
            this.arrivalImages = [];
            this.finishImages = [];
            this.sopImages = [];
            this.syncToReport();
          }
        },

        // AI 视觉识别引擎（17 个方法）已抽到 ai-vision-client.js

        // ===== 报告渲染 =====
        syncToReport() {
          // 封面项目信息（归档人/施工部位/日期）与图片无关，先同步，避免无图时提前 return 不更新
          this.syncCoverMeta();
          // 正文输入已由 editor-state.js 即时写入数据；渲染不能用旧 DOM 覆盖新值。
          this.syncArrivalGallery(); // 班组进场照片区独立渲染（1 对 1 模板没有总区，按框分区）
          this.syncSopGallery(); // SOP 区独立于主图，必须每次都渲染（即使无主图）
          this.syncFinishGallery(); // 完工照片画廊同理，独立于主图渲染
          this.ensureTitles();   // 最终安全网：确保没有空 title/desc 渲染出去

          // 1 对 1 阶段按框循环：进场照片与校正节点都按框分区，不存在全局 #images-container。
          if (this.isFramedTemplate()) { this.syncFrames(); return; }

          // 把图片数据同步到报告 DOM
          const container = document.getElementById('images-container');
          if (!container) return;

          if (this.images.length === 0) {
            container.innerHTML = `
              <div class="sop-upload-zone" id="node-zone-empty">
                <div class="sop-upload-icon">📤</div>
                <p class="sop-upload-text">点击或拖拽上传施工节点照片</p>
                <p class="sop-upload-hint">框架 / 玻扇 / 五金 / 密封 / 成品保护</p>
                <input type="file" id="node-input-empty" accept="image/*" multiple class="hidden">
              </div>
            `;
            const zone = container.querySelector('#node-zone-empty');
            const input = container.querySelector('#node-input-empty');
            if (zone && input) {
              zone.addEventListener('click', () => input.click());
              zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('sop-drag-over'); });
              zone.addEventListener('dragleave', () => zone.classList.remove('sop-drag-over'));
              zone.addEventListener('drop', e => {
                e.preventDefault(); zone.classList.remove('sop-drag-over');
                const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
                this.processFiles(files);
              });
              input.addEventListener('change', e => this.handleFileSelect(e));
            }
            return;
          }

          // 注意：封面和项目信息已在 getTemplateHtml() 中通过 {{PROJECT_INFO}} 注入到模板
          // #images-container 只放节点卡片，不再注入封面
          // 在施工节点顶部提供与 arrival/finish 同源的「添加照片」入口
          let html =
            '<div class="sop-grid-top-row mb-4">' +
            '<div class="sop-upload-zone sop-upload-small" id="node-zone-add">+ 添加照片</div>' +
            '<input type="file" id="node-input-add" accept="image/*" multiple class="hidden">' +
            '</div>' +
            '<div class="node-cards-container">';
          this.images.forEach((img, idx) => {
            const highlightsHtml = (img.highlights || [])
              .map(h => `<span class="highlight-badge">✦ ${this.escapeHtml(h)}</span>`)
              .join('');

            html += `
              <div class="node-card node-block group" data-img-id="${img.id}">
                <div class="node-card-header">
                  <span class="node-card-num">${String(idx + 1).padStart(2, '0')}</span>
                  <span class="node-card-meta">${this.escapeHtml(img.category)} · ${this.escapeHtml(img.time)}</span>
                </div>
                <h3 class="text-base font-bold text-[#1F3D2A] mb-2 px-5 editable-block" contenteditable="true" style="padding-left:18px;padding-right:18px;">${this.escapeHtml(img.title) || '未命名节点'}</h3>
                ${img.stage ? `<div style="padding:0 18px 10px"><span class="node-card-stage-badge">📍 ${this.escapeHtml(img.stage)}</span></div>` : ''}
                <div class="node-card-body">
                  <div class="node-card-image">
                    <img src="${img.dataUrl}" alt="${this.escapeHtml(img.title)}" loading="lazy">
                  </div>
                  <div class="node-card-detail">
                    <p class="node-card-desc editable-block" contenteditable="true">${this.escapeHtml(img.desc) || '<span style="color:#bbb">[请填写工艺说明]</span>'}</p>
                    ${this.dupWarnHtml(img)}
                    ${ (img.desc && (img.desc.includes('请补充') || img.desc.includes('📝'))) ? `
                    <details class="mb-2 bg-amber-50 border border-amber-200 rounded p-2 text-xs debug-panel">
                      <summary class="cursor-pointer font-bold text-amber-700">🔍 工艺说明为占位符 — 点击查看 AI 原始返回</summary>
                      <pre class="mt-1 text-[10px] text-red-800 whitespace-pre-wrap break-all max-h-60 overflow-auto">${this.escapeHtml(JSON.stringify(img._debug||{error:'无调试数据'}, null, 2))}</pre>
                    </details>` : '' }
                    <div class="node-card-highlights-label">✦ 工艺亮点</div>
                    <div class="editable-block" contenteditable="true">${highlightsHtml || '<span style="color:#bbb;font-size:12px">[待补充]</span>'}</div>
                  </div>
                </div>
              </div>
            `;
          });
          html += '</div>';  // .node-cards-container
          container.innerHTML = html;

          // 同步封面项目信息到 DOM（输入框改了值要实时反映到右侧封面）
          this.syncCoverMeta();

          // 绑定施工节点区顶部的「添加照片」入口（与左侧上传同源）
          const nodeZone = document.getElementById('node-zone-add');
          const nodeInput = document.getElementById('node-input-add');
          if (nodeZone && nodeInput) {
            nodeZone.addEventListener('click', () => nodeInput.click());
            nodeZone.addEventListener('dragover', e => { e.preventDefault(); nodeZone.classList.add('sop-drag-over'); });
            nodeZone.addEventListener('dragleave', () => nodeZone.classList.remove('sop-drag-over'));
            nodeZone.addEventListener('drop', e => {
              e.preventDefault();
              nodeZone.classList.remove('sop-drag-over');
              const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
              this.processFiles(files);
            });
            nodeInput.addEventListener('change', e => this.handleFileSelect(e));
          }

          // 填充 SOP 离场照片 / 完工照片 展示区（用真实照片替代纯文字说明）
          this.syncSopGallery();
          this.syncFinishGallery();
        },

        syncCoverMeta() {
          const cover = document.querySelector('#report-content .pdf-cover');
          if (!cover) return;
          // 按关键字子串匹配，避免 emoji 变体选择符（U+FE0F）导致精确比对失败
          const map = [
            ['项目名称', this.projectName || '未命名项目'],
            ['施工部位', this.siteLocation || '—'],
            ['归档日期', this.archiveDate || sitelogEditor.localDate()],
            ['归档人', this.archivePerson || '—'],
          ];
          cover.querySelectorAll('.pdf-meta-item').forEach(item => {
            const label = item.querySelector('.pdf-meta-label');
            const value = item.querySelector('.pdf-meta-value');
            if (!label || !value) return;
            const txt = label.textContent;
            const entry = map.find(m => txt.includes(m[0]));
            if (entry) { value.textContent = entry[1]; }
          });
        },

        // ===== PDF 导出（方案2：html2pdf.js 直接下载）=====
        // 用户点击 → 弹「导出指引」弹窗 → 用户点「立即下载 PDF」→ 直接生成并下载 PDF 文件
        exportPDF() {
          this.syncFieldReport();
          const totalPhotos = this.images.length + this.arrivalImages.length + this.finishImages.length + this.sopImages.length;
          if (totalPhotos === 0) {
            if (!confirm('当前报告暂无照片，是否仍要导出空白模板？')) return;
          }
          // 每次打开弹窗时，根据 h1 给出默认建议名（用户没改过才覆盖）
          const h1 = document.querySelector('#report-content h1');
          const suggested = (h1 && h1.innerText.trim()) ? h1.innerText.trim() : (this.templateType + '归档');
          if (!this.pdfFilenameTouched || !this.pdfFilename) {
            this.pdfFilename = suggested;
            this.pdfFilenameTouched = false;
          }
          // 先弹导出指引（独立弹窗，不与设置弹窗混淆）
          this.exportGuideOpen = true;
        },

        // 导出指引确认 → 直接下载 PDF
        async generatePDF() {
          // 只同步封面元信息；绝不重建卡片 DOM——
          // 用户当场手改的文字就在 DOM 里，直接克隆导出即可保留
          this.syncCoverMeta();
          const container = document.getElementById('report-content');
          if (!container) {
            this.showToast('❌ 未找到报告内容，请刷新后重试', 'error');
            return;
          }

          // 文件名
          let baseName = '';
          if (this.pdfFilename && this.pdfFilename.trim()) {
            baseName = this.pdfFilename.trim();
          } else {
            const h1 = container.querySelector('h1');
            baseName = (h1 && h1.innerText.trim()) ? h1.innerText.trim() : (this.reportTitle || '施工归档');
          }
          const cleanName = baseName.replace(/\.pdf$/i, '').replace(/[\/:*?"<>|]/g, '_').trim() || '施工归档';

          this.exportGuideOpen = false;
          this.showToast('📄 正在准备打印，请在弹窗选「另存为 PDF」…');

          try {
            // ═══ v4.1.0：浏览器原生打印（文字真实可选中 / 可编辑的 PDF） ═══
            // 告别 html2canvas 截图（文字被烤成图片 → 无法修改、无法复制）
            // 做法：把报告区克隆进隐藏 iframe，注入打印样式后调用 iframe.print()
            // 用户在打印窗口选「另存为 PDF」即可，得到的 PDF 文字是真实文字层
            const css = window.reportCssText();

            const clone = container.cloneNode(true);
            clone.removeAttribute('id');
            clone.setAttribute('id', 'report-content');
            clone.querySelectorAll('button, [data-action], details.debug-panel').forEach(el => el.remove());

            const printCss =
              '@page{size:A4;margin:14mm 15mm 16mm 15mm}'
              + '*,*::before,*::after{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}'
              + 'html,body{margin:0!important;padding:0!important;background:#fff!important}'
              + '#report-content{width:100%!important;max-width:none!important;margin:0!important;padding:0!important;box-shadow:none!important;border:none!important;background:#fff!important}'
              + '.node-card,.pdf-editable-box,.pdf-section-header,.pdf-info-card,.pdf-check-card,.pdf-callout,.pdf-footer,.pdf-cover{break-inside:avoid;page-break-inside:avoid}'
              + '.pdf-cover{break-after:page;page-break-after:always}'
              + 'button,[data-action],.no-print{display:none!important}'
              + '[contenteditable]:hover,[contenteditable]:focus{background:transparent!important}';

            const docHtml =
              '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
              + '<title>' + cleanName + '</title>'
              + '<style>' + css + '</style>'
              + '<style>' + printCss + '</style>'
              + '</' + 'head><body>' + clone.outerHTML + '</body></html>';

            const iframe = document.createElement('iframe');
            iframe.setAttribute('aria-hidden', 'true');
            iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
            document.body.appendChild(iframe);
            const idoc = iframe.contentDocument || iframe.contentWindow.document;
            idoc.open(); idoc.write(docHtml); idoc.close();

            await new Promise(r => setTimeout(r, 700));
            const imgs = Array.from(idoc.images);
            await Promise.all(imgs.map(im => (im.complete && im.naturalWidth)
              ? Promise.resolve()
              : new Promise(res => { im.onload = im.onerror = res; setTimeout(res, 2500); })));

            const w = iframe.contentWindow;
            w.focus();
            w.print();

            this.showToast('✅ 已呼起打印窗口，选「另存为 PDF」即可（建议勾选「背景图形」）', 'info', 6000);
            setTimeout(() => { if (iframe.parentNode) iframe.parentNode.removeChild(iframe); }, 1500);
          } catch (err) {
            console.error('❌ [PDF] v4.1.0 打印失败:', err.message, err.stack);
            this.showToast('❌ PDF 导出失败: ' + err.message.slice(0, 80), 'error');
          }
        },

        // ===== 导出可编辑 HTML（文字 100% 可改，给需要大改的场景） =====
        exportEditableHTML() {
          // 只同步封面元信息；直接克隆当前 DOM，保留用户全部手改内容
          this.syncCoverMeta();
          const container = document.getElementById('report-content');
          if (!container) { this.showToast('❌ 未找到报告内容，请刷新后重试', 'error'); return; }
          const css = window.reportCssText();
          const clone = container.cloneNode(true);
          clone.removeAttribute('id');
          clone.setAttribute('id', 'report-content');
          clone.querySelectorAll('button, [data-action], details.debug-panel').forEach(el => el.remove());
          const safeName = (this.pdfFilename && this.pdfFilename.trim())
            ? this.pdfFilename.trim().replace(/\.pdf$/i, '').replace(/[\/:*?"<>|]/g, '_')
            : '施工归档';
          const tip = '<p class="export-tip">✏️ 直接点击文中任意文字即可修改。改完后用浏览器菜单「打印 → 另存为 PDF」生成可发给客户的文件（文字真实可选中，可在 Acrobat / WPS 中继续编辑）。</p>';
          const docHtml =
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            + '<title>' + safeName + '</title>'
            + '<style>' + css + '</style>'
            + '<style>body{padding:24px;background:#eef0f3}'
            + '.export-tip{font:14px/1.6 system-ui,"Segoe UI",sans-serif;color:#1F3D2A;background:#fff8e6;border:1px solid #f0d999;border-radius:8px;padding:12px 16px;margin:0 auto 18px;max-width:840px}'
            + '[contenteditable]:focus{outline:2px solid #B8924A;background:#fffdf5;border-radius:3px}'
            + '</style></' + 'head><body>' + tip + clone.outerHTML + '</body></html>';
          const blob = new Blob([docHtml], { type: 'text/html;charset=utf-8' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = safeName + '.html';
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 1000);
          this.showToast('✅ 可编辑文档已下载（.html），用浏览器/WPS 打开即可改文字');
        },

        // 关闭导出指引
        closeExportGuide() {
          this.exportGuideOpen = false;
        },

        // ===== v4.4 分享功能：确认完成 → 上传 → 二维码 → 业主扫码看 =====
        SHARE_API: '/api/share',

        async shareRequest(path = '', options = {}) {
          return this.sessionRequest(path, options);
        },

        openShareDialog() {
          this.publicationAttempt = null;
          this.shareResult = null;
          this.shareError = '';
          this.shareCardReady = false;
          this.shareDialogOpen = true;
          this.resetAddressPick();
          this.loadClientLogos();
        },

        // ===== 客户 LOGO 库 =====
        async loadClientLogos() {
          try { this.clientLogos = (await this.accountJSON('/client-logos')).items || []; } catch (e) { /* 非关键，静默 */ }
        },
        onClientLogoFile(event) { this.clientLogoFiles = Array.from(event.target.files || []); event.target.value = ''; },
        // 支持一次多选多个文件：单文件用填写的名称，多文件默认用各自文件名（去扩展名）
        async uploadClientLogo() {
          const files = this.clientLogoFiles || [];
          if (!files.length || this.clientLogoBusy) return;
          const single = files.length === 1;
          if (single && !this.clientLogoName.trim()) { this.showToast('请填写 LOGO 名称（客户公司名）', 'error', 6000); return; }
          this.clientLogoBusy = true;
          let ok = 0; const failed = [];
          try {
            for (const file of files) {
              let name = this.clientLogoName.trim();
              if (!single || !name) name = String(file.name || '').replace(/\.[^.]+$/, '').trim();
              if (!name) { failed.push((file.name || '未命名') + '（无法确定名称）'); continue; }
              name = name.slice(0, 60);
              try {
                // 先缩再传：原图动辄几 MB，而 LOGO 显示尺寸只有几百 px。
                // 后端 8MB 是兜底，这里才是「不让员工等」的那一层。
                const dataUrl = await this.prepareLogoUpload(file);
                await this.accountJSON('/admin/client-logos', { name, dataUrl });
                ok++;
              } catch (e) { failed.push((file.name || '未命名') + '：' + (e.message || '失败')); }
            }
            this.clientLogoName = ''; this.clientLogoFiles = [];
            await this.loadClientLogos();
            if (!failed.length) this.showToast(ok > 1 ? `✅ 已上传 ${ok} 个客户 LOGO` : '✅ 客户 LOGO 已上传');
            else this.showToast(`成功 ${ok} 个，失败 ${failed.length} 个：${failed.join('；')}`, 'error', 10000);
          } finally { this.clientLogoBusy = false; }
        },
        async deleteClientLogo(id) {
          if (!confirm('确定删除该客户 LOGO？已发布的报告中若使用了它仍将显示，直到重新发布。')) return;
          try {
            await this.sessionRequest('/admin/client-logos/' + id, { method: 'DELETE' });
            await this.loadClientLogos();
            if (this.clientLogoId === id) { this.clientLogoId = ''; this.addClientLogo = false; this.applyClientLogo(); }
            this.showToast('已删除');
          } catch (e) { this.showToast(e.message || '删除失败', 'error', 8000); }
        },
        // 在报告封面注入/移除客户 LOGO（发布前确保已就位）
        applyClientLogo() {
          const root = document.getElementById('report-content');
          if (!root) return;
          const existing = root.querySelector('.client-logo');
          if (existing) existing.remove();
          if (!this.addClientLogo || !this.clientLogoId) { this.clientLogoId = ''; this.markDraftDirty(); return; }
          const img = document.createElement('img');
          img.className = 'client-logo';
          img.setAttribute('alt', '客户LOGO');
          img.setAttribute('src', '/api/share/client-logo/' + this.clientLogoId);
          img.setAttribute('data-client-logo', this.clientLogoId);
          img.style.maxHeight = '72px';
          img.style.margin = '0 auto 10px';
          img.style.display = 'block';
          const cover = root.querySelector('.pdf-cover');
          if (cover) cover.insertBefore(img, cover.firstChild);
          else root.insertBefore(img, root.firstChild);
          this.markDraftDirty();
        },
        drawClientLogoOnCard(ctx, W, H) {
          return new Promise((resolve) => {
            if (!this.addClientLogo || !this.clientLogoId) return resolve();
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => {
              const maxW = 160, maxH = 70;
              let w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
              if (w && h) { const ratio = Math.min(maxW / w, maxH / h, 1); w = Math.round(w * ratio); h = Math.round(h * ratio); }
              try { ctx.drawImage(img, W - 30 - w, 40, w, h); } catch (e) { /* 绘制失败不阻塞 */ }
              resolve();
            };
            img.onerror = () => resolve();
            img.src = '/api/share/client-logo/' + this.clientLogoId;
          });
        },

        async doShare() {
          if (this.shareBusy || this.reviewBusy || this.cloudBusy) return;
          const totalPhotos = this.images.length + this.arrivalImages.length + this.finishImages.length + this.sopImages.length;
          if (totalPhotos === 0 && !confirm('当前还没有上传任何照片，确定要分享吗？')) return;
          if (this.addressPickOn && !this.addressPickId) { this.showToast('请选择归属地址，或取消勾选「归到某个地址」', 'error', 8000); return; }

          this.shareBusy = true;
          this.shareError = '';
          this.shareCardReady = false;
          try {
            this.shareStep='1/3 正在保存当前工程…';this.showToast(this.shareStep, 'info', 8000);
            const data = await this.publishCloudProject();
            this.shareResult = { id: data.id, url: data.url };
            await this.$nextTick();
            await this.drawShareCard(data.url, data.id);
            this.shareCardReady = true;
            // 一址一码：发布成功后挂到所选地址。挂接失败不影响已生成的分享码，单独提示。
            await this.attachAfterPublish();
            this.showToast('✅ 分享码已生成，保存分享卡发到客户群即可');
          } catch (e) {
            console.error('[share] 上传失败:', e);
            this.shareError = (this.shareResult ? '链接已创建，二维码未完成：' : '分享未完成：') + (e.message || '网络错误');
            this.showToast(this.shareError, 'error', 8000);
          } finally {
            this.shareBusy = false;
          }
        },

        // 打包当前报告：克隆当前 DOM（含用户手改内容）+ 收集 CSS + 压缩大图
        async buildSharePayload() {
          const container = document.getElementById('report-content');
          if (!container) throw new Error('未找到报告内容，请刷新页面');
          const css = window.reportCssText();
          const clone = container.cloneNode(true);
          clone.querySelectorAll('button, select, details.debug-panel, .sop-upload-zone, .sop-grid-top-row, .sop-remove-btn, .frame-add-row, .frame-move-row').forEach(el => el.remove());
          clone.querySelectorAll('[contenteditable]').forEach(el => el.removeAttribute('contenteditable'));
          const imgs = Array.from(clone.querySelectorAll('img'));
          let compressed = 0;
          for (const im of imgs) {
            const src = im.getAttribute('src') || '';
            if (src.startsWith('data:image') && src.length > 400 * 1024) {
              try { im.setAttribute('src', await this.compressDataUrl(src)); compressed++; } catch (e) { /* 单张失败不阻塞 */ }
            }
          }
          const title = (this.pdfFilename && this.pdfFilename.trim())
            ? this.pdfFilename.trim().replace(/[\/:*?"<>|]/g, '_')
            : ((this.projectName || '未命名项目') + ' 施工归档');
          if (compressed > 0) console.log('[share] 已压缩 ' + compressed + ' 张大图');
          return {
            title: title.slice(0, 80),
            project: (this.projectName || '') + (this.siteLocation ? ' · ' + this.siteLocation : ''),
            owner: this.archivePerson || '',
            css: css,
            html: clone.innerHTML
          };
        },

        // 大图压缩：长边 1280px / JPEG 0.78，控制上传体积
        compressDataUrl(dataUrl) {
          return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
              const MAX = 1280;
              let w = img.naturalWidth, h = img.naturalHeight;
              if (Math.max(w, h) > MAX) { const k = MAX / Math.max(w, h); w = Math.round(w * k); h = Math.round(h * k); }
              const c = document.createElement('canvas');
              c.width = w; c.height = h;
              c.getContext('2d').drawImage(img, 0, 0, w, h);
              resolve(c.toDataURL('image/jpeg', 0.78));
            };
            img.onerror = () => resolve(dataUrl);
            img.src = dataUrl;
          });
        },

        // 客户 LOGO 上传前的预处理：等比缩到长边 1200px，并把 data URL 压到 1.4MB 以内。
        //
        // 【为什么不能直接用 compressDataUrl】
        // 那个函数固定输出 JPEG。JPEG 没有透明通道，公司 LOGO 的透明底会变成黑块
        // （或者被填成白块），贴到深墨绿的报告封面上就废了。LOGO 必须**保持原格式**：
        // PNG 进 PNG 出，WebP 进 WebP 出。
        //
        // 【为什么非要缩】
        // LOGO 在报告封面和分享卡上的显示尺寸只有几百 px。传一张 8MB 的原图，
        // 员工要等很久、报告体积变大、手机端加载变慢、SQLite 里躺着一堆没人看的像素——
        // 换来的画质提升在几百 px 的显示尺寸下等于零。
        // 所以这里先把尺寸压到合理范围，8MB 那个上限只是**兜底**（防绕过前端直接打接口）。
        //
        // 【为什么最后要比一下长度】
        // 小图重新编码 PNG 有时反而更大（截图类图片尤其明显）。缩完更大就用原图，
        // 别为了「压缩」白掉一次画质。
        async prepareLogoUpload(file, maxEdge = 1200, maxDataUrl = 1400000) {
          const type = String((file && file.type) || '');
          if (!/^image\/(png|jpeg|webp)$/.test(type)) throw new Error('仅支持 PNG、JPG、WebP 格式的图片');
          const original = await this.fileToDataUrl(file);
          const image = await new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error('这个文件不是有效的图片，请重新选择'));
            // 直接用刚读出来的 data URL 当 src。这里**不用** createObjectURL：
            // 反正 original 已经在内存里了，再开一个 blob URL 只是多一个要 revoke 的
            // 对象，而 revoke 的时机（onload 里立刻撤销）在部分浏览器上会让后面的
            // drawImage 拿不到像素——那是一个只在 Safari 上偶发的白图 bug。
            img.src = original;
          });
          const w = image.naturalWidth || 0, h = image.naturalHeight || 0;
          if (!w || !h) return original;
          const scale = Math.min(1, maxEdge / Math.max(w, h));
          if (scale >= 1 && original.length <= maxDataUrl) return original;
          const tw = Math.max(1, Math.round(w * scale)), th = Math.max(1, Math.round(h * scale));
          const canvas = document.createElement('canvas');
          canvas.width = tw; canvas.height = th;
          const ctx = canvas.getContext('2d');
          // JPEG 没有透明通道，直接画会得到黑底；先铺白底。
          if (type === 'image/jpeg') { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, tw, th); }
          ctx.drawImage(image, 0, 0, tw, th);
          const shrunk = type === 'image/png' ? canvas.toDataURL('image/png') : canvas.toDataURL(type, 0.9);
          return shrunk.length < original.length ? shrunk : original;
        },

        // 品牌分享卡：墨绿底 + 项目名 + 二维码（canvas 绘制，可保存为图片发群）
        async drawShareCard(url, id) {
          const canvas = document.getElementById('share-card-canvas');
          if (!canvas || typeof window.qrcode !== 'function') {
            throw new Error('二维码组件未就绪，请稍后重绘，或先复制分享链接');
          }
          const W = 750, H = 1000;
          canvas.width = W; canvas.height = H;
          canvas.style.width = '300px'; canvas.style.height = '400px';
          const ctx = canvas.getContext('2d');
          ctx.textAlign = 'center';
          ctx.fillStyle = '#1F3D2A'; ctx.fillRect(0, 0, W, H);
          ctx.strokeStyle = '#B8924A'; ctx.lineWidth = 2;
          ctx.strokeRect(26, 26, W - 52, H - 52);
          ctx.fillStyle = '#B8924A';
          ctx.font = '500 22px "PingFang SC","Microsoft YaHei",sans-serif';
          ctx.fillText('CHUJIANG · 初匠门窗服务中心', W / 2, 96);
          ctx.fillStyle = '#ffffff';
          ctx.font = '500 38px "PingFang SC","Microsoft YaHei",sans-serif';
          const title = (this.pdfFilename && this.pdfFilename.trim()) || ((this.projectName || '未命名项目') + ' 施工归档');
          const lines = this.wrapCanvasText(ctx, title, W - 160);
          lines.slice(0, 2).forEach((ln, i) => ctx.fillText(ln, W / 2, 175 + i * 52));
          const divY = 175 + Math.min(lines.length, 2) * 52 + 2;
          ctx.fillStyle = '#B8924A'; ctx.fillRect(W / 2 - 40, divY, 80, 3);
          ctx.fillStyle = 'rgba(255,255,255,0.85)';
          ctx.font = '22px "PingFang SC","Microsoft YaHei",sans-serif';
          ctx.fillText((this.projectName || '—') + (this.siteLocation ? ' · ' + this.siteLocation : ''), W / 2, divY + 48);
          ctx.fillText('归档日期：' + (this.archiveDate || sitelogEditor.localDate()), W / 2, divY + 82);
          const qrSize = 380, qrX = (W - qrSize) / 2, qrY = divY + 118;
          ctx.fillStyle = '#ffffff';
          this.drawRoundRect(ctx, qrX, qrY, qrSize, qrSize, 18); ctx.fill();
          try {
            const qr = window.qrcode(0, 'M');
            qr.addData(url); qr.make();
            const n = qr.getModuleCount();
            const inner = qrSize - 60;
            const cell = inner / n;
            const ox = qrX + 30, oy = qrY + 30;
            ctx.fillStyle = '#1F3D2A';
            for (let r = 0; r < n; r++) {
              for (let c = 0; c < n; c++) {
                if (qr.isDark(r, c)) ctx.fillRect(ox + c * cell, oy + r * cell, cell + 0.5, cell + 0.5);
              }
            }
          } catch (e) { throw new Error('二维码绘制失败，请重绘或复制分享链接'); }
          ctx.fillStyle = '#B8924A';
          ctx.font = '500 26px "PingFang SC","Microsoft YaHei",sans-serif';
          ctx.fillText('微信扫码 · 查看工程施工记录', W / 2, qrY + qrSize + 58);
          ctx.fillStyle = 'rgba(255,255,255,0.7)';
          ctx.font = '20px "PingFang SC","Microsoft YaHei",sans-serif';
          ctx.fillText('汕头市初匠门窗科技有限公司', W / 2, H - 96);
          ctx.font = '17px "PingFang SC","Microsoft YaHei",sans-serif';
          ctx.fillText('记录编号 ' + id + ' · 粤ICP备2024297744号-2', W / 2, H - 62);
          await this.drawClientLogoOnCard(ctx, W, H);
        },

        // 折行。中文没有词边界，只能逐片量宽；但门牌号、栋号这类连续数字/字母
        // 必须整体不拆——否则「…3 栋 2201」会被断成「…3 栋 220」+「1」，
        // 二维码卡片上看起来就像地址写错了，业主扫之前先起了疑心。
        // 所以先把文本切成「不可分割片段」：连续 [0-9A-Za-z]（含中间的 - _ / #）
        // 算一片，其余每个字算一片。单片自身超宽时再按字符硬拆，避免顶出画布。
        // 地址卡片与分享卡片共用这个方法，两处都受益。
        wrapCanvasText(ctx, text, maxWidth) {
          const chunks = String(text == null ? '' : text)
            .match(/[0-9A-Za-z]+(?:[-_/#][0-9A-Za-z]+)*|\s+|[\s\S]/g) || [];
          const lines = []; let cur = '';
          for (const chunk of chunks) {
            if (cur && ctx.measureText(cur + chunk).width > maxWidth) {
              const done = cur.replace(/\s+$/, '');
              if (done) lines.push(done);
              cur = /^\s+$/.test(chunk) ? '' : chunk;
            } else {
              cur += chunk;
            }
            while (ctx.measureText(cur).width > maxWidth && cur.length > 1) {
              let cut = cur.length - 1;
              while (cut > 1 && ctx.measureText(cur.slice(0, cut)).width > maxWidth) cut--;
              lines.push(cur.slice(0, cut));
              cur = cur.slice(cut);
            }
          }
          const tail = cur.replace(/\s+$/, '');
          if (tail) lines.push(tail);
          return lines;
        },

        drawRoundRect(ctx, x, y, w, h, r) {
          ctx.beginPath();
          ctx.moveTo(x + r, y);
          ctx.arcTo(x + w, y, x + w, y + h, r);
          ctx.arcTo(x + w, y + h, x, y + h, r);
          ctx.arcTo(x, y + h, x, y, r);
          ctx.arcTo(x, y, x + w, y, r);
          ctx.closePath();
        },

        async retryShareCard() {
          if (!this.shareResult) return;
          try {
            await this.drawShareCard(this.shareResult.url, this.shareResult.id);
            this.shareCardReady = true;
            this.shareError = '';
          } catch (error) { this.shareError = error.message; }
        },

        downloadShareCard() {
          if (!this.shareCardReady) return;
          const canvas = document.getElementById('share-card-canvas');
          if (!canvas) return;
          const a = document.createElement('a');
          a.href = canvas.toDataURL('image/png');
          a.download = ((this.projectName || '初匠工程记录') + '分享卡.png').replace(/[\/:*?"<>|]/g, '_');
          document.body.appendChild(a); a.click(); a.remove();
          this.showToast('✅ 分享卡已下载，发到客户群即可');
        },

        copyShareUrl() { if (this.shareResult && this.shareResult.url) this.copyText(this.shareResult.url); },

        async copyText(text) {
          try {
            await navigator.clipboard.writeText(text);
            this.showToast('✅ 链接已复制');
          } catch (e) {
            const ta = document.createElement('textarea');
            ta.value = text; document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); this.showToast('✅ 链接已复制'); }
            catch (e2) { this.showToast('❌ 复制失败，请手动复制：' + text, 'error', 6000); }
            ta.remove();
          }
        },

        openShareManage() {
          this.shareManageOpen = true;
          this.loadShareList();
        },

        async loadShareList() {
          this.shareListLoading = true;
          try {
            const resp = await this.shareRequest('/list');
            const data = await resp.json().catch(() => ({}));
            if (resp.status === 401) {
              this.showToast('❌ 无权访问分享服务，请从初匠系统页面打开', 'error');
              this.shareList = [];
              return;
            }
            if (data.ok) {
              this.shareList = data.items || [];
            } else {
              this.showToast('❌ 加载失败：' + (data.error || resp.status), 'error');
            }
          } catch (e) {
            this.showToast('❌ 网络错误：' + (e.message || '').slice(0, 50), 'error');
          } finally {
            this.shareListLoading = false;
          }
        },

        async revokeShare(id) {
          if (!confirm('确定作废这个分享链接吗？作废后业主扫码将显示"链接已失效"。')) return;
          await this.shareAction(id, '/revoke');
        },

        async restoreShare(id) {
          await this.shareAction(id, '/restore');
        },

        async shareAction(id, action) {
          try {
            const resp = await this.shareRequest(action, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id: id })
            });
            const data = await resp.json().catch(() => ({}));
            if (data.ok) {
              this.showToast(action === '/revoke' ? '✅ 已作废，旧二维码即刻失效' : '✅ 链接已恢复');
              this.loadShareList();
            } else {
              this.showToast('❌ 操作失败：' + (data.error || resp.status), 'error');
            }
          } catch (e) {
            this.showToast('❌ 网络错误：' + (e.message || '').slice(0, 50), 'error');
          }
        },

        // ===== 示例数据 =====
        // ★ v4.0.0 修复：btoa() 无法编码中文（Latin1 范围外）→ 示例按钮原本必崩
        //    改用 UTF-8 → base64 的安全转换
        svgDataUrl(svg) {
          const bytes = new TextEncoder().encode(svg);
          let bin = '';
          for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
          return 'data:image/svg+xml;base64,' + btoa(bin);
        },

        loadSampleData() {
          if (this.hasWork() && !confirm('载入示例会替换当前正文与照片，是否继续？可使用撤销恢复。')) return;
          this.undoSnapshot = this.snapshot();this.resetProjectContext();
          this.templateType = '框架施工';
          this.images = [
            {
              id: 'sample1',
              dataUrl: this.svgDataUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect fill="#e2e8f0" width="400" height="300"/><text x="200" y="150" text-anchor="middle" fill="#64748b" font-size="20">工具清点</text><text x="200" y="180" text-anchor="middle" fill="#94a3b8" font-size="12">电钻 · 水平仪 · 羊角锤</text></svg>`),
              category: '框架施工',
              time: '2026-06-23 14:00',
              title: '工具准备与定位放线',
              desc: '班组入场后第一项工作：工具清点 + 定位放线。激光水平仪校准洞口水平度偏差 ≤ 1.5mm，确保后续框体就位基准准确。',
              highlights: ['激光水平仪校准', '工具整齐铺放', '基准线清晰', '安全帽规范佩戴']
            },
            {
              id: 'sample2',
              dataUrl: this.svgDataUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect fill="#dbeafe" width="400" height="300"/><text x="200" y="150" text-anchor="middle" fill="#1e40af" font-size="20">框体就位</text><text x="200" y="180" text-anchor="middle" fill="#3b82f6" font-size="12">化学锚栓 · 激光校准</text></svg>`),
              category: '框架施工',
              time: '2026-06-23 15:30',
              title: '框体就位与化学锚栓固定',
              desc: '采用 M10×130 化学锚栓将框体固定于结构墙体，固化 24h 后进入下一道工序。框体四周预留 15mm 注胶间隙，激光水平仪复核垂直度偏差 ≤ 2mm。',
              highlights: ['M10 化学锚栓', '24h 固化标准', '15mm 注胶间隙', '垂直度 ≤ 2mm']
            },
            {
              id: 'sample3',
              dataUrl: this.svgDataUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect fill="#dcfce7" width="400" height="300"/><text x="200" y="150" text-anchor="middle" fill="#166534" font-size="20">注胶密封</text><text x="200" y="180" text-anchor="middle" fill="#16a34a" font-size="12">硅酮结构胶</text></svg>`),
              category: '密封收口',
              time: '2026-06-24 13:53',
              title: '框墙接缝注胶密封',
              desc: '框体与结构墙体之间 15mm 缝隙，采用硅酮结构胶（GB/T 14683-2017）双道密封：内层结构胶 + 外层耐候胶，48h 完全固化后形成柔性防水屏障。',
              highlights: ['硅酮结构胶', '双道密封工艺', '48h 固化', '柔性防水屏障']
            }
          ];
          this.syncToReport();
          this.reportTitle = '框架施工归档（示例）';
          this.showToast('✅ 已载入示例数据，点「导出 PDF」可查看效果');
        },

        // ===== 工具 =====
        showToast(msg, type = 'info', duration = 3000) {
          this.toast = { show: true, msg, type };
          clearTimeout(this._toastTimer);
          this._toastTimer = setTimeout(() => this.toast.show = false, duration);
        }
      };
    }
