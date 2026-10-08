/* ================================================================
 * AI 视觉识别引擎（v5.x）：批量组织 / 单张重分析 / 视觉 API 调用 /
 *   多模型投票去重 / 健壮 JSON 提取 / 文案清洗评分
 *
 * 从 app-main.js 原样搬来（228–775 行，17 个方法，548 行）。这一块是
 * 「AI 整理」按钮背后的全部逻辑，原先内联在 Alpine 组件字面量里，vm 跑不动；
 * 搬出来之后 test-ai-vision-client.cjs 可以直接在干净上下文里跑纯逻辑
 * （extractJSONRobust / _findMatchingBrace / dedupeDesc / buildAnalysisPrompt …）。
 *
 * 【为什么成员缩进是 8 空格】
 * 刻意保持原样、逐字节搬移，由 test-app-main-splits.cjs 用 sha256 守护。
 * 不要为了「好看」重排缩进：块里有多行模板字符串（buildAnalysisPrompt 的
 * 提示词数组 join），整体加/减缩进会真的改掉字符串内容，而 HTML 里看不出来。
 *
 * 【依赖】
 *   1. 全局函数 scoreSiteLogText / polishSiteLogText、常量 AI_STYLE / NL
 *      来自 ai-style.js —— 因此本文件**必须排在 ai-style.js 之后加载**
 *      （index.html 里 ai-style.js 已经先加载）。
 *   2. 组件状态与跨 mixin 方法（this.images / this.showToast / this.syncToReport /
 *      this.compressDataUrl / this.proposeAI / this.runAIBatch …）全部定义在合并后的
 *      同一对象上，运行时解析，因此本文件与 app-main.js 的加载顺序**不影响** this.*。
 *      但 index.html 里仍排在 app-main.js 之前，保持与其它 mixin 一致。
 * ================================================================ */

