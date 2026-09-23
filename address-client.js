// 一址一码：地址实体管理 + 发布时挂接阶段 + 地址二维码卡片。
//
// 与后端 addresses.py 对应。后端是唯一真源，这里只做界面与调用。
//
// 【阶段名必须与后端一致】
// 后端真源是 cj-share/current/stages.py 的 STAGE_KEYS。
// 前端因浏览器无法 import Python，只能保留一份副本；test-stage-parity.cjs 负责守护一致性。
// 改阶段名时，后端 stages.py、这里、index.html 的 <option> 与 TEMPLATES 四处都要改。
window.addressFeatures = {
  // 施工阶段（与 stages.py 同序，顺序即施工顺序，地址页按此排列）
  ADDRESS_STAGE_KEYS: ['吊装施工', '框架施工', '玻扇施工', '五金安装', '离场自检', '售后保养'],
  ADDRESS_STAGE_DISPLAY: {
    '吊装施工': '吊装施工归档',
    '框架施工': '框架归档记录',
    '玻扇施工': '玻扇施工归档',
    '五金安装': '五金安装归档',
    '离场自检': '离场前自检留底',
    '售后保养': '售后保养施工归档'
  },

  // ===== 状态 =====
  addressPanel: false,          // 地址管理面板
  addressItems: [], addressQuery: '', addressPage: 1, addressTotal: 0,
  addressLoading: false,
  addressDetail: null,          // 打开某个地址后的详情（含 stages）
  addressStageGroups: [],       // 详情按施工阶段分组（同阶段的多次留档归到一组，只含已有留档的阶段）
  addressPendingStages: [],     // 还没留档的阶段名，列表下方做一行提示
  addressDoneStages: 0,         // 已留档的**阶段数**（去重；售后来过两次仍算一个阶段）
  addressForm: { label: '', client_name: '', note: '' },
  addressEditingId: '',         // 正在编辑的地址 id；空=新建
  addressFormOpen: false,
  addressBusy: false,
  // 补挂：从已有工程里挑一版挂上来
  addressAttachOpen: false,
  addressAttachQuery: '', addressAttachProjects: [], addressAttachSearching: false,
  addressAttachPid: '', addressAttachProjectTitle: '',
  addressAttachVersions: [], addressAttachPick: '', addressAttachStage: '',
  // 留档方式：auto = 新增一次（后端自动分配槽位，绝不覆盖已有）；replace = 替换已有的第 N 次
  addressAttachSlotMode: 'auto', addressAttachSlot: 0, addressAttachExisting: [],
  // 分享弹窗里的「归属地址」
  addressOptions: [], addressOptionsLoading: false,
  addressPickOn: false, addressPickId: '', addressStage: '', addressAttachNote: '',
  addressPickHint: '',          // 「该地址的这个阶段已有 N 次留档」提示
  addressCardReady: false,

  // ===== 工具 =====
  addressStageLabel(key) { return this.ADDRESS_STAGE_DISPLAY[key] || key; },
  addressStageOrder(key) { const i = this.ADDRESS_STAGE_KEYS.indexOf(key); return i < 0 ? 99 : i; },
  addressStamp(seconds) {
    if (!seconds) return '—';
    const d = new Date(seconds * 1000), p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  },
  // 地址公开页链接。优先用后端给的 url（与 public_base_url 一致），退回同源推导。
  addressUrl(address) {
    if (typeof address === 'string') return location.origin + '/a/' + address;
    return (address && address.url) || (location.origin + '/a/' + (address && address.id));
  },
  // 某个阶段在当前地址下的全部留档，按 slot 递增。
  // slot 0 → 「第 1 次」，slot 1 → 「第 2 次」……业主看到的序号就来自这里。
  addressStageRecords(stageKey) {
    return ((this.addressDetail && this.addressDetail.stages) || [])
      .filter(s => s.stage_key === stageKey)
      .slice()
      .sort((a, b) => a.slot - b.slot);
  },
  // 把详情里的阶段记录按施工阶段分组，供界面按「阶段 → 多次留档」两级展示。
  //
  // 【只保留有留档的阶段】面板回答的是「这个地址上已经挂了什么」。
  // 若把 6 个阶段全列出来，会有 4 个「0 次留档」的空分组带按钮，把真正的内容
  // 挤到屏幕外。还没开始的阶段在列表下方用一行文字提示即可（见 addressPendingStages）。
  buildAddressStageGroups(stages) {
    const groups = [];
    for (const stage of stages || []) {
      let group = groups.find(g => g.key === stage.stage_key);
      // 兜底：后端出现前端清单没覆盖的历史阶段名时，照样建组，绝不在界面上凭空消失。
      if (!group) {
        group = { key: stage.stage_key, label: this.ADDRESS_STAGE_DISPLAY[stage.stage_key] || stage.stage_key, items: [] };
        groups.push(group);
      }
      group.items.push(stage);
    }
    groups.sort((a, b) => this.addressStageOrder(a.key) - this.addressStageOrder(b.key));
    for (const group of groups) group.items.sort((a, b) => a.slot - b.slot);
    return groups;
  },
  // 还没留档的阶段名。放在阶段列表下方做一行提示，让员工知道「还差哪几步」。
  // 写成状态字段而不是在模板里调方法：x-for 里调方法每次渲染都会返回新数组，
  // 白白触发一轮重渲染。
  buildAddressPendingStages(stages) {
    const done = new Set((stages || []).map(s => s.stage_key));
    return this.ADDRESS_STAGE_KEYS.filter(key => !done.has(key));
  },
  // 已留档的**阶段数**，不是留档条数。
  // 售后保养来过两次仍然只算一个阶段——用条数会让「已归档 5 个阶段 / 共 6 个」
  // 这种自相矛盾的文案冒出来（总共只有 6 个阶段，哪来的 5 个？其实是 4 个阶段 5 条留档）。
  addressDoneStageCount(stages) {
    return new Set((stages || []).filter(s => s.visible).map(s => s.stage_key)).size;
  },

  // ===== 列表 =====
  async openAddressPanel() {
    this.addressPanel = true;
    this.addressDetail = null;
    this.addressFormOpen = false;
    await this.loadAddresses();
  },
  async loadAddresses() {
    this.addressLoading = true;
    try {
      const data = await this.accountJSON('/addresses?q=' + encodeURIComponent(this.addressQuery) + '&page=' + this.addressPage);
      this.addressItems = data.items || [];
      this.addressTotal = data.total || 0;
    } catch (e) {
      this.showToast(e.message || '地址列表加载失败', 'error', 8000);
      this.addressItems = [];
    } finally { this.addressLoading = false; }
  },
  addressSearch() { this.addressPage = 1; return this.loadAddresses(); },

  // ===== 新建 / 编辑 =====
  openAddressForm(address) {
    this.addressEditingId = address ? address.id : '';
    this.addressForm = address
      ? { label: address.label || '', client_name: address.client_name || '', note: address.note || '' }
      : { label: '', client_name: '', note: '' };
    this.addressFormOpen = true;
  },
  closeAddressForm() { this.addressFormOpen = false; this.addressEditingId = ''; },
  async saveAddressForm() {
    if (this.addressBusy) return;
    if (!this.addressForm.label.trim()) { this.showToast('请填写地址名称', 'error', 6000); return; }
    this.addressBusy = true;
    try {
      const body = { label: this.addressForm.label, client_name: this.addressForm.client_name, note: this.addressForm.note };
      const saved = this.addressEditingId
        ? await this.accountJSON('/addresses/' + this.addressEditingId, body)
        : await this.accountJSON('/addresses', body);
      this.showToast(this.addressEditingId ? '✅ 地址已更新' : '✅ 地址已创建');
      this.closeAddressForm();
      await this.loadAddresses();
      if (this.addressDetail && this.addressDetail.id === saved.id) await this.openAddress(saved.id);
    } catch (e) { this.showToast(e.message || '保存失败', 'error', 8000); }
    finally { this.addressBusy = false; }
  },

  // ===== 详情 =====
  async openAddress(addressId) {
    try {
      const detail = await this.accountJSON('/addresses/' + addressId);
      detail.stages = (detail.stages || []).slice().sort((a, b) =>
        this.addressStageOrder(a.stage_key) - this.addressStageOrder(b.stage_key) || (a.slot - b.slot));
      this.addressDetail = detail;
      this.addressStageGroups = this.buildAddressStageGroups(detail.stages);
      this.addressPendingStages = this.buildAddressPendingStages(detail.stages);
      this.addressDoneStages = this.addressDoneStageCount(detail.stages);
      this.addressAttachOpen = false;
    } catch (e) { this.showToast(e.message || '地址读取失败', 'error', 8000); }
  },
  closeAddressDetail() {
    this.addressDetail = null;
    this.addressStageGroups = [];
    this.addressPendingStages = [];
    this.addressDoneStages = 0;
    this.addressAttachOpen = false;
    this.addressCardReady = false;
  },
  async refreshAddressDetail() {
    if (!this.addressDetail) return;
    await this.openAddress(this.addressDetail.id);
    await this.loadAddresses();
  },
  async archiveAddress(address) {
    if (!confirm('归档后这个地址的二维码将立即失效，业主扫码看不到档案。已发出的二维码不会被别的地址接管。确定归档？')) return;
    try {
      await this.accountJSON('/addresses/' + address.id + '/archive', {});
      this.showToast('地址已归档');
      if (this.addressDetail && this.addressDetail.id === address.id) this.closeAddressDetail();
      await this.loadAddresses();
    } catch (e) { this.showToast(e.message || '归档失败', 'error', 8000); }
  },
  async restoreAddress(address) {
    try {
      await this.accountJSON('/addresses/' + address.id + '/restore', {});
      this.showToast('地址已恢复');
      await this.loadAddresses();
    } catch (e) { this.showToast(e.message || '恢复失败', 'error', 8000); }
  },

  // ===== 阶段操作 =====
  async detachStage(stage) {
    if (!this.addressDetail) return;
    const times = this.addressStageRecords(stage.stage_key).length > 1
      ? '的第 ' + (stage.slot + 1) + ' 次留档' : '';
    if (!confirm('从地址页移除「' + this.addressStageLabel(stage.stage_key) + '」' + times + '？\n\n只影响地址页展示，/s/' + String(stage.publication_id).slice(0, 8) + '… 这条直链仍然有效。')) return;
    try {
      await this.accountJSON('/addresses/' + this.addressDetail.id + '/detach',
        { stage_key: stage.stage_key, slot: stage.slot });
      this.showToast('已从地址页移除');
      await this.refreshAddressDetail();
    } catch (e) { this.showToast(e.message || '移除失败', 'error', 8000); }
  },
  async toggleStageVisible(stage) {
    if (!this.addressDetail) return;
    try {
      await this.accountJSON('/addresses/' + this.addressDetail.id + '/visible',
        { stage_key: stage.stage_key, slot: stage.slot, visible: !stage.visible });
      await this.refreshAddressDetail();
      const times = this.addressStageRecords(stage.stage_key).length > 1 ? '第 ' + (stage.slot + 1) + ' 次' : '';
      this.showToast(stage.visible ? '已在地址页隐藏该阶段' + times : '已恢复显示' + times);
    } catch (e) { this.showToast(e.message || '操作失败', 'error', 8000); }
  },

  // ===== 补挂：从已有工程里挑一版 =====
  openAddressAttach(stageKey) {
    this.addressAttachOpen = true;
    this.addressAttachQuery = '';
    this.addressAttachProjects = [];
    this.addressAttachPid = '';
    this.addressAttachProjectTitle = '';
    this.addressAttachVersions = [];
    this.addressAttachPick = '';
    this.addressAttachStage = stageKey || this.addressStageDefault();
    this.onAddressAttachStageChange();
  },
  // 换阶段后重算「这个阶段已有几次留档」，并把留档方式复位成「新增一次」。
  // 复位很关键：换阶段后还停在「替换第 3 次」上，是最容易误覆盖的状态。
  onAddressAttachStageChange() {
    this.addressAttachExisting = this.addressStageRecords(this.addressAttachStage);
    this.addressAttachSlotMode = 'auto';
    this.addressAttachSlot = this.addressAttachExisting.length;
  },
  async searchAttachProjects() {
    this.addressAttachSearching = true;
    try {
      const data = await this.accountJSON('/projects?q=' + encodeURIComponent(this.addressAttachQuery) + '&page=1');
      this.addressAttachProjects = data.items || [];
      if (!this.addressAttachProjects.length) this.showToast('没有找到匹配的工程', 'error', 6000);
    } catch (e) { this.showToast(e.message || '工程搜索失败', 'error', 8000); }
    finally { this.addressAttachSearching = false; }
  },
  async pickAttachProject(project) {
    this.addressAttachSearching = true;
    try {
      const detail = await this.accountJSON('/projects/' + project.id);
      this.addressAttachPid = project.id;
      this.addressAttachProjectTitle = project.title || '';
      this.addressAttachProjects = [];
      // 只有「公开」且未撤回的发布版本能挂到地址页；其余直接过滤，避免选了才报错。
      this.addressAttachVersions = (detail.versions || []).filter(v => v.share_id && !v.revoked && v.audience === 'public');
      if (!this.addressAttachVersions.length) this.showToast('该工程还没有「公开」范围的分享码，请先在项目工作区发布一版', 'error', 10000);
      // 默认选中最新一版。必须等 <option> 渲染完再赋值：x-model 的初始赋值早于
      // x-for 插入 <option>，先赋会找不到匹配项而回落显示第一项（=最新版，恰好
      // 看起来对，但换过工程后就会错位），所以显式等一个 tick。
      this.addressAttachPick = '';
      await this.$nextTick();
      if (this.addressAttachVersions.length) this.addressAttachPick = this.addressAttachVersions[0].share_id;
    } catch (e) { this.showToast(e.message || '工程读取失败', 'error', 8000); }
    finally { this.addressAttachSearching = false; }
  },
  async submitAddressAttach() {
    if (!this.addressDetail || !this.addressAttachPick) { this.showToast('请先选择要挂接的分享码', 'error', 6000); return; }
    const label = this.addressStageLabel(this.addressAttachStage);
    // 不传 slot = 后端自动追加一次，绝不覆盖已有留档。
    const body = { stage_key: this.addressAttachStage, publication_id: this.addressAttachPick };
    if (this.addressAttachSlotMode === 'replace') {
      // 覆盖是这套数据里唯一会丢东西的操作，必须让员工明确确认一次再动手。
      const target = this.addressAttachExisting.find(s => s.slot === this.addressAttachSlot);
      if (!target) { this.showToast('要替换的那一次已不存在，请重新选择留档方式', 'error', 8000); return; }
      if (!confirm('「' + label + '」的第 ' + (target.slot + 1) + ' 次留档（' + this.addressStamp(target.created) + '）将被替换，\n原来那一份会从地址页移除。\n\n确定替换？')) return;
      body.slot = target.slot;
    }
    this.addressBusy = true;
    try {
      const result = await this.accountJSON('/addresses/' + this.addressDetail.id + '/attach', body);
      const receipt = (result && result.attached) || null;
      const times = receipt && receipt.count > 1 ? '（第 ' + (receipt.slot + 1) + ' 次留档）' : '';
      this.showToast('✅ 已挂接到「' + label + '」' + times);
      this.addressAttachOpen = false;
      await this.refreshAddressDetail();
    } catch (e) { this.showToast(e.message || '挂接失败', 'error', 8000); }
    finally { this.addressBusy = false; }
  },

  // ===== 分享弹窗里的「归属地址」 =====
  async loadAddressOptions() {
    this.addressOptionsLoading = true;
    try {
      const data = await this.accountJSON('/addresses?q=&page=1');
      this.addressOptions = (data.items || []).filter(a => a.status !== 'archived');
    } catch (e) { this.addressOptions = []; }
    finally { this.addressOptionsLoading = false; }
    // 选项是 x-for 动态渲染的：若 addressPickId 在选项出现前就已有值（重新打开弹窗、
    // 或上次挂接失败后重试），select 会显示成第一项。等一个 tick 再回填一次。
    await this.$nextTick();
    if (this.addressPickId && !this.addressOptions.some(a => a.id === this.addressPickId)) this.addressPickId = '';
  },
  // 阶段默认取当前报告的施工阶段 —— 员工不用再选一次，也避免选错。
  addressStageDefault() {
    return this.ADDRESS_STAGE_KEYS.includes(this.templateType) ? this.templateType : this.ADDRESS_STAGE_KEYS[0];
  },
  resetAddressPick() {
    this.addressPickOn = false;
    this.addressPickId = '';
    this.addressStage = this.addressStageDefault();
    this.addressAttachNote = '';
    this.addressPickHint = '';
  },
  // 告诉员工「这一份会变成第几次留档」。不提示的话，售后第二次上门时
  // 员工会以为自己在覆盖上一次的记录，不敢点；或者反过来以为无所谓而选错阶段。
  async refreshAddressPickHint() {
    this.addressPickHint = '';
    if (!this.addressPickOn || !this.addressPickId) return;
    try {
      const detail = await this.accountJSON('/addresses/' + this.addressPickId);
      const label = this.addressStageLabel(this.addressStage);
      const same = (detail.stages || []).filter(s => s.stage_key === this.addressStage);
      this.addressPickHint = same.length
        ? '该地址的「' + label + '」已有 ' + same.length + ' 次留档，本次会作为第 ' + (same.length + 1) + ' 次保留，旧的不会被覆盖。'
        : '该地址的「' + label + '」还没有留档，本次是第 1 次。';
    } catch (e) { this.addressPickHint = ''; }
  },
  // 发布成功后挂接。挂接失败不能影响「分享码已生成」这个既成事实，所以单独提示。
  async attachAfterPublish() {
    if (!this.addressPickId || !this.shareResult) return;
    try {
      // 不传 slot：后端自动追加一次。第二次售后保养不会覆盖第一次。
      const result = await this.accountJSON('/addresses/' + this.addressPickId + '/attach',
        { stage_key: this.addressStage, publication_id: this.shareResult.id });
      const receipt = (result && result.attached) || null;
      const target = this.addressOptions.find(a => a.id === this.addressPickId);
      const times = receipt && receipt.count > 1
        ? '（该阶段第 ' + (receipt.slot + 1) + ' 次留档）' : '';
      this.addressAttachNote = '✅ 已挂到「' + (target ? target.label : '所选地址') + '」的「' + this.addressStageLabel(this.addressStage) + '」' + times + '。业主扫该地址的二维码即可看到这一份。';
      this.showToast(this.addressAttachNote);
    } catch (e) {
      this.addressAttachNote = '⚠️ 分享码已生成，但挂到地址失败：' + (e.message || '未知原因') + '。可在「地址管理」里补挂。';
      this.showToast(this.addressAttachNote, 'error', 12000);
    }
  },

  // ===== 地址二维码卡片（一址一码，贴门口/交业主） =====
  // 折行 wrapCanvasText() 与圆角矩形 drawRoundRect() 由 index.html 的
  // siteLogApp() 提供（地址卡片与分享卡片共用），这里不要再定义一份：
  // mixin 展开在前、对象字面量在后，后定义的会覆盖前者，重复定义只会变成死代码。
  async drawAddressCard() {
    const canvas = document.getElementById('address-card-canvas');
    const address = this.addressDetail;
    if (!canvas) return;
    if (typeof window.qrcode !== 'function') throw new Error('二维码组件未就绪，请稍后重试');
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
    ctx.fillText('CHUJIANG · 初匠门窗服务中心', W / 2, 92);
    ctx.fillStyle = 'rgba(255,255,255,0.62)';
    ctx.font = '500 20px "PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillText('本户施工归档 · 一码看全程', W / 2, 132);

    ctx.fillStyle = '#ffffff';
    ctx.font = '600 40px "PingFang SC","Microsoft YaHei",sans-serif';
    const titleLines = this.wrapCanvasText(ctx, address.label || '未命名地址', W - 150);
    titleLines.slice(0, 2).forEach((ln, i) => ctx.fillText(ln, W / 2, 196 + i * 52));
    let y = 196 + Math.min(titleLines.length, 2) * 52;

    ctx.fillStyle = '#B8924A'; ctx.fillRect(W / 2 - 40, y + 2, 80, 3);
    y += 46;
    if (address.client_name) {
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.font = '22px "PingFang SC","Microsoft YaHei",sans-serif';
      ctx.fillText('业主：' + address.client_name, W / 2, y);
      y += 34;
    }
    // 同样是「阶段数」口径：卡片是要打印贴门口、交业主的，
    // 写成留档条数会出现「已归档 5 个阶段」而总共只有 6 个阶段的困惑。
    const done = this.addressDoneStageCount(address.stages);
    ctx.fillStyle = 'rgba(255,255,255,0.62)';
    ctx.font = '20px "PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillText('已归档 ' + done + ' 个阶段 · 施工推进中会自动更新', W / 2, y);
    y += 30;

    const qrSize = Math.min(400, H - y - 210), qrX = (W - qrSize) / 2, qrY = y + 14;
    ctx.fillStyle = '#ffffff';
    this.drawRoundRect(ctx, qrX, qrY, qrSize, qrSize, 18); ctx.fill();
    const qr = window.qrcode(0, 'M');
    qr.addData(this.addressUrl(address)); qr.make();
    const n = qr.getModuleCount(), inner = qrSize - 60, cell = inner / n, ox = qrX + 30, oy = qrY + 30;
    ctx.fillStyle = '#1F3D2A';
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        if (qr.isDark(r, c)) ctx.fillRect(ox + c * cell, oy + r * cell, cell + 0.5, cell + 0.5);
      }
    }
    ctx.fillStyle = '#B8924A';
    ctx.font = '500 26px "PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillText('微信扫码 · 查看本户各阶段施工归档', W / 2, qrY + qrSize + 56);
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.font = '20px "PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillText('汕头市初匠门窗科技有限公司', W / 2, H - 96);
    ctx.font = '17px "PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillText('地址编号 ' + address.id + ' · 粤ICP备2024297744号-2', W / 2, H - 62);
  },
  async renderAddressCard() {
    try {
      await this.$nextTick();
      await this.drawAddressCard();
      this.addressCardReady = true;
    } catch (e) { this.addressCardReady = false; this.showToast(e.message || '二维码绘制失败', 'error', 8000); }
  },
  async downloadAddressCard() {
    const canvas = document.getElementById('address-card-canvas');
    if (!canvas || !this.addressDetail) return;
    const name = '施工归档二维码_' + String(this.addressDetail.label || '地址').replace(/[\\/:*?"<>|\s]/g, '') + '.png';
    const link = document.createElement('a');
    link.download = name;
    link.href = canvas.toDataURL('image/png');
    link.click();
  },
  async copyAddressUrl() {
    if (!this.addressDetail) return;
    const text = this.addressUrl(this.addressDetail);
    try { await navigator.clipboard.writeText(text); this.showToast('✅ 地址链接已复制'); }
    catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); this.showToast('✅ 地址链接已复制'); }
      catch (e2) { this.showToast('复制失败，请手动复制：' + text, 'error', 8000); }
      ta.remove();
    }
  }
};
