    // ═══════════════════════════════════════════════════════════════
    //  html2pdf 胶水层 v4.0.0 —— A4 规范化分页引擎（本地化，无 CDN 依赖）
    //
    //  ★ v4.0.0 核心重写：真正实现 pagebreak
    //    旧版缺陷：整页截一张大 canvas → 按「固定高度」一刀切
    //             → 卡片/图片被拦腰截断（跨页断层），pagebreak 配置是空转
    //    新版方案：渲染前采集所有「不可切割块」在页面中的 y 坐标区间
    //             → 切片时若切点落在某块内部，把切点上移到该块顶部
    //             → 该块整体推到下一页，永不被切开
    //
    //  配置项：
    //    margin:    [top, left, bottom, right]（mm）
    //    pagebreak: { avoid: ['.node-card', ...], after: ['.pdf-cover'] }
    //    footer:    { enabled, text（中文，预渲染成图）, pageLabel }
    //  用法：await html2pdf().set(opt).from(el).build();
    // ═══════════════════════════════════════════════════════════════
    (function () {
      // 把一段中文文本预渲染成透明底小图（jsPDF 原生字体不支持中文，只能贴图）
      function renderTextStrip(text) {
        if (!text || typeof window.html2canvas !== 'function') return Promise.resolve(null);
        var d = document.createElement('div');
        // 注意：用 fixed 移出可视区（仍在文档流内渲染，offsetWidth 正常）
        // 切勿用 detached DOM —— html2canvas 会算出 0 尺寸
        d.style.cssText = 'position:fixed;left:-99999px;top:0;z-index:-1;' +
          'font:500 10px/1.4 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;' +
          'color:#9a9488;letter-spacing:0.08em;white-space:nowrap;padding:1px 0;background:transparent;';
        d.textContent = text;
        document.body.appendChild(d);
        return window.html2canvas(d, { scale: 4, backgroundColor: null, logging: false })
          .then(function (c) {
            document.body.removeChild(d);
            return { dataUrl: c.toDataURL('image/png'), w: c.width, h: c.height };
          })
          .catch(function () {
            if (d.parentNode) document.body.removeChild(d);
            return null;   // 失败就降级为无中文条，不阻断导出
          });
      }

      function html2pdf() {
        var opt = {
          margin:       [14, 15, 16, 15],   // [top, left, bottom, right] mm
          filename:     'document.pdf',
          image:        { type: 'jpeg', quality: 0.95 },
          html2canvas:  { scale: 2, useCORS: true, logging: false, backgroundColor: '#ffffff' },
          jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
          pagebreak:    { avoid: [], after: [] },
          footer:       { enabled: false, text: '', pageLabel: '' }
        };
        var source = null;

        function set(o) {
          for (var k in o) {
            if (typeof opt[k] === 'object' && opt[k] !== null && !Array.isArray(opt[k])) {
              opt[k] = Object.assign({}, opt[k], o[k] || {});
            } else {
              opt[k] = o[k];
            }
          }
          return api;
        }
        function from(el) { source = (typeof el === 'string') ? document.querySelector(el) : el; return api; }

        // ── 渲染前：采集不可切割块 / 强制分页点（真实 DOM 坐标，单位 CSS px）──
        function collectBlocks() {
          var srcRect = source.getBoundingClientRect();
          var res = { atoms: [], forces: [], srcH: srcRect.height };
          var avoidSel = (opt.pagebreak && opt.pagebreak.avoid) || [];
          var afterSel = (opt.pagebreak && opt.pagebreak.after) || [];
          if (avoidSel.length) {
            source.querySelectorAll(avoidSel.join(',')).forEach(function (el) {
              var r = el.getBoundingClientRect();
              if (r.height > 1) res.atoms.push({ top: r.top - srcRect.top, bottom: r.bottom - srcRect.top });
            });
          }
          if (afterSel.length) {
            source.querySelectorAll(afterSel.join(',')).forEach(function (el) {
              var r = el.getBoundingClientRect();
              if (r.height > 1) res.forces.push(r.bottom - srcRect.top);
            });
          }
          res.atoms.sort(function (a, b) { return a.top - b.top; });
          res.forces.sort(function (a, b) { return a - b; });
          return res;
        }

        // 共享：渲染 source → 返回 jsPDF 实例（save / outputBlob 复用）
        function build() {
          if (!source) return Promise.reject(new Error('html2pdf: no source element'));
          if (typeof window.jspdf === 'undefined' || !window.jspdf.jsPDF) {
            return Promise.reject(new Error('html2pdf: jsPDF 未加载'));
          }
          if (typeof window.html2canvas === 'undefined') {
            return Promise.reject(new Error('html2pdf: html2canvas 未加载'));
          }

          var jsPDF = window.jspdf.jsPDF;
          var pdf = new jsPDF({
            unit:        opt.jsPDF.unit,
            format:      opt.jsPDF.format,
            orientation: opt.jsPDF.orientation
          });

          var pageW = pdf.internal.pageSize.getWidth();    // 210mm
          var pageH = pdf.internal.pageSize.getHeight();   // 297mm
          var m  = Array.isArray(opt.margin) ? opt.margin : [opt.margin, opt.margin, opt.margin, opt.margin];
          var mT = m[0] || 0, mL = m[1] || 0, mB = m[2] || 0, mR = m[3] || 0;
          var contentW = pageW - mL - mR;
          var contentH = pageH - mT - mB;

          // 采集必须在 html2canvas 之前（此时 DOM 布局已锁定为 A4 宽度）
          var blocks = collectBlocks();

          return renderTextStrip(opt.footer && opt.footer.enabled ? opt.footer.text : '')
            .then(function (strip) {
              return window.html2canvas(source, Object.assign({}, opt.html2canvas))
                .then(function (canvas) { return { canvas: canvas, strip: strip }; });
            })
            .then(function (bundle) {
              var canvas = bundle.canvas;
              var strip  = bundle.strip;

              // CSS px → canvas px 的换算比（用实测比例，比假定 scale 更准）
              var pxPerCss = blocks.srcH > 0 ? (canvas.height / blocks.srcH) : (opt.html2canvas.scale || 2);
              var ratio    = canvas.width / contentW;              // canvas px / mm
              var sliceMax = Math.floor(contentH * ratio);         // 一页最多容纳的 canvas 像素高

              var atoms  = blocks.atoms.map(function (b) {
                return { top: b.top * pxPerCss, bottom: b.bottom * pxPerCss };
              });
              var forces = blocks.forces.map(function (v) { return v * pxPerCss; });

              var pageCanvas = document.createElement('canvas');
              pageCanvas.width = canvas.width;
              var ctx = pageCanvas.getContext('2d');

              var y = 0, first = true, guard = 0;
              while (y < canvas.height - 2 && guard++ < 300) {
                var cut = Math.min(y + sliceMax, canvas.height);

                if (cut < canvas.height) {
                  var chosen = cut;

                  // (a) 避免切断原子块：块起点在本页内、终点超出切点 → 把切点提到块顶
                  //     ★ 前提：该块本身塞得进一页。若块高 > 一页（如超长卡片），
                  //       推到下一页照样放不下，反而制造一个只有几行的空页 → 直接硬切
                  for (var j = 0; j < atoms.length; j++) {
                    var b = atoms[j];
                    if ((b.bottom - b.top) <= sliceMax &&
                        b.top > y + 2 && b.top < cut && b.bottom > cut + 1) {
                      if (b.top < chosen) chosen = b.top;
                    }
                  }

                  // (b) 强制分页点（如封面之后必须换页）：取本页内最靠后的一个
                  var fcut = -1;
                  for (var i = 0; i < forces.length; i++) {
                    if (forces[i] > y + 4 && forces[i] <= cut && forces[i] > fcut) fcut = forces[i];
                  }
                  if (fcut > 0 && fcut < chosen) chosen = fcut;

                  // 兜底：切点至少要往前推进 10% 页高，防止死循环 / 大量空页
                  cut = Math.max(chosen, y + Math.floor(sliceMax * 0.10));
                  cut = Math.min(cut, canvas.height);
                }

                var h = Math.round(cut - y);
                if (h <= 0) break;

                pageCanvas.height = h;
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, pageCanvas.width, h);
                ctx.drawImage(canvas, 0, y, canvas.width, h, 0, 0, canvas.width, h);

                // ★ v4.0.0 修复：MIME 必须写全 'image/jpeg'。
                //   旧代码传 'jpeg'（无效 MIME）→ 浏览器静默退回 PNG，
                //   jsPDF 却按 JPEG 声明嵌入 → 实为未压缩位图，
                //   3 张图的报告能撑到 34MB，客户手机端打开必卡死。
                var sliceData = pageCanvas.toDataURL('image/' + opt.image.type, opt.image.quality);
                if (!first) pdf.addPage();
                // 注意：不传 compression 参数（'FAST' 在部分 jsPDF 构建不支持）
                pdf.addImage(sliceData, opt.image.type.toUpperCase(), mL, mT, contentW, h / ratio);
                first = false;
                y = cut;
              }

              // ── 每页统一页脚：金色细线 + 中文公司条 + 页码 ──
              if (opt.footer && opt.footer.enabled) {
                var total = pdf.internal.getNumberOfPages();
                var lineY = pageH - mB + 5.5;
                var textY = pageH - mB + 10.5;
                for (var p = 1; p <= total; p++) {
                  pdf.setPage(p);
                  pdf.setDrawColor(184, 146, 74);      // 商务金 #B8924A
                  pdf.setLineWidth(0.4);
                  pdf.line(mL, lineY, pageW - mR, lineY);

                  if (strip && strip.dataUrl) {
                    var sW = 46;                                   // 固定宽 46mm
                    var sH = sW * (strip.h / strip.w);
                    pdf.addImage(strip.dataUrl, 'PNG', mL, textY - sH + 1, sW, sH);
                  }

                  pdf.setFont('helvetica', 'normal');
                  pdf.setFontSize(8);
                  pdf.setTextColor(154, 148, 136);
                  var lbl = (opt.footer.pageLabel || '') +
                    ('0' + p).slice(-2) + ' / ' + ('0' + total).slice(-2);
                  pdf.text(lbl, pageW - mR, textY, { align: 'right' });
                }
                pdf.setPage(1);
              }

              return pdf;
            });
        }

        function save() {
          return build().then(function (pdf) { pdf.save(opt.filename); return pdf; });
        }

        // 产出 PDF 二进制 Blob（供原生「另存为」对话框 / 新标签页使用）
        function outputBlob() {
          return build().then(function (pdf) { return pdf.output('blob'); });
        }

        var api = { set: set, from: from, build: build, save: save, outputBlob: outputBlob };
        return api;
      }
      window.html2pdf = html2pdf;
    })();