window.aiVisionFeatures = {
        // ===== AI 视觉识别（批量：按分区成组，每组最多 8 张一次提交）=====
        async aiOrganizeAll() {
          if (this.processing || this.aiChecking) return;
          this.aiChecking = true;
          let ready;
          try { ready = await this.ensureCompanyAI(); }
          finally { this.aiChecking = false; }
          if (!ready) return;
          // 只分析还没有被 AI 分析过的照片（用 _analyzed 标记，而非检查 title）
          // 因为 ensureTitles 会在渲染时自动补 title 兜底值，不能用它判断是否已分析
          const todo = [
            ...this.images.filter(img => !img._analyzed && !Object.keys(img._manual || {}).length),
            ...this.arrivalImages.filter(img => !img._analyzed && !Object.keys(img._manual || {}).length),
            ...this.finishImages.filter(img => !img._analyzed && !Object.keys(img._manual || {}).length)
          ];
          if (todo.length === 0) {
            this.showToast('现有识别结果和人工内容已保留；需要新建议时请用单张“重分析”');
            return;
          }
          this.aiCancelRequested = false;
          this.processing = true;
          this.processedCount = 0;
          const failures = [];
          const BATCH_MAX = 8; // 与后端 BATCH_MAX 一致：单次最多 8 张
          const SECTION_CONTEXT = { construction: '施工过程照片', arrival: '班组进场照片', finish: '完工/离场照片' };
          // 按 section 分组，组内每 8 张一批（同一批用该分区的提示词与上下文）
          const groups = {};
          for (const img of todo) {
            const key = img.section || 'construction';
            (groups[key] = groups[key] || []).push(img);
          }
          const model = this.companyAIModel;
          const sectionNameOf = img => img.section === 'arrival' ? '进场照片' : (img.section === 'finish' ? '完工照片' : '施工节点');
          const indexOf = img => img.section === 'arrival' ? this.arrivalImages.indexOf(img) + 1 : (img.section === 'finish' ? this.finishImages.indexOf(img) + 1 : this.images.indexOf(img) + 1);
          try {
            outer:
            for (const [section, group] of Object.entries(groups)) {
              for (let i = 0; i < group.length; i += BATCH_MAX) {
                if (this.aiCancelRequested) break outer;
                const batch = group.slice(i, i + BATCH_MAX);
                batch.forEach(img => img.analyzing = true);
                const beforeArr = batch.map(img => JSON.stringify([img.title, img.desc, img.highlights, img._manual]));
                let result;
                try {
                  // 批量前先压缩超大连图，避免一次请求体积过大
                  const images = [];
                  for (const img of batch) {
                    let data = img.dataUrl;
                    if (data.length > 400 * 1024) data = await this.compressDataUrl(data);
                    images.push(data);
                  }
                  result = await this.runAIBatch(images, this.buildAnalysisPrompt(section), model, { context: SECTION_CONTEXT[section] || '工程照片' });
                } catch (e) {
                  batch.forEach((img, k) => {
                    if (beforeArr[k] === JSON.stringify([img.title, img.desc, img.highlights, img._manual])) {
                      img.title = `${sectionNameOf(img)} ${indexOf(img)}`;
                      img.desc = `[AI 识别失败] ${e.message}\n\n当前照片已保留，可稍后重试或手动填写。`;
                    }
                    img.aiError = e.message;
                    failures.push({ name: (img.file && img.file.name) || img.id, error: e.message });
                    img.analyzing = false;
                  });
                  this.processedCount += batch.length;
                  this.syncToReport();
                  continue;
                }
                // 后端返回 items 数组（与提交顺序一一对应）；长度不符则降级逐张单图识别
                let items = (result && Array.isArray(result.items)) ? result.items : null;
                if (items && items.length !== batch.length) items = null;
                if (!items) {
                  for (let k = 0; k < batch.length; k++) {
                    const img = batch[k];
                    const before = beforeArr[k];
                    try {
                      const candidate = { ...img, highlights: [...(img.highlights || [])], _manual: {} };
                      await this.analyzeImage(candidate);
                      this.applyCandidateAndAdopt(img, candidate, before);
                    } catch (e) {
                      if (before === JSON.stringify([img.title, img.desc, img.highlights, img._manual])) {
                        img.title = `${sectionNameOf(img)} ${indexOf(img)}`;
                        img.desc = `[AI 识别失败] ${e.message}\n\n当前照片已保留，可稍后重试或手动填写。`;
                      }
                      img.aiError = e.message;
                      failures.push({ name: (img.file && img.file.name) || img.id, error: e.message });
                    } finally {
                      img.analyzing = false;
                    }
                  }
                  this.processedCount += batch.length;
                  this.syncToReport();
                  continue;
                }
                batch.forEach((img, k) => {
                  const candidate = { ...img, highlights: [...(img.highlights || [])], _manual: {} };
                  const r = items[k] || {};
                  r._model = result.model || model;
                  this.applyAnalysisResult(candidate, r, model);
                  this.applyCandidateAndAdopt(img, candidate, beforeArr[k]);
                  img.analyzing = false;
                });
                this.processedCount += batch.length;
                this.syncToReport();
              }
            }
            if (this.aiCancelRequested) { this.showToast('已停止后续识别，现有内容已保留'); }
            else if (failures.length === 0) { this.showToast(`✨ AI 整理完成，本次共处理 ${this.processedCount} 张（已批量提交，更快更稳）— 点击文字可直接修改，导出时自动保留您的修改`); }
            else { this.showToast(`⚠️ ${failures.length} 张识别失败：${failures[0].error.slice(0, 80)}`, 'error'); }
          } finally {
            this.processing = false;
          }
        },

        // 识别完成后：若期间用户没手改文字，则直接采用；否则给出建议待确认
        applyCandidateAndAdopt(img, candidate, before) {
          if (before === JSON.stringify([img.title, img.desc, img.highlights, img._manual])) {
            for (const key of ['title','desc','category','stage','highlights','uncertainties','aiConfirmed','_analyzed','aiError','aiSource']) img[key] = candidate[key];
            img.aiBaseline = { title: candidate.title, desc: candidate.desc, category: candidate.category, highlights: [...(candidate.highlights || [])], source: candidate.aiSource || {}, capturedAt: new Date().toISOString() };
          } else {
            this.proposeAI(img, candidate);
            this.showToast('识别期间你修改了文字，新建议需确认后才会采用');
          }
        },

        async reAnalyze(img) {
          if (this.processing || this.aiChecking || img.analyzing) return;
          this.aiChecking = true;
          let ready;
          try { ready = await this.ensureCompanyAI(); }
          finally { this.aiChecking = false; }
          if (!ready) return;
          img.analyzing = true;
          try {
            const candidate = { ...img, highlights: [...(img.highlights || [])], _manual: {} };
            await this.analyzeImage(candidate);
            this.proposeAI(img, candidate);
            this.showToast('新建议已生成，请比较后选择采用或保留当前内容');
          } catch (e) {
            this.showToast('❌ 识别失败：' + e.message, 'error');
          } finally {
            img.analyzing = false;
          }
        },

        // 重建 innerHTML 前，先把用户在 contenteditable 里的编辑回写到 img 数据，
        // 否则 syncToReport 会用旧数据覆盖掉用户手改的标题/描述/亮点
        captureDomEdits() {
          // 通用回写：施工节点 / 班组进场 / 完工照片 三个分区的手改文字 → img 数据。
          // 必须在任何画廊重建之前调用，否则重建会用旧数据冲掉用户编辑。
          const isPlaceholder = v =>
            v.includes('请补充') || v.includes('[AI 识别失败') || v.includes('[请填写') || v.startsWith('📝');
          const capture = (block, img) => {
            if (!img) return;
            const titleEl = block.querySelector('h3');
            const descEl = block.querySelector('.node-card-desc');
            const hlBadges = block.querySelectorAll('.highlight-badge');
            if (titleEl) {
              const t = titleEl.innerText.trim();
              if (t && !isPlaceholder(t)) img.title = t;
            }
            // ⚠️ 关键防护：只有用户手写的非占位符内容才回写。
            //    DOM 若是系统占位符，说明 analyzeImage 未完成或为兜底值，
            //    此时绝不能写回 img 对象——否则会覆盖真实 AI 结果。
            if (descEl) {
              const val = descEl.innerText.trim();
              if (val && !isPlaceholder(val)) img.desc = val;
              else console.log(`🛡️ captureDomEdits: 跳过占位符回写 (img=${img.file?.name||img.id}, dom="${val.slice(0,30)}...")`);
            }
            if (hlBadges.length) {
              const hls = Array.from(hlBadges)
                .map(b => b.innerText.replace(/^✦\s*/, '').trim())
                .filter(Boolean);
              if (hls.length) img.highlights = hls;
            }
          };
          // 1 对 1 阶段按框循环后容器是 images-container-f0 / arrival-gallery-f0，
          // 因此用前缀匹配；旧模板的 images-container / arrival-gallery 同样命中。
          document.querySelectorAll('[id^="images-container"] .node-block').forEach(block =>
            capture(block, this.images.find(i => i.id === block.dataset.imgId)));
          document.querySelectorAll('[id^="arrival-gallery"] .node-block').forEach(block =>
            capture(block, this.arrivalImages.find(i => i.id === block.dataset.arrivalId)));
          document.querySelectorAll('#finish-gallery .node-block').forEach(block =>
            capture(block, this.finishImages.find(i => i.id === block.dataset.finishId)));
        },

        // 最终安全网：syncToReport 渲染前扫描，确保每张图都有 title 和 desc
        // —— 即使 analyzeImage 兜底失效或被异常跳过，用户也永远看不到「未命名节点」
        ensureTitles() {
          const SAFE = {
            '框架施工':  { title: '框体就位与水平校准' },
            '框架1对1':  { title: '框架单扇校正节点' },
            '玻扇施工':  { title: '中空玻璃合片工艺' },
            '玻扇1对1':  { title: '玻扇单扇调试节点' },
            '五金安装':  { title: '门窗五金件安装调试' },
            '密封收口':  { title: '框墙接缝密封收口' },
            '成品保护':  { title: '门窗成品保护与自检' },
            '离场自检':  { title: '离场前合规留底' },
          };
          const aliasMap = {
            '框架1对1': ['框架1对1','一对一框架','门洞校正','单扇校正','调校'],
            '框架施工': ['框架','框体','立框','装框'],
            '玻扇1对1': ['玻扇1对1','一对一玻扇','单扇调试','调缝'],
            '玻扇施工': ['玻璃','玻扇','玻璃施工','合片','装玻璃','挂扇','扇'],
            '五金安装': ['五金','把手','锁具','铰链','合页'],
            '密封收口': ['密封','收口','打胶','注胶','填缝'],
            '成品保护': ['成品','保护','保护膜','完工','自检'],
            '离场自检': ['离场','关门','关水','关电','清场','留底'],
          };
          const resolve = (cat) => {
            for (const [k, aliases] of Object.entries(aliasMap)) {
              if (cat === k || cat.includes(k) || k.includes(cat) || aliases.some(a => cat.includes(a) || a.includes(cat))) return k;
            }
            return cat;
          };
          let fixed = 0;
          this.images.forEach(img => {
            if (!img.title || !img.title.trim()) {
              const k = resolve(img.category || '');
              img.title = (SAFE[k] && SAFE[k].title) || `${img.category || '施工'}节点`;
              fixed++;
            }
            if (!img.desc || !img.desc.trim()) {
              const k = resolve(img.category || '');
              img.desc = '📝 请补充本张照片的具体工艺说明';
              fixed++;
            }
          });
          if (fixed > 0) console.log(`🛡️ ensureTitles: 补全 ${fixed} 个空字段`);
        },

        async analyzeImage(img) {
          const model = this.companyAIModel;
          const result = await this.callVisionAPI(img.dataUrl, this.buildAnalysisPrompt(img.section || 'construction'), model);
          this.applyAnalysisResult(img, result, model);
        },

        // 把模型返回的解析结果落到 img（单图与批量复用同一套字段映射）
        applyAnalysisResult(img, result, model) {
          if (result._noJson || !result.desc) {
            img._analyzed = true;
            img.aiError = 'AI 返回内容不完整，请保留照片并重试';
            return;
          }
          const categories = ['框架施工','玻扇施工','五金安装','密封收口','成品保护','其他'];
          img.category = img.section === 'arrival' ? '班组进场' : img.section === 'finish' ? '完工照片' : categories.includes(result.category) ? result.category : '其他';
          img.title = result.title || '待核实节点';
          img.desc = result.desc;
          img.stage = result.stage || '';
          img.highlights = Array.isArray(result.highlights) ? result.highlights : [];
          img.uncertainties = Array.isArray(result.uncertainties) ? result.uncertainties : ['尺寸、安装精度与验收结论需结合现场记录核实'];
          img.aiConfirmed = false;
          img._analyzed = true;
          img.aiError = '';
          img.aiSource = { model: result._model || model, generatedAt: new Date().toISOString(), kind: 'AI 建议，待人工确认' };
        },

        buildAnalysisPrompt(section = 'construction') {
          const role = AI_STYLE.ROLE;
          const rules = '写作铁律（违反即不合格）：' + NL + AI_STYLE.RULES.split(NL).map((r, i) => (i + 1) + '. ' + r).join(NL);
          const glossary = '行业术语库（优先使用）：' + NL + AI_STYLE.GLOSSARY;
          const formula = AI_STYLE.FORMULA;
          const common = [
            role, '',
            rules, '',
            glossary, '',
            formula, '',
            '输出格式（纯 JSON，不要 markdown 代码块，不要任何解释文字）：'
          ].join(NL);

          if (section === 'arrival') {
            return [
              common,
              '{',
              '  "title": "进场工序名，8-16字，只写工序，不带形容词",',
              '  "stage": "当前准备进度，8-18字，如：材料到场待验收 / 洞口复核中 / 安全交底完成",',
              '  "desc": "节点说明，50-110字，按写作公式写成一两句连贯的工程书面语",',
              '  "highlights": ["要点1", "要点2", "要点3"]',
              '}',
              '',
              '本节点场景：' + NL + AI_STYLE.SECTION.arrival,
              '',
              '❌ 反面（会被判废）："班组已到达现场" / "照片中可以看到工人和材料" / "进场准备工作充分，工艺精湛"',
              '✅ 正面："60系列断桥铝型材带原厂保护膜进场，按规格分层码放于室内干燥地面，底部垫木方防潮，待核对壁厚与表面处理后转入洞口复核工序。"',
              '✅ 正面："洞口基层已剔凿找平，激光水平仪复核洞口宽高与设计值偏差在允许范围内，两侧预留安装间隙满足框体就位要求。"'
            ].join(NL);
          }
          if (section === 'finish') {
            return [
              common,
              '{',
              '  "title": "完工工序名，8-16字，只写工序，不带形容词",',
              '  "stage": "交付状态，8-18字，如：整体完工待验收 / 细部收口完成 / 成品保护到位",',
              '  "desc": "节点说明，50-110字，按写作公式写成一两句连贯的工程书面语",',
              '  "highlights": ["要点1", "要点2", "要点3"]',
              '}',
              '',
              '本节点场景：' + NL + AI_STYLE.SECTION.finish,
              '',
              '❌ 反面（会被判废）："门窗安装完成" / "照片中展示了安装好的窗户" / "整体效果美观，做工精细"',
              '✅ 正面："推拉门整体安装完成，室外侧框墙接缝硅酮耐候密封胶饱满连续无断点，披水板排水孔通畅，玻璃保护膜保留待业主验收后撕除。"',
              '✅ 正面："开启扇执手启闭灵活，锁点锁座啮合到位，关闭后无自开现象；五金传动器已调试，扇体四周间隙均匀。"'
            ].join(NL);
          }
          return [
            common,
            '{',
            '  "title": "工序名，8-16字，只写工序，不带形容词",',
            '  "category": "分类，只能取：框架施工 / 玻扇施工 / 五金安装 / 密封收口 / 成品保护 / 离场自检",',
            '  "stage": "当前施工进度，8-18字，如：框体就位待固定 / 注胶完成待固化",',
            '  "desc": "节点说明，50-110字，按写作公式写成一两句连贯的工程书面语",',
            '  "highlights": ["要点1", "要点2", "要点3"]',
            '}',
            '',
            '本节点场景：' + NL + AI_STYLE.SECTION.construction,
            '',
            '分类判定标准：',
            '- 框架施工：只有铝合金框体立在或固定在洞口，未见玻璃与窗扇',
            '- 玻扇施工：玻璃已装入框体，可见玻璃反光 / 铝隔条 / 完整窗扇',
            '- 五金安装：画面主体为执手 / 锁具 / 铰链滑撑 / 传动器等金属件',
            '- 密封收口：框体与墙体之间打胶、塞泡沫棒、贴防水膜等收口动作',
            '- 成品保护：保护膜张贴、工地清理、完工待验收状态',
            '- 离场自检：含水印（树立门窗最后一道防火墙 / 初匠门窗安装服务中心），或拍到关闭的水阀、跳闸的电箱、关闭的门窗、打包清运的垃圾',
            '',
            '❌ 反面（会被判废）："中空玻璃已合片装入框体" / "照片中可以看到窗框" / "施工规范，质量良好"',
            '✅ 正面："框体采用 M10 化学锚栓穿透固定片与结构墙连接，四周预留 15mm 注胶间隙，激光水平仪复核垂直度偏差 ≤ 2mm 后转入注胶工序。"',
            '✅ 正面："框墙缝隙先嵌泡沫棒作背衬，再打硅酮耐候密封胶，胶缝连续饱满无断点、无气泡，形成外侧第一道防雨屏障。"',
            '✅ 正面："离场自检留底：总水阀已关闭、配电箱漏电保护器处于分闸位、门窗全部落锁，建筑垃圾装袋清运出场。"'
          ].join(NL);
        },

        // ─── v4.6：跨照片去重 ───
        // 模型偶尔对同一批照片输出同一句说明（"每张都一样"是客户最反感的点）。
        // 若新文案与已有照片高度雷同，先尝试换成其它模型的版本，都没有才保留并打标。
        dedupeDesc(img, votes) {
          const norm = (s) => (s || '').replace(/[\s，。、；：""''（）()]/g, '');
          const bigrams = (s) => {
            const set = new Set();
            for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
            return set;
          };
          const similarity = (a, b) => {
            a = norm(a); b = norm(b);
            if (!a || !b) return 0;
            if (a === b) return 1;
            const A = bigrams(a), B = bigrams(b);
            if (!A.size || !B.size) return 0;
            let inter = 0;
            A.forEach(x => { if (B.has(x)) inter++; });
            return inter / (A.size + B.size - inter);
          };
          const pool = [...(this.images || []), ...(this.arrivalImages || []), ...(this.finishImages || [])];
          const others = pool.filter(x => x && x !== img && x._analyzed && x.desc).map(x => x.desc);
          if (!others.length) return;

          const isDup = (d) => others.some(o => similarity(d, o) > 0.72);
          if (!isDup(img.desc)) return;

          // 找一条不与已有照片雷同的替代文案（按质量分从高到低）
          const alt = (votes || [])
            .filter(v => v.desc && !isDup(v.desc))
            .sort((a, b) => (b._score || 0) - (a._score || 0))[0];
          if (alt) {
            console.log('🔁 文案与已有照片雷同，已换成其它模型的版本');
            img.desc = alt.desc;
            img.title = (alt.title || '').trim() || img.title;
            img.highlights = Array.isArray(alt.highlights) && alt.highlights.length ? alt.highlights : img.highlights;
            return;
          }
          img._dupDesc = true;
          console.warn('⚠️ 多个模型输出的说明均与已有照片雷同，已打标提示人工补充');
        },

        // 重复说明的界面提示（details.debug-panel 在导出 PDF / 分享时会被自动移除）
        dupWarnHtml(img) {
          if (!img || !img._dupDesc) return '';
          return '<details class="mb-2 bg-amber-50 border border-amber-200 rounded p-2 text-xs debug-panel">' +
            '<summary class="cursor-pointer font-bold text-amber-700">⚠️ 本张说明与另一张照片雷同，建议人工补一句差异点</summary></details>';
        },

        // ─── 客户端图片特征检测 ───
        // 简单的像素统计：检测玻璃反光（高亮像素比例）、深色框体像素、暖色（室内）冷色（室外）
        async callVisionAPI(imageDataUrl, prompt, modelOverride) {
          if (imageDataUrl.length > 400 * 1024) imageDataUrl = await this.compressDataUrl(imageDataUrl);
          const config = { model: this.companyAIModel || modelOverride };
          const data = await this.runAIJob(imageDataUrl, prompt, config.model);
          if (['length','max_tokens'].includes(data.choices?.[0]?.finish_reason)) throw Error('AI 输出达到长度上限，结果已截断；照片已保留，请稍后重试');
          const rawContent = data.choices[0].message.content;

          // 智能提取 JSON（兼容 markdown 代码块、前后废话、键名差异、多余花括号等）
          const parsed = this.extractJSONRobust(rawContent);

          // 归一化 category
          if (parsed && parsed.category) {
            parsed.category = parsed.category.trim();
          }
          // 挂模型名用于调试追踪
          parsed._model = data.model || config.model || 'unknown';
          return parsed;
        },

        // ─── 鲁棒 JSON 提取（根治 desc 丢失）───
        // 旧实现用贪婪正则 /\{[\s\S]*\}/ —— 从第一个 { 匹配到最后一个 }，
        // 一旦返回里夹杂任何多余花括号（解释文字/嵌套）就整段解析失败，desc 全丢。
        // 新实现：① 整段直解 ② 平衡花括号定位 ③ 容错修复 ④ 逐字段正则抠取。
        // 且 desc 做多键名归一化（desc/description/描述/工艺说明…），杜绝「键名不对就丢」。
        extractJSONRobust(raw) {
          if (typeof raw !== 'string' || !raw) return { _raw: '', _noJson: true };
          // 部分服务商将推理区和最终答案放在同一 content；推理中的示例不是工程结果。
          raw = raw.replace(/<(think|thinking)>[\s\S]*?<\/\1>/gi, '').replace(/<(?:think|thinking)>[\s\S]*$/gi, '').trim();
          if (!raw) return { _raw: '', _noJson: true };

          // 1) 整段直接解析（纯 JSON 情况）
          try {
            const p = JSON.parse(raw.trim());
            if (p && typeof p === 'object') return this._normalizeParsed(p, raw);
          } catch (e) { /* 继续 */ }

          // 2) 遍历所有 { 位置，找「能解析且字段最全」的 JSON 对象。
          //    避免首个 { 误抓到解释文字里的小括号对（如「这是{玻扇施工}阶段」）。
          let best = null, bestScore = -1;
          for (let i = raw.indexOf('{'); i >= 0; i = raw.indexOf('{', i + 1)) {
            const end = this._findMatchingBrace(raw, i);
            if (end <= i) continue;
            const cand = raw.slice(i, end + 1);
            let obj = null;
            try { obj = JSON.parse(cand); } catch (e) { obj = null; }
            if (!obj || typeof obj !== 'object') {
              // 3a) 容错修复：去尾逗号 + 未引号键
              try {
                const fixed = cand
                  .replace(/,\s*([}\]])/g, '$1')
                  .replace(/([{,])\s*([A-Za-z_\u4e00-\u9fa5]+)\s*:/g, '$1"$2":');
                obj = JSON.parse(fixed);
              } catch (e2) {
                // 3b) 纯单引号 JSON → 全部转双引号（兼容旧式返回）
                if (cand.includes("'") && !cand.includes('"')) {
                  try { obj = JSON.parse(cand.replace(/'/g, '"')); } catch (e3) { obj = null; }
                }
              }
            }
            if (obj && typeof obj === 'object') {
              const score = (obj.title ? 1 : 0)
                + (obj.desc || obj.description || obj['描述'] ? 1 : 0)
                + (obj.category ? 1 : 0)
                + (obj.highlights ? 1 : 0);
              if (score >= bestScore) { bestScore = score; best = obj; }
            }
          }
          if (best) return this._normalizeParsed(best, raw);

          // 4) 完全解析不了 → 逐字段正则抠取（最差情况也尽量保留信息）
          const byField = this._extractFieldsByRegex(raw);
          if (byField) return byField;

          // 5) 彻底没 JSON：保留原文，desc 兜底里尝试从原文抽一句
          console.warn('⚠️ AI 返回中未找到可解析 JSON，原始内容前200字:', raw.slice(0, 200));
          return { _raw: raw.slice(0, 600), _noJson: true };
        },

        _findMatchingBrace(s, start) {
          let depth = 0, inStr = false, esc = false;
          for (let i = start; i < s.length; i++) {
            const c = s[i];
            if (esc) { esc = false; continue; }
            if (c === '\\') { esc = true; continue; }
            if (c === '"') { inStr = !inStr; continue; }
            if (inStr) continue;
            if (c === '{') depth++;
            else if (c === '}') { depth--; if (depth === 0) return i; }
          }
          return -1;
        },

        _normalizeParsed(p, raw) {
          // 多键名归一化：模型可能用不同字段名表达「工艺说明」
          const descKeys = ['desc','description','描述','工艺说明','说明','caption','detail','内容','备注'];
          let desc = '';
          for (const k of descKeys) {
            if (typeof p[k] === 'string' && p[k].trim()) { desc = p[k].trim(); break; }
          }
          // JSON 里没有 desc，但从自然语言原文抽一句兜底（仍比占位符有价值）
          if (!desc) desc = this._extractSentenceFromRaw(raw);

          // ── v4.6 文案清洗：拍照腔 / 套话 / emoji / 引号 在入库前全部清掉 ──
          const polishTitle = (t) => {
            let s = polishSiteLogText(t, { maxLen: 24 }).replace(/[。！？；]$/, '');
            // 标题不要括号补充说明与破折号后缀
            s = s.replace(/[（(][^）)]*[）)]\s*$/, '').replace(/\s*[-—–].*$/, '').trim();
            return s;
          };
          const polishHl = (arr) => (arr || [])
            .map(h => polishSiteLogText(h, { maxLen: 22 }).replace(/[。！？；]$/, ''))
            .filter(h => h && h.length >= 3 && !AI_STYLE.GENERIC.some(g => h.includes(g)))
            .slice(0, 4);

          const cleanTitle = polishTitle(p.title);
          // minLen=14：剥掉拍照腔/套话后不足 14 个有效字，视为无效文案，走兜底
          const cleanDesc  = polishSiteLogText(desc, { maxLen: 200, minLen: 14 });
          const cleanStage = polishSiteLogText(p.stage, { maxLen: 26 }).replace(/[。！？；]$/, '');

          return {
            title:     cleanTitle,
            category:  typeof p.category === 'string' ? p.category.trim() : '',
            stage:     cleanStage,
            desc:      cleanDesc,
            highlights: polishHl(Array.isArray(p.highlights) ? p.highlights.filter(x=>typeof x==='string') : []),
            uncertainties: Array.isArray(p.uncertainties) ? p.uncertainties.filter(x=>typeof x==='string').slice(0,10) : [],
            _raw:      raw ? raw.slice(0, 600) : '',
            // 评分用：清洗后的文案质量（越高越专业）
            _score:    scoreSiteLogText(cleanDesc, cleanTitle, (p.category || '').trim())
          };
        },

        _extractFieldsByRegex(raw) {
          const get = (key) => {
            const m = raw.match(new RegExp('"?' + key + '"?\\s*[:：]\\s*"?([^"\\n,}]*)"?', 'i'));
            return m ? m[1].trim().replace(/^["'「『]|["'」』]$/g, '') : '';
          };
          const title = get('title');
          const category = get('category');
          const stage = get('stage');
          const desc = get('desc') || get('description') || get('描述') || get('工艺说明') || this._extractSentenceFromRaw(raw);
          // 亮点只从 "highlights": [...] 数组里取，避免误抓键名/其它引号串
          const hlMatch = raw.match(/"highlights"\s*:\s*\[([\s\S]*?)\]/i);
          const hl = hlMatch ? [...hlMatch[1].matchAll(/"([^"]{1,40})"/g)].map(m => m[1]) : [];
          if (!title && !desc && !category) return null;
          return { title, category, stage, desc: desc || '', highlights: hl, _raw: raw.slice(0, 600) };
        },

        _extractSentenceFromRaw(raw) {
          const cleaned = raw.replace(/```json|```|[\{\}\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
          const m = cleaned.match(/[一-龥][^。！？\n]{6,60}[。！？]?/);
          return m ? m[0].trim() : '';
        },

        async testConnection() {
          this.testing = true;
          this.testResult = '';
          try {
            // 用一张 1x1 透明 PNG 测试
            const testImg = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
            const result = await this.callVisionAPI(testImg, '请回复 JSON: {"ok": true, "msg": "连接正常"}');
            this.testResult = '<div class="p-2 bg-green-50 text-green-800 rounded">✅ 连接正常！模型已就绪。</div>';
          } catch (e) {
            this.testResult = `<div class="p-2 bg-red-50 text-red-800 rounded">❌ 连接失败：${e.message}</div>`;
          } finally {
            this.testing = false;
          }
        },
};
