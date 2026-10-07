// 为仍打开 v5.0.0 的员工页面更新 AI 方法，保留 Alpine 数据和人工编辑 DOM。
(async () => {
  try {
    const app = window.Alpine && window.Alpine.$data(document.body);
    if (!app || typeof app.aiOrganizeAll !== 'function') throw Error('请回到原有工程归档页面，再点击此书签。');
    if (app.processing || app.aiChecking) throw Error('正在整理照片，请等待本次整理结束再恢复。');
    const get = async path => {
      const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) throw Error('更新文件暂时无法读取，请稍后重试。');
      return response.text();
    };
    // ⚠️ 2026-10-05 起 index.html 的内联 CSS/JS 已外置（P2 拆分）：siteLogApp() 现在
    // 定义在 app-main.js，且依赖 templates.js / ai-style.js 的顶层常量（加载顺序与
    // index.html 里一致）。**不能再从 index.html 的最后一个内联脚本里取** —— 那里
    // 现在只剩一段 97 字节的 GitHub Pages 跳转，取到的 siteLogApp 必然未定义，
    // 表现为 alert「siteLogApp is not defined」而 AI 永远恢复不了（2026-10-07 修）。
    const [auth, aiStyle, templates, appMain] = await Promise.all([
      get('/sitelog/auth-client.js'),
      get('/sitelog/ai-style.js'),
      get('/sitelog/templates.js'),
      get('/sitelog/app-main.js'),
    ]);
    const features = new Function('window', auth + '\nreturn window.accountFeatures;')({});
    // 传「以真实 window 为原型」的 scope：siteLogApp() 会展开 window.editorFeatures /
    // projectFeatures / addressFeatures 等，这些在**旧页面上本来就存在**（旧页面同样
    // 加载了那些 client 脚本）；只有 accountFeatures 需要用刚拉到的新版覆盖掉。
    const scope = Object.create(window);
    scope.accountFeatures = features;
    const updated = new Function('window', aiStyle + '\n' + templates + '\n' + appMain + '\nreturn siteLogApp();')(scope);
    const methods = ['applySession', 'refreshCompanyStatus', 'ensureCompanyAI', 'aiOrganizeAll', 'reAnalyze', 'analyzeImage', 'callVisionAPI', 'openSettings'];
    for (const name of methods) if (typeof updated[name] !== 'function') throw Error('更新文件不完整，当前工程未更改。');
    for (const name of methods) app[name] = updated[name];
    app.aiChecking = false;
    if (!await app.refreshCompanyStatus()) return;
    app.showSettings = false;
    app.showToast(app.aiConfigured ? 'AI 已恢复，照片和审核文字均已保留，请点击 AI 一键整理。' : '页面已更新，正在等待公司 AI 配置。');
  } catch (error) { alert(error.message || '恢复未完成，请保留当前工程页面。'); }
})();
