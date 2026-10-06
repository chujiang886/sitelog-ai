/* ================================================================
 * 归档报告模板（专业版 v3 · 墨绿+金商务配色）
 *
 * 从 app-main.js 原样搬来：763 行模板字符串，占该文件近三成行数，
 * 但全是数据、没有逻辑 —— 和后端把业主侧模板抽到 views.py 是同一件事。
 *
 * 约定：
 *   1. 内容逐字节保持原样，由 test_templates_split.py / test-stage-parity.cjs 用 sha256 守护；
 *   2. 纯数据，不 import、不依赖任何运行时状态；
 *   3. 顶层 const（非 module），app-main.js 直接引用 —— 因此本文件
 *      **必须在 app-main.js 之前加载**（index.html 里的顺序不能颠倒）。
 * ================================================================ */
    // ====== 模板定义（专业版 v3 · 墨绿+金商务配色）======
    const TEMPLATES = {
      frame: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">工程影像归档</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">ENGINEERING ARCHIVE</p>
            <h1 class="pdf-cover-main-title">框架施工归档</h1>
            <p class="pdf-cover-tagline">精工艺 · 守标准 · 留凭证</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、阶段实施概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">阶段实施概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
本次框架施工整体进度与实施概况：施工范围、阶段目标、已完成工序、当前状态、下一步计划及总体质量把控要点。建议 100-200 字。
          </div>
        </section>

        <!-- ═══ 二、班组进场 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">二</span>
            <span class="pdf-section-title">班组进场</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="arrival-gallery">
            <!-- syncArrivalGallery() 动态渲染：人员到位、材料到场、安全交底等进场照片 -->
          </div>
        </section>

        <!-- ═══ 三、施工节点 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">三</span>
            <span class="pdf-section-title">施工节点</span>
            <span class="pdf-section-line"></span>
          </div>
          <div id="images-container"></div>
        </section>

        <!-- ═══ 四、完工照片 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">完工照片</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="finish-gallery">
            <!-- syncFinishGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 五、班组离场 SOP ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">五</span>
            <span class="pdf-section-title">班组离场 SOP</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 六、业主使用与维护建议 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">六</span>
            <span class="pdf-section-title">业主使用与维护建议</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
1. 定期检查：每年 1-2 次的五金保养、密封胶检查<br>2. 应急联系：售后服务电话 / 微信<br>📱 客服微信号：plf32118（售后咨询 · 预约保养）
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「用精工艺，给您一个可追溯的家」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `,

      glass: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">工程影像归档</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">ENGINEERING ARCHIVE</p>
            <h1 class="pdf-cover-main-title">玻扇施工归档</h1>
            <p class="pdf-cover-tagline">精工艺 · 守标准 · 留凭证</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、阶段实施概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">阶段实施概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
本次玻扇施工整体进度与实施概况：施工范围、阶段目标、已完成工序、当前状态、下一步计划及总体质量把控要点。建议 100-200 字。
          </div>
        </section>

        <!-- ═══ 二、班组进场 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">二</span>
            <span class="pdf-section-title">班组进场</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="arrival-gallery">
            <!-- syncArrivalGallery() 动态渲染：人员到位、材料到场、安全交底等进场照片 -->
          </div>
        </section>

        <!-- ═══ 三、施工节点 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">三</span>
            <span class="pdf-section-title">施工节点</span>
            <span class="pdf-section-line"></span>
          </div>
          <div id="images-container"></div>
        </section>

        <!-- ═══ 四、完工照片 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">完工照片</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="finish-gallery">
            <!-- syncFinishGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 五、班组离场 SOP ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">五</span>
            <span class="pdf-section-title">班组离场 SOP</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 六、业主使用与维护建议 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">六</span>
            <span class="pdf-section-title">业主使用与维护建议</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
玻扇的日常使用与维护建议，重点是五金保养和玻璃清洁。<br>📱 客服微信号：plf32118（售后咨询 · 预约保养）
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「用精工艺，给您一个可追溯的家」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `,

      hardware: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">工程影像归档</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">ENGINEERING ARCHIVE</p>
            <h1 class="pdf-cover-main-title">五金安装归档</h1>
            <p class="pdf-cover-tagline">精工艺 · 守标准 · 留凭证</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、阶段实施概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">阶段实施概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
[请编辑：本次五金安装的整体进度。]
          </div>
        </section>

        <!-- ═══ 二、五金安装工艺详解 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">二</span>
            <span class="pdf-section-title">五金安装工艺详解</span>
            <span class="pdf-section-line"></span>
          </div>
          <div id="images-container"></div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「用精工艺，给您一个可追溯的家」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
        </footer>
      `,

      departure: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">安全合规留底</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">SAFETY COMPLIANCE</p>
            <h1 class="pdf-cover-main-title">离场前自检 · 安全合规留底</h1>
            <p class="pdf-cover-tagline">关水 · 关电 · 关门 · 清场</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、离场合规总览 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">离场合规总览</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
[请编辑：本次离场前自检的整体说明。建议覆盖：项目名称、施工班组、自检日期、自检人、下道工序衔接安排。100-200 字为宜。]
          </div>
        </section>

        <!-- ═══ 二、四项合规自检 · 影像归档 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">二</span>
            <span class="pdf-section-title">四项合规自检 · 影像归档</span>
            <span class="pdf-section-line"></span>
          </div>
          <div id="images-container"></div>
          <div class="pdf-grid-2 mt-6">
            <div class="pdf-check-card pdf-check-green">
              <p class="pdf-check-title"><span>💧</span>水源关闭</p>
              <p class="pdf-check-desc">现场用水阀门归零位、临时水管卸压</p>
            </div>
            <div class="pdf-check-card pdf-check-gold">
              <p class="pdf-check-title"><span>⚡</span>电源关闭</p>
              <p class="pdf-check-desc">配电箱断路器归零位、临时用电插座拔除</p>
            </div>
            <div class="pdf-check-card pdf-check-green">
              <p class="pdf-check-title"><span>🚪</span>大门关闭</p>
              <p class="pdf-check-desc">入户门 / 阳台门关闭上锁、钥匙移交</p>
            </div>
            <div class="pdf-check-card pdf-check-neutral">
              <p class="pdf-check-title"><span>🗑️</span>垃圾清场</p>
              <p class="pdf-check-desc">施工余料 / 包装 / 边角料打包成捆、定点堆放</p>
            </div>
          </div>
        </section>

        <!-- ═══ 三、自检结论与离场声明 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">三</span>
            <span class="pdf-section-title">自检结论与离场声明</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 四、影像追溯体系 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">影像追溯体系</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-grid-3">
            <div class="pdf-info-card">
              <div class="pdf-info-card-icon">📸</div>
              <p class="pdf-info-card-title">影像性质</p>
              <p class="pdf-info-card-desc">所有照片均为现场实拍，含拍摄人/时间/定位水印，可作为第三方追溯凭证</p>
            </div>
            <div class="pdf-info-card">
              <div class="pdf-info-card-icon">🔍</div>
              <p class="pdf-info-card-title">影像要素</p>
              <p class="pdf-info-card-desc">四项合规事项逐一留底（关水/关电/关门/清场），照片可直观佐证离场状态</p>
            </div>
            <div class="pdf-info-card">
              <div class="pdf-info-card-icon">📦</div>
              <p class="pdf-info-card-title">影像归档</p>
              <p class="pdf-info-card-desc">原图随本档案一并交付业主保存</p>
            </div>
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「安全离场 · 责任交接 · 凭证留底」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `,

      // ═══ 吊装施工（P2 新增）═══
      // 大件型材/整窗吊装就位阶段的归档。风险点是高处作业与成品磕碰，
      // 所以版式把「安全交底」和「成品保护」单独成节，不并进施工节点。
      lifting: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">高处作业留证</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">HOISTING &amp; LIFTING</p>
            <h1 class="pdf-cover-main-title">吊装施工归档</h1>
            <p class="pdf-cover-tagline">复核 · 试吊 · 就位 · 保护</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、吊装作业概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">吊装作业概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
本次吊装施工整体情况：吊装部位与楼层、构件规格与重量、使用吊具与设备、作业人数与分工、当日天气与风力、起吊与就位时间、总体安全与质量控制要点。建议 100-200 字。
          </div>
        </section>

        <!-- ═══ 二、班组进场与安全交底 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">二</span>
            <span class="pdf-section-title">班组进场与安全交底</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="arrival-gallery">
            <!-- syncArrivalGallery() 动态渲染：人员到位、吊具检查、警戒区设置、安全交底等 -->
          </div>
        </section>

        <!-- ═══ 三、吊装作业节点 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">三</span>
            <span class="pdf-section-title">吊装作业节点</span>
            <span class="pdf-section-line"></span>
          </div>
          <div id="images-container"></div>
          <div class="pdf-grid-2 mt-6">
            <div class="pdf-check-card pdf-check-gold">
              <p class="pdf-check-title"><span>📐</span>洞口复核</p>
              <p class="pdf-check-desc">吊装前复核洞口尺寸、垂直度与水平基准，误差控制在规范范围内</p>
            </div>
            <div class="pdf-check-card pdf-check-green">
              <p class="pdf-check-title"><span>🪢</span>吊具检查</p>
              <p class="pdf-check-desc">吊带 / 吸盘 / 吊点逐一检查，确认无破损、无超载</p>
            </div>
            <div class="pdf-check-card pdf-check-green">
              <p class="pdf-check-title"><span>⬆️</span>试吊与就位</p>
              <p class="pdf-check-desc">先离地试吊确认平衡，再缓慢提升就位，全程设专人指挥</p>
            </div>
            <div class="pdf-check-card pdf-check-neutral">
              <p class="pdf-check-title"><span>🛡️</span>成品保护</p>
              <p class="pdf-check-desc">型材表面贴膜保留，落地垫软性材料，防止磕碰划伤</p>
            </div>
          </div>
        </section>

        <!-- ═══ 四、就位固定与成品保护 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">就位固定与成品保护</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="finish-gallery">
            <!-- syncFinishGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 五、班组离场 SOP ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">五</span>
            <span class="pdf-section-title">班组离场 SOP</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 六、吊装安全提示 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">六</span>
            <span class="pdf-section-title">吊装安全提示</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
1. 风力超过 5 级或雨天禁止室外吊装作业<br>2. 吊装作业区下方设警戒，严禁人员穿行或停留<br>3. 构件就位后未固定完成前，不得松开吊具<br>📱 客服微信号：plf32118（售后咨询 · 预约保养）
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「吊装稳一分，业主安十分」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `,

      // ═══ 售后保养施工（P2 新增）═══
      // 交付后回访保养阶段的归档。这是唯一会「同一阶段重复多次」的阶段，
      // 后端用 address_stages.slot 区分第几次上门。
      aftercare: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">售后保养留底</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">AFTER-SALES CARE</p>
            <h1 class="pdf-cover-main-title">售后保养施工归档</h1>
            <p class="pdf-cover-tagline">调试 · 密封 · 清洁 · 复检</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、本次保养概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">本次保养概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
本次售后保养情况：上门原因（定期保养 / 业主报修 / 竣工验收后回访）、保养范围与门窗数量、保养项目、更换配件、业主反馈与本阶段结论。建议 100-200 字。
          </div>
        </section>

        <!-- ═══ 二、上门准备与业主交接 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">二</span>
            <span class="pdf-section-title">上门准备与业主交接</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="arrival-gallery">
            <!-- syncArrivalGallery() 动态渲染：上门预约、工具材料、现场交接、业主沟通等 -->
          </div>
        </section>

        <!-- ═══ 三、保养作业节点 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">三</span>
            <span class="pdf-section-title">保养作业节点</span>
            <span class="pdf-section-line"></span>
          </div>
          <div id="images-container"></div>
          <div class="pdf-grid-2 mt-6">
            <div class="pdf-check-card pdf-check-green">
              <p class="pdf-check-title"><span>🔧</span>五金调试</p>
              <p class="pdf-check-desc">执手、传动器、合页润滑与松紧调整，开合顺畅无异响</p>
            </div>
            <div class="pdf-check-card pdf-check-gold">
              <p class="pdf-check-title"><span>🌧️</span>密封检查</p>
              <p class="pdf-check-desc">胶条老化情况、打胶开裂修补、排水孔疏通</p>
            </div>
            <div class="pdf-check-card pdf-check-neutral">
              <p class="pdf-check-title"><span>🧽</span>清洁保养</p>
              <p class="pdf-check-desc">型材与玻璃表面清洁、轨道除尘、边缝清理</p>
            </div>
            <div class="pdf-check-card pdf-check-green">
              <p class="pdf-check-title"><span>✅</span>功能复检</p>
              <p class="pdf-check-desc">逐扇开合锁闭、密封性复检，与业主当面确认</p>
            </div>
          </div>
        </section>

        <!-- ═══ 四、保养后复检与清洁 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">保养后复检与清洁</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="finish-gallery">
            <!-- syncFinishGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 五、班组离场 SOP ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">五</span>
            <span class="pdf-section-title">班组离场 SOP</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 六、日常保养建议 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">六</span>
            <span class="pdf-section-title">日常保养建议</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
1. 轨道与滑轮每半年清理一次积尘，勿用强酸强碱清洁剂<br>2. 密封胶条每年检查一次，出现硬化开裂及时更换<br>3. 五金件每半年润滑一次，避免暴力开合<br>4. 建议每年预约一次上门保养，延长门窗使用寿命<br>📱 客服微信号：plf32118（售后咨询 · 预约保养）
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「交付不是结束，是长期服务的开始」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `,

      // ═══ 框架 1 对 1 施工（P4 新增）═══
      // 「1 对 1」是师傅口语，指同一户型里一扇一扇地校正框体五金位。
      // 业主端不显示「1 对 1」字样，统一说「单独校正 / 单扇记录」。
      frameOneOnOne: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">单扇校正留证</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">FRAME 1-ON-1</p>
            <h1 class="pdf-cover-main-title">框架单扇校正归档</h1>
            <p class="pdf-cover-tagline">逐洞复核 · 单扇校正 · 调平调直</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、本次单扇校正概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">本次单扇校正概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
本次单扇（门洞）框架校正整体情况：校正部位与洞口编号、框体规格、校正前偏差、校正方法与工具、校正后指标、整体质量把控要点。建议 100-200 字。
          </div>
        </section>

        <!-- ═══ 二…、按框循环区 ═══ -->
        <!-- 一套房子里有多个门洞，每个门洞算一框，各自一组「进场与洞口确认 + 单扇校正节点」。
             段落编号由 renumberSections() 按 DOM 顺序统一算，模板里不写死；
             框内容由 syncFrames() 渲染。 -->
        <div id="frames-container"></div>

        <!-- ═══ 四、校正后固定与成品保护 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">校正后固定与成品保护</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="finish-gallery">
            <!-- syncFinishGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 五、班组离场 SOP ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">五</span>
            <span class="pdf-section-title">班组离场 SOP</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 六、单扇校正注意 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">六</span>
            <span class="pdf-section-title">单扇校正注意</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
1. 每扇独立校正、独立记录，避免批量放样导致相邻扇偏差累积<br>2. 校正完成后在框体标注洞口编号，便于后续玻扇 1 对 1 对应<br>3. 五金位以单扇开合顺畅、锁点咬合到位为准<br>📱 客服微信号：plf32118（售后咨询 · 预约保养）
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「一扇一对，校正到底」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `,

      // ═══ 玻扇 1 对 1 施工（P4 新增）═══
      // 「1 对 1」指每一扇玻扇单独调试、单独记录。与框架 1 对 1 一一对应，
      // 业主端不显示「1 对 1」字样，统一说「单扇调试 / 单扇记录」。
      glassOneOnOne: () => `
        <!-- ═══ 封面 ═══ -->
        <div class="pdf-cover">
          <div class="pdf-cover-band">
            <span class="pdf-cover-brand">CHUJIANG 初匠门窗</span>
            <span class="pdf-cover-badge">单扇调试留证</span>
          </div>
          <div class="pdf-cover-body">
            <p class="pdf-cover-eng">SASH 1-ON-1</p>
            <h1 class="pdf-cover-main-title">玻扇单扇调试归档</h1>
            <p class="pdf-cover-tagline">逐扇入位 · 单扇调缝 · 开合复检</p>
            {{PROJECT_INFO}}
          </div>
        </div>

        <!-- ═══ 一、本次单扇调试概况 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">一</span>
            <span class="pdf-section-title">本次单扇调试概况</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
本次单扇（门洞）玻扇调试整体情况：调试部位与对应洞口编号、玻扇规格、入位与调缝方法、五金调试、开合复检结果、整体质量把控要点。建议 100-200 字。
          </div>
        </section>

        <!-- ═══ 二…、按框循环区 ═══ -->
        <!-- 与框架 1 对 1 同构：每个门洞一框，各自一组「进场与扇位确认 + 单扇调试节点」。
             框内容由 syncFrames() 渲染，编号由 renumberSections() 统一计算。 -->
        <div id="frames-container"></div>

        <!-- ═══ 四、调试后复检与清洁 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">四</span>
            <span class="pdf-section-title">调试后复检与清洁</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="finish-gallery">
            <!-- syncFinishGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 五、班组离场 SOP ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">五</span>
            <span class="pdf-section-title">班组离场 SOP</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-sop-gallery" id="sop-gallery">
            <!-- syncSopGallery() 动态渲染 -->
          </div>
        </section>

        <!-- ═══ 六、日常使用建议 ═══ -->
        <section class="pdf-section">
          <div class="pdf-section-header">
            <span class="pdf-section-num">六</span>
            <span class="pdf-section-title">日常使用建议</span>
            <span class="pdf-section-line"></span>
          </div>
          <div class="pdf-editable-box" contenteditable="true">
1. 每扇独立调试、独立记录，对应框架 1 对 1 的洞口编号便于追溯<br>2. 开合有阻滞及时联系调试，避免暴力操作损伤五金<br>3. 五金件每半年润滑一次，胶条每年检查更换<br>📱 客服微信号：plf32118（售后咨询 · 预约保养）
          </div>
        </section>

        <!-- ═══ 页脚 ═══ -->
        <footer class="pdf-footer">
          <div class="pdf-footer-line-gold"></div>
          <p class="pdf-footer-slogan">「一扇一对，调试到位」</p>
          <p class="pdf-footer-company">汕头市初匠门窗科技有限公司 · CHUJIANG</p>
          <p class="pdf-footer-sub">施格归档 · SITELOG AI 出品 · ICP备2024297744号-2</p>
          <div class="pdf-footer-links">
            <span>服务热线：待填写</span>
            <span>官网：chujiang.中国</span>
            <span>地址：广东省汕头市</span>
          </div>
        </footer>
      `
    };
