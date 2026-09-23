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
  ADDRESS_STAGE_KEYS: ['吊装施工', '框架施工', '框架1对1', '玻扇施工', '玻扇1对1', '五金安装', '离场自检', '售后保养'],
  ADDRESS_STAGE_DISPLAY: {
    '吊装施工': '吊装施工归档',
    '框架施工': '框架归档记录',
    '框架1对1': '框架1对1施工归档',
    '玻扇施工': '玻扇施工归档',
    '玻扇1对1': '玻扇1对1施工归档',
    '五金安装': '五金安装归档',
    '离场自检': '离场前自检留底',
    '售后保养': '售后保养施工归档'
  },

  // 需要「洞口/窗位名称」的阶段（1 对 1 类目）。
  // 与后端 stages.LABELED_STAGE_KEYS 同源，由 test-stage-parity.cjs 守护一致性。
  // 「1 对 1」按门洞逐个建档：每一条留档都要带洞口名，业主端用它替代「第 N 次」。
  ADDRESS_LABELED_STAGES: ['框架1对1', '玻扇1对1'],

  // ===== 状态 =====
  addressPanel: false,          // 地址管理面板
  addressItems: [], addressQuery: '', addressPage: 1, addressTotal: 0,
  addressLoading: false,
  addressDetail: null,          // 打开某个地址后的详情（含 stages）
  addressStageGroups: [],       // 详情按施工阶段分组（同阶段的多次留档归到一组，只含已有留档的阶段）
  addressPendingStages: [],     // 还没留档的阶段名，列表下方做一行提示
  addressDoneStages: 0,         // 已留档的**阶段数**（去重；售后来过两次仍算一个阶段）
  // enabled_stages = 该地址要展示给业主的类目（P4-B 选择性展示）。
  // 新建时默认全选，编辑时回填已勾选；未勾选的类目业主扫码看不到。
  addressForm: { label: '', client_name: '', note: '', enabled_stages: [] },
  addressEditingId: '',         // 正在编辑的地址 id；空=新建
  addressFormOpen: false,
  addressBusy: false,
  // 补挂：从已有工程里挑一版挂上来
  addressAttachOpen: false,
  addressAttachQuery: '', addressAttachProjects: [], addressAttachSearching: false,
  addressAttachPid: '', addressAttachProjectTitle: '',
  addressAttachVersions: [], addressAttachPick: '', addressAttachStage: '',
  addressAttachLabel: '',       // 洞口/窗位名称（仅 1 对 1 类目必填）
  // 留档方式：auto = 新增一次（后端自动分配槽位，绝不覆盖已有）；replace = 替换已有的第 N 次
  addressAttachSlotMode: 'auto', addressAttachSlot: 0, addressAttachExisting: [],
  // 分享弹窗里的「归属地址」
  addressOptions: [], addressOptionsLoading: false,
  addressPickOn: false, addressPickId: '', addressStage: '', addressAttachNote: '',
  addressPickLabel: '',         // 洞口/窗位名称（仅 1 对 1 类目必填）
  addressPickHint: '',          // 「该地址的这个阶段已有 N 次留档」提示
  addressCardReady: false,

  // ===== 存量归类（未挂到任何地址的分享码）=====
  //
  // 【为什么需要这个东西】
  // 一址一码是 5.4.4 才上的能力，之前发出去的分享码全都「无主」：
  // 能打开，但不会出现在任何地址页上。存量可能几十上百条，
  // 靠人工翻工程列表找不现实。
  addressOverview: null,        // 地址维度统计总览
  addressOverviewOpen: false,   // 停滞清单是否展开
  addressBulkOpen: false,       // 未归类弹窗
  addressBulkItems: [],         // 候选清单（未归类分享码）
  addressBulkTotal: 0, addressBulkPage: 1,
  addressBulkQuery: '', addressBulkLoading: false,
  addressBulkPicked: {},        // { [publication_id]: true } 勾选状态
  addressBulkStage: {},         // { [publication_id]: stage_key } 每条可单独改目标阶段
  addressBulkLabel: {},         // { [publication_id]: 洞口名 } 1 对 1 类目必填
  addressBulkTarget: '',        // 目标地址 id（必选）
  addressBulkBusy: false,
  addressBulkResult: null,      // 逐条回执，提交后展示

  // ===== 工具 =====
  addressStageLabel(key) { return this.ADDRESS_STAGE_DISPLAY[key] || key; },
  addressStageOrder(key) { const i = this.ADDRESS_STAGE_KEYS.indexOf(key); return i < 0 ? 99 : i; },
  // 该阶段是否必须填洞口/窗位名称（1 对 1 类目）。界面据此显隐输入框、后端据此强制校验。
  addressNeedsLabel(key) { return this.ADDRESS_LABELED_STAGES.includes(key); },
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
  // 若把 8 个阶段全列出来，会有若干「0 次留档」的空分组带按钮，把真正的内容
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
    // 给 1 对 1 类目的每条留档补上「同洞口内的第几次」（unitSeq / unitTotal）。
    //
    // 【为什么不能直接用 slot+1】
    // slot 是**整个类目**内的序号，不是洞口内的序号。一个地址里
    // 「主卧 C1 洞口」占 slot 0/1、「次卧 C2 洞口」占 slot 2，
    // 那么次卧那条会显示成「第 3 次」——而次卧其实只做过一次。
    //
    // 【为什么必须区分】
    // 同一洞口有两条留档时，行标题如果都只写洞口名，
    // 员工看到的是一模一样的两行「主卧 C1 洞口」，
    // 点「移除」或「替换某一次」时根本不知道自己在动哪一次。
    for (const group of groups) {
      const seen = new Map();
      for (const item of group.items) {
        const key = item.label || '';
        if (!key) continue;                    // 非 1 对 1 类目：模板仍按 slot 显示「第 N 次」
        seen.set(key, (seen.get(key) || 0) + 1);
        item.unitSeq = seen.get(key);
      }
      const totals = new Map();
      for (const item of group.items) {
        if (item.label) totals.set(item.label, (totals.get(item.label) || 0) + 1);
      }
      for (const item of group.items) {
        if (item.label) item.unitTotal = totals.get(item.label) || 1;
      }
    }
    return groups;
  },
  // 还没留档的**启用类目**。放在阶段列表下方做一行提示，让员工知道「还差哪几步」。
  // 未勾选的类目不在提示范围内——提示回答的是「这个地址还差哪几步」，
  // 未勾选的步骤本就不该出现在业主页上，列出来只会误导员工。
  // 写成状态字段而不是在模板里调方法：x-for 里调方法每次渲染都会返回新数组，
  // 白白触发一轮重渲染。
  buildAddressPendingStages(stages, enabled) {
    const done = new Set((stages || []).map(s => s.stage_key));
    const scope = (enabled && enabled.length) ? enabled : this.ADDRESS_STAGE_KEYS;
    return scope.filter(key => !done.has(key));
  },
  // 该地址的启用类目数（进度条分母）。老地址没有勾选记录时退回全部类目。
  // 列表项带 enabled_count（后端算好的），详情带 enabled_stages。
  addressEnabledCount(address) {
    if (!address) return this.ADDRESS_STAGE_KEYS.length;
    if (typeof address.enabled_count === 'number' && address.enabled_count > 0) return address.enabled_count;
    if (address.enabled_stages && address.enabled_stages.length) return address.enabled_stages.length;
    return this.ADDRESS_STAGE_KEYS.length;
  },
  // 已留档的**阶段数**，不是留档条数。
  // 售后保养来过两次仍然只算一个阶段——用条数会让「已归档 5 个阶段 / 共 8 个」
  // 这种自相矛盾的文案冒出来（总共只有 8 个阶段，哪来的 5 个？其实是 4 个阶段 5 条留档）。
  addressDoneStageCount(stages) {
    return new Set((stages || []).filter(s => s.visible).map(s => s.stage_key)).size;
  },

  // ===== 列表 =====
  async openAddressPanel() {
    this.addressPanel = true;
    this.addressDetail = null;
    this.addressFormOpen = false;
    this.addressBulkOpen = false;
    // 统计和列表一起拉：两者不同步时，统计条会显示「3 条待归类」而列表里
    // 一条都没有，员工会以为功能坏了。并行请求，一起落库。
    await Promise.all([this.loadAddresses(), this.loadAddressOverview()]);
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

  // ===== 统计总览 =====
  //
  // 【为什么不把数字算在前端】
  // 「已归档几个阶段」必须按**去重后的阶段数**算（售后保养来两次仍算一个阶段）。
  // 这个口径在代码里已经错过四次（地址页进度条、详情头部、二维码卡片、地址列表），
  // 每一次都是「不报错、画面看着也正常」。所以统计一律走后端，前端只负责显示，
  // 不再自己数一遍——少一处能算错的地方。
  async loadAddressOverview() {
    try {
      this.addressOverview = await this.accountJSON('/addresses/overview');
    } catch (e) {
      // 统计失败不该挡住地址管理本身，静默降级：统计条不显示，列表照常可用。
      this.addressOverview = null;
    }
  },
  addressOverviewLine() {
    const data = this.addressOverview;
    if (!data) return '';
    const parts = ['共 ' + data.total + ' 个地址'];
    if (data.complete) parts.push('完工 ' + data.complete);
    if (data.in_progress) parts.push('进行中 ' + data.in_progress);
    if (data.not_started) parts.push('未开始 ' + data.not_started);
    if (data.archived) parts.push('已归档 ' + data.archived);
    return parts.join(' · ');
  },
  // 阶段总数。优先用后端回传的（唯一真源），拿不到时退回前端自己那份清单长度。
  // **不要写死数字**：这个项目已经因为「阶段名/阶段数三处手工同步」出过事，
  // 加一个阶段就要记得改四个地方。退回值有 test-stage-parity.cjs 守护一致性。
  addressStageTotal() {
    return (this.addressOverview && this.addressOverview.stages_total) || this.ADDRESS_STAGE_KEYS.length;
  },
  // 停滞名单的口径必须写在界面上。只显示「落后」而把阈值藏起来，
  // 员工就无从判断这个名单可不可信——14 天是猜的，不是真理。
  addressStallTitle() {
    const data = this.addressOverview;
    if (!data) return '';
    return '这些地址 ' + data.stall_days + ' 天没有更新，阶段也没走完';
  },

  // ===== 存量归类：未挂到任何地址的分享码 =====
  async openAddressBulk() {
    this.addressBulkOpen = true;
    this.addressBulkResult = null;
    this.addressBulkPage = 1;
    this.addressBulkPicked = {};
    this.addressBulkLabel = {};
    // 默认目标是「当前打开的地址」——员工通常正是从这个地址点进来的。
    if (!this.addressBulkTarget && this.addressDetail) this.addressBulkTarget = this.addressDetail.id;
    await this.loadAddressBulk();
  },
  closeAddressBulk() {
    this.addressBulkOpen = false;
    this.addressBulkResult = null;
    this.addressBulkPicked = {};
    this.addressBulkStage = {};
    this.addressBulkLabel = {};
  },
  async loadAddressBulk() {
    this.addressBulkLoading = true;
    try {
      const data = await this.accountJSON('/addresses/unassigned?q=' + encodeURIComponent(this.addressBulkQuery) + '&page=' + this.addressBulkPage);
      this.addressBulkItems = data.items || [];
      this.addressBulkTotal = data.total || 0;
      // 逐条铺默认阶段：用后端从**发布版本快照**取的建议值。
      // 取不到就留空，并让这条不可提交——宁可让人自己选，不可替人猜。
      const next = {};
      const nextLabel = {};
      for (const item of this.addressBulkItems) {
        next[item.publication_id] = this.addressBulkStage[item.publication_id] || item.stage_key || '';
        nextLabel[item.publication_id] = this.addressBulkLabel[item.publication_id] || '';
      }
      this.addressBulkStage = next;
      this.addressBulkLabel = nextLabel;
    } catch (e) {
      this.showToast(e.message || '待归类清单加载失败', 'error', 8000);
      this.addressBulkItems = [];
    } finally { this.addressBulkLoading = false; }
  },
  addressBulkSearch() { this.addressBulkPage = 1; return this.loadAddressBulk(); },
  addressBulkPickedCount() { return this.addressBulkItems.filter(i => this.addressBulkPicked[i.publication_id]).length; },
  // 勾选的前提是这条已经确定了目标阶段。没有阶段还允许勾，
  // 提交时必然 400，员工只会看到「N 条失败」而不知道为什么。
  addressBulkPickable(item) {
    const stage = this.addressBulkStage[item.publication_id] || '';
    if (!stage) return false;
    // 1 对 1 类目还必须填洞口名，否则提交必然逐条失败（后端强制要求）。
    if (this.addressNeedsLabel(stage) && !((this.addressBulkLabel[item.publication_id] || '').trim())) return false;
    return true;
  },
  addressBulkToggleAll(on) {
    const next = Object.assign({}, this.addressBulkPicked);
    for (const item of this.addressBulkItems) {
      if (on && !this.addressBulkPickable(item)) continue;
      next[item.publication_id] = !!on;
    }
    this.addressBulkPicked = next;
  },
  addressBulkAllPicked() {
    const pickable = this.addressBulkItems.filter(i => this.addressBulkPickable(i));
    return pickable.length > 0 && pickable.every(i => this.addressBulkPicked[i.publication_id]);
  },
  addressBulkTargetLabel() {
    const found = this.addressItems.find(a => a.id === this.addressBulkTarget);
    return found ? found.label : '';
  },
  // 提交前的二次确认。**必须把目标地址名念出来**——
  // 批量挂错地址就是把 A 客户的档案挂到 B 客户门口，
  // 而「挂到哪」恰恰是批量操作里最容易选错的一项。
  async submitAddressBulk() {
    if (this.addressBulkBusy) return;
    const picked = this.addressBulkItems.filter(i => this.addressBulkPicked[i.publication_id]);
    if (!picked.length) { this.showToast('请先勾选要归类的分享码', 'error', 6000); return; }
    if (!this.addressBulkTarget) { this.showToast('请先选择要归到哪个地址', 'error', 6000); return; }
    const missing = picked.filter(i => !this.addressBulkPickable(i));
    if (missing.length) {
      this.showToast('有 ' + missing.length + ' 条还没选施工阶段，请先补上', 'error', 8000);
      return;
    }
    const label = this.addressBulkTargetLabel() || this.addressBulkTarget;
    const ok = confirm(
      '把选中的 ' + picked.length + ' 条分享码挂到：\n\n' + label + '\n\n' +
      '每一条都会作为该阶段的「新一次留档」追加，不会覆盖地址上已有的记录。\n\n确定归类？'
    );
    if (!ok) return;
    this.addressBulkBusy = true;
    try {
      const result = await this.accountJSON('/addresses/' + this.addressBulkTarget + '/attach-many', {
        items: picked.map(i => {
          const row = { publication_id: i.publication_id, stage_key: this.addressBulkStage[i.publication_id] };
          // 洞口名只在填了的时候带上。1 对 1 类目必填（addressBulkPickable 已挡住未填的）。
          const hole = (this.addressBulkLabel[i.publication_id] || '').trim();
          if (hole) row.label = hole;
          return row;
        })
      });
      this.addressBulkResult = result;
      // 成功的那些已经挂上去了，从勾选里去掉，避免重复提交。
      const next = Object.assign({}, this.addressBulkPicked);
      for (const item of (result.items || [])) if (item.ok) delete next[item.publication_id];
      this.addressBulkPicked = next;
      if (result.failed) {
        this.showToast('归类完成：成功 ' + result.succeeded + ' 条，失败 ' + result.failed + ' 条（原因见下方清单）', 'error', 12000);
      } else {
        this.showToast('✅ 已归类 ' + result.succeeded + ' 条');
      }
      // 归类会改变统计和列表，一起刷新。
      await Promise.all([this.loadAddressBulk(), this.loadAddresses(), this.loadAddressOverview()]);
      if (this.addressDetail && this.addressDetail.id === result.address_id) await this.openAddress(result.address_id);
    } catch (e) {
      this.showToast(e.message || '归类失败', 'error', 8000);
    } finally { this.addressBulkBusy = false; }
  },

  // ===== 新建 / 编辑 =====
  openAddressForm(address) {
    this.addressEditingId = address ? address.id : '';
    // 全选副本：新建 = 全选（默认展示全部类目）；编辑 = 回填已勾选。
    // 老地址（P4-B 之前建的）后端会把 enabled_stages 当作「全部启用」返回，
    // 所以这里拿到的永远是一个非空列表，不会出现「编辑时全部未勾」的错觉。
    const allKeys = this.ADDRESS_STAGE_KEYS.slice();
    this.addressForm = address
      ? {
          label: address.label || '', client_name: address.client_name || '', note: address.note || '',
          enabled_stages: (address.enabled_stages && address.enabled_stages.length ? address.enabled_stages.slice() : allKeys)
        }
      : { label: '', client_name: '', note: '', enabled_stages: allKeys };
    this.addressFormOpen = true;
  },
  closeAddressForm() { this.addressFormOpen = false; this.addressEditingId = ''; },
  async saveAddressForm() {
    if (this.addressBusy) return;
    if (!this.addressForm.label.trim()) { this.showToast('请填写地址名称', 'error', 6000); return; }
    // 一个类目都不勾 = 业主扫码看到空白页，必是误操作。保存前就挡下来，
    // 别等业主扫码才发现「怎么什么都没有」。
    if (!this.addressForm.enabled_stages.length) { this.showToast('请至少勾选一个要展示给业主的类目', 'error', 6000); return; }
    this.addressBusy = true;
    try {
      const body = {
        label: this.addressForm.label, client_name: this.addressForm.client_name, note: this.addressForm.note,
        enabled_stages: this.addressForm.enabled_stages.slice()
      };
      const saved = this.addressEditingId
        ? await this.accountJSON('/addresses/' + this.addressEditingId, body)
        : await this.accountJSON('/addresses', body);
      this.showToast(this.addressEditingId ? '✅ 地址已更新' : '✅ 地址已创建');
      this.closeAddressForm();
      await Promise.all([this.loadAddresses(), this.loadAddressOverview()]);
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
      this.addressPendingStages = this.buildAddressPendingStages(detail.stages, detail.enabled_stages);
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
    // 详情一变，统计和列表跟着变（阶段数、漂移数、待归类数都受影响）。
    await Promise.all([this.loadAddresses(), this.loadAddressOverview()]);
  },
  async archiveAddress(address) {
    if (!confirm('归档后这个地址的二维码将立即失效，业主扫码看不到档案。已发出的二维码不会被别的地址接管。确定归档？')) return;
    try {
      await this.accountJSON('/addresses/' + address.id + '/archive', {});
      this.showToast('地址已归档');
      if (this.addressDetail && this.addressDetail.id === address.id) this.closeAddressDetail();
      await Promise.all([this.loadAddresses(), this.loadAddressOverview()]);
    } catch (e) { this.showToast(e.message || '归档失败', 'error', 8000); }
  },
  async restoreAddress(address) {
    try {
      await this.accountJSON('/addresses/' + address.id + '/restore', {});
      this.showToast('地址已恢复');
      await Promise.all([this.loadAddresses(), this.loadAddressOverview()]);
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
    this.addressAttachLabel = '';
    this.addressAttachStage = stageKey || this.addressStageDefault();
    this.onAddressAttachStageChange();
  },
  // 换阶段后重算「这个阶段已有几次留档」，并把留档方式复位成「新增一次」。
  // 复位很关键：换阶段后还停在「替换第 3 次」上，是最容易误覆盖的状态。
  // 洞口名一并清空：上一个阶段的洞口名（如「主卧飘窗」）属于另一个类目，留着必错。
  onAddressAttachStageChange() {
    this.addressAttachExisting = this.addressStageRecords(this.addressAttachStage);
    this.addressAttachSlotMode = 'auto';
    this.addressAttachSlot = this.addressAttachExisting.length;
    this.addressAttachLabel = '';
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
    const stageLabel = this.addressStageLabel(this.addressAttachStage);
    // 1 对 1 类目必须填洞口名。后端也会拒，这里先挡一道并给出人话提示。
    const holeLabel = (this.addressAttachLabel || '').trim();
    if (this.addressNeedsLabel(this.addressAttachStage) && !holeLabel) {
      this.showToast('「' + stageLabel + '」需要填写洞口/窗位名称（如「主卧飘窗」），业主靠它区分是哪个洞口', 'error', 8000);
      return;
    }
    // 不传 slot = 后端自动追加一次，绝不覆盖已有留档。
    const body = { stage_key: this.addressAttachStage, publication_id: this.addressAttachPick };
    if (holeLabel) body.label = holeLabel;
    const shown = stageLabel + (holeLabel ? ' · ' + holeLabel : '');
    if (this.addressAttachSlotMode === 'replace') {
      // 覆盖是这套数据里唯一会丢东西的操作，必须让员工明确确认一次再动手。
      const target = this.addressAttachExisting.find(s => s.slot === this.addressAttachSlot);
      if (!target) { this.showToast('要替换的那一次已不存在，请重新选择留档方式', 'error', 8000); return; }
      if (!confirm('「' + shown + '」的第 ' + (target.slot + 1) + ' 次留档（' + this.addressStamp(target.created) + '）将被替换，\n原来那一份会从地址页移除。\n\n确定替换？')) return;
      body.slot = target.slot;
    }
    this.addressBusy = true;
    try {
      const result = await this.accountJSON('/addresses/' + this.addressDetail.id + '/attach', body);
      const receipt = (result && result.attached) || null;
      const times = receipt && receipt.count > 1 ? '（第 ' + (receipt.slot + 1) + ' 次留档）' : '';
      this.showToast('✅ 已挂接到「' + shown + '」' + times);
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
    this.addressPickLabel = '';
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
    const stageLabel = this.addressStageLabel(this.addressStage);
    const holeLabel = (this.addressPickLabel || '').trim();
    // 1 对 1 类目没填洞口名时后端会拒。先在这里提示，别让「分享码已生成」这个
    // 好消息被一个本可避免的挂接失败盖过去。
    if (this.addressNeedsLabel(this.addressStage) && !holeLabel) {
      this.addressAttachNote = '⚠️ 分享码已生成。但「' + stageLabel + '」需要填写洞口/窗位名称才能挂到地址，请到「地址管理」补挂。';
      this.showToast(this.addressAttachNote, 'error', 12000);
      return;
    }
    try {
      // 不传 slot：后端自动追加一次。第二次售后保养不会覆盖第一次。
      const body = { stage_key: this.addressStage, publication_id: this.shareResult.id };
      if (holeLabel) body.label = holeLabel;
      const result = await this.accountJSON('/addresses/' + this.addressPickId + '/attach', body);
      const receipt = (result && result.attached) || null;
      const target = this.addressOptions.find(a => a.id === this.addressPickId);
      const times = receipt && receipt.count > 1
        ? '（该阶段第 ' + (receipt.slot + 1) + ' 次留档）' : '';
      const shown = stageLabel + (holeLabel ? ' · ' + holeLabel : '');
      this.addressAttachNote = '✅ 已挂到「' + (target ? target.label : '所选地址') + '」的「' + shown + '」' + times + '。业主扫该地址的二维码即可看到这一份。';
      this.showToast(this.addressAttachNote);
      // 只在地址面板开着时刷统计：面板没开的时候这些数字没人看，
      // 白发一次请求还多一个失败点（发布流程已经成功了，不该被统计请求影响）。
      if (this.addressPanel) await this.loadAddressOverview();
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
