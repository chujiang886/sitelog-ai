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

  // ===== 客户签认（contract signoff v1，员工侧）=====
  //
  // 【这套东西解决什么】
  // 现场负责人把手机递给业主，业主手写签名确认「这一阶段的档案我看过了」。
  // 业主免登录：后端发一次性令牌，业主扫 /sign/<token> 提交笔迹。
  // 员工侧只做三件事：生成令牌 → 把二维码/链接给业主 → 事后看签认记录、必要时撤回。
  //
  // 【三条不能越界的线（契约 redlines）】
  //   1. 签认链接只用后端返回的 url。前端不拼公开页地址——一旦自己拼，
  //      换域名/换 base_url 时前端生成的链接会指向一个不存在的页面，而二维码已经递出去了。
  //   2. 不在前端算 digest / manifest。签认的法律含义来自服务端冻结的那份清单，
  //      前端算一遍只会得到「和证据不是同一个值」的第二个数字。
  //   3. 409「此阶段已签认」这类后端错误原样透出后端 error 文案，前端不另编话术。
  //      编一套的结果是员工拿着前端文案去问后端，两边说的不是一回事。
  SIGNOFF_REVOKE_NOTE_MIN: 2,   // 契约 REVOKE_NOTE_MIN：撤回原因至少 2 字
  SIGNOFF_REVOKE_NOTE_MAX: 500, // 契约 REVOKE_NOTE_LIMIT
  signoffBusy: false,           // 生成令牌请求进行中（防重复提交）
  signoffPanelOpen: false,      // 签认二维码面板
  signoffKind: '',              // 'stage' | 'final'
  signoffStageKey: '',          // kind=stage 时的阶段名；final 为空串
  signoffSlot: 0,
  signoffLabel: '',             // 签认范围的显示名（念给业主听的那一句）
  signoffToken: '',
  signoffUrl: '',               // 只用后端返回的 url，绝不前端拼
  signoffExpires: 0,            // epoch 秒
  signoffNow: 0,                // 每秒推进的当前时间（秒）；0 = 用真实时间
  signoffTimer: null,           // setInterval 句柄
  signoffQrError: '',           // 二维码绘制失败时仍保留链接（同分享卡片的既有教训）
  signoffItems: [],             // 签认记录（含已撤回）
  signoffLoading: false,
  signoffError: '',
  signoffRevokeId: '',          // 正在填撤回原因的那一条
  signoffRevokeNote: '',
  signoffRevokeBusy: false,

  // ===== 隐蔽工程验收（contract hiddenwork v1，员工侧）=====
  //
  // 【这套东西解决什么】
  // GB 50210-2018 6.1.4 强制三项隐蔽工程验收：预埋件和锚固件 / 隐蔽部位的防腐和填嵌处理 /
  // 高层金属窗防雷连接节点。隐蔽部位**封板之后就拍不到了**，所以每一项有结论就必须有照片——
  // 那是事后争议里唯一的证据。三项必须**全部**有结论才能保存：标准强制三项，缺一项就不算「已验收」。
  //
  // 【三条不能越界的线】
  //   1. 三项的 key / label / hint **一律由后端 H1 返回**，前端不抄第二份。
  //      抄一份的结果是后端改了名、界面还印着旧名字，而员工正拿着它去对标准原文。
  //   2. 会展示给业主的字段（每项说明 `note`、不适用理由 `na_reason`）在界面上必须写明，
  //      员工得知道自己写的东西业主看得到。整单备注 `note` 不公开，也要标明。
  //   3. 409 **不静默重试**。静默重试会把对方刚存的那一版覆盖掉，而两边都以为自己的生效了。
  //
  // 【为什么不做业主签认】
  // 隐蔽工程封板前业主常不在场，硬要签认只会变成现场补签、流于形式。
  // 业主的确认动作统一留到整址竣工（P5 已有一次性令牌签认）。
  HIDDEN_RESULT_LABELS: { pass: '合格', fail: '不合格', na: '不适用' },
  // 三项的 key。**这不是真源**——真源是后端 `hidden_work.ITEMS`（契约 constants.ITEMS）。
  // 它只干一件事：后端返回的项目形状不对时（少一项 / 多项）当场报错，而不是静默渲染半张表、
  // 让员工存下一份「不完整」的记录。一致性由 test-hidden-client.cjs 的 SITELOG_BACKEND 守卫钉住。
  HIDDEN_ITEM_KEYS: ['embedded_parts', 'anti_corrosion', 'lightning_bond'],
  HIDDEN_NA_REASON_MIN: 2,        // 契约 NA_REASON_MIN：「不适用」和「没做」必须能区分
  HIDDEN_NA_REASON_LIMIT: 200,    // 契约 NA_REASON_LIMIT
  HIDDEN_NOTE_LIMIT: 200,         // 契约 NOTE_LIMIT（整单备注与每项说明同上限）
  HIDDEN_PHOTOS_PER_ITEM_MAX: 8,  // 契约 PHOTOS_PER_ITEM_MAX
  // 契约 PHOTO_DATA_URL_CEILING（= media_store.PHOTO_MAX_BYTES 10MB base64 放大 4/3 再留余量）。
  // 超了后端会 413，先拦下来省一次白传。
  HIDDEN_PHOTO_DATA_URL_CEILING: 15029588,

  hiddenLoading: false,
  hiddenError: '',
  hiddenItems: [],          // 后端返回的三项：label/hint/result/na_reason/note/photos 全部来自后端
  hiddenAcceptance: null,   // null = 尚未填写
  hiddenRevision: 0,        // 乐观并发：新建传 0
  hiddenAcceptedAt: '',     // <input type="date"> 的值（'YYYY-MM-DD'，提交时转 epoch 秒）
  hiddenNote: '',           // 整单备注，**不公开**
  hiddenBusy: false,        // 整单保存中（防重复提交）
  hiddenPhotoBusy: '',      // 正在传/删照片的 item_key（同一时刻只允许一张）
  hiddenPreview: '',        // 正在放大查看的照片 mid（照片证据要能放大核对）

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
    this.resetSignoffState();
    // 面板重开时详情已被置空，隐蔽工程状态也要一起清掉：
    // 留着上一户的三项结论和照片 id，重开面板会先闪一屏旧数据。
    this.resetHiddenState();
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
      // 签认记录属于「这个地址」，切地址时必须先清空再拉。
      // 不清空的后果是：A 户的签认记录会短暂显示在 B 户详情里，
      // 而两条记录长得一模一样（都是姓名+手机号+笔迹），肉眼分辨不出来。
      this.resetSignoffState();
      // 隐蔽工程比签认更要紧：这里错的是**照片**。A 户的现场照片出现在 B 户详情里，
      // 员工不会察觉、业主更不会——而照片看起来都像「我家的工地」。
      this.resetHiddenState();
      await Promise.all([this.loadSignoffs(addressId), this.loadHiddenAcceptance(addressId)]);
    } catch (e) { this.showToast(e.message || '地址读取失败', 'error', 8000); }
  },
  closeAddressDetail() {
    this.addressDetail = null;
    this.addressStageGroups = [];
    this.addressPendingStages = [];
    this.addressDoneStages = 0;
    this.addressAttachOpen = false;
    this.addressCardReady = false;
    this.resetSignoffState();
    this.resetHiddenState();
  },
  // 关闭整个地址面板。签认面板与批量归类弹窗是地址面板之上的一层，
  // 关掉下层却留着上层，会在下次打开地址面板时凭空冒出来。
  closeAddressPanel() {
    this.closeSignoffPanel();
    this.cancelSignoffRevoke();
    this.closeAddressBulk();
    this.addressFormOpen = false;
    this.resetHiddenState();
    this.addressPanel = false;
  },
  // Esc 逐层退出：照片放大 → 签认面板 → 批量归类 → 地址表单 → 地址面板。
  escapeAddressPanel() {
    // 照片放大是最内层的一层浮层，先收它，否则 Esc 会连底下整块面板一起关掉。
    if (this.hiddenPreview) { this.closeHiddenPreview(); return; }
    if (this.signoffPanelOpen) { this.closeSignoffPanel(); return; }
    if (this.addressBulkOpen) { this.closeAddressBulk(); return; }
    if (this.addressFormOpen) { this.addressFormOpen = false; return; }
    this.closeAddressPanel();
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
  },

  // ===== 客户签认：入口（生成一次性令牌）=====
  //
  // 契约 A1：POST /api/share/addresses/<aid>/signoff-token
  //   body {kind:'stage'|'final', stage_key, slot}
  //   201 → {ok, token, url, expires, kind, stage_key, slot}
  //   403 无权限 / Origin 或 CSRF 失败；404 地址不存在或阶段未挂接；409 已签认
  //
  // 签认粒度是 (address_id, kind, stage_key, slot)——也就是「某阶段的某一次留档」，
  // 不是「某个阶段」。售后保养来过两次就有两条独立签认，所以入口挂在**每一条留档**上，
  // 而不是阶段分组头上（分组头对应的是 0..N 条留档，指不出 slot）。
  async requestSignoffToken(kind, stageKey, slot) {
    if (this.signoffBusy) return;                       // 防重复提交：连点两下只发一次
    if (!this.addressDetail) { this.showToast('请先打开一个地址', 'error', 6000); return; }
    const isFinal = kind === 'final';
    if (!isFinal && !stageKey) { this.showToast('请先选择要签认的阶段', 'error', 6000); return; }
    this.signoffBusy = true;
    try {
      // final 也把 stage_key/slot 显式带上（契约表里两者有 DEFAULT ''/0，
      // 且规则写明 kind=final 时忽略）。少传字段的风险是后端若按「字段必须存在」
      // 校验就直接 400，而多传两个「会被忽略」的默认值没有任何副作用。
      const body = isFinal
        ? { kind: 'final', stage_key: '', slot: 0 }
        : { kind: 'stage', stage_key: stageKey, slot: Number(slot) || 0 };
      const data = await this.accountJSON('/addresses/' + this.addressDetail.id + '/signoff-token', body);
      this.signoffToken = data.token || '';
      this.signoffUrl = data.url || '';                 // 只用后端的 url
      this.signoffExpires = Number(data.expires) || 0;
      this.signoffKind = data.kind || (isFinal ? 'final' : 'stage');
      this.signoffStageKey = this.signoffKind === 'final' ? '' : (data.stage_key || stageKey || '');
      this.signoffSlot = this.signoffKind === 'final' ? 0 : (data.slot === undefined ? (Number(slot) || 0) : data.slot);
      // 范围文案优先用后端回的 label（后端与业主页同一份显示名），拿不到才本地拼。
      this.signoffLabel = data.label || this.signoffScopeLabel(this.signoffKind, this.signoffStageKey);
      this.signoffQrError = '';
      this.signoffPanelOpen = true;
      this.startSignoffTimer();
      await this.$nextTick?.();
      try { await this.drawSignoffQr(); }
      catch (e) {
        // 二维码画不出来不能把链接一起弄丢——链接是唯一能递给业主的东西，
        // 二维码只是更方便的入口（同分享卡片的既有教训）。
        this.signoffQrError = e.message || '二维码绘制失败，请改用下方链接';
      }
    } catch (e) {
      // 409「此阶段已签认」/ 403 / 404 一律原样透出后端文案，前端不另编话术。
      this.showToast(e.message || '签认链接生成失败', 'error', 8000);
    } finally { this.signoffBusy = false; }
  },
  // 签认范围的显示名。念给业主听的那一句，必须和后端 stage_label 口径一致。
  signoffScopeLabel(kind, stageKey) {
    if (kind === 'final') return '整址竣工验收';
    return this.addressStageLabel(stageKey) || stageKey || '未指定阶段';
  },
  // 关掉二维码面板 = 这一张令牌在界面上作废。链接与过期时间一并清掉：
  // 留着一条已经不在屏幕上的链接，只会让下一个打开面板的人以为它还有效。
  // 注意**不动** signoffItems——签认记录是地址的数据，不是这一张令牌的临时状态。
  closeSignoffPanel() {
    this.stopSignoffTimer();
    this.signoffPanelOpen = false;
    this.signoffQrError = '';
    this.signoffToken = '';
    this.signoffUrl = '';
    this.signoffExpires = 0;
    this.signoffNow = 0;
  },
  // 切地址 / 关详情时把签认相关的状态全部复位，
  // 否则上一户的链接、倒计时、签认记录、撤回输入框会跟着到下一户。
  resetSignoffState() {
    this.closeSignoffPanel();
    this.signoffBusy = false;
    this.signoffKind = '';
    this.signoffStageKey = '';
    this.signoffSlot = 0;
    this.signoffLabel = '';
    this.signoffItems = [];
    this.signoffLoading = false;
    this.signoffError = '';
    this.cancelSignoffRevoke();
    this.signoffRevokeBusy = false;
  },

  // ===== 客户签认：倒计时（契约 TOKEN_TTL_SECONDS = 300）=====
  //
  // 【为什么倒计时做成「由 expires 反推」而不是「本地从 300 往下减」】
  // 本地自减有两处会对不上：员工切后台再回来、手机息屏，定时器会被浏览器降频甚至暂停，
  // 本地减到 120 秒时链接可能早就过期了；反过来手机时间不准也会偏。
  // 唯一可靠的判据是后端给的 expires 绝对时间戳，本地只负责每秒重算一次显示值。
  startSignoffTimer() {
    this.stopSignoffTimer();
    this.signoffNow = Math.floor(Date.now() / 1000);
    if (typeof setInterval === 'function') this.signoffTimer = setInterval(() => this.signoffTick(), 1000);
  },
  stopSignoffTimer() {
    if (this.signoffTimer && typeof clearInterval === 'function') clearInterval(this.signoffTimer);
    this.signoffTimer = null;
  },
  signoffNowAt() { return this.signoffNow || Math.floor(Date.now() / 1000); },
  signoffExpired() { return !this.signoffExpires || this.signoffNowAt() >= this.signoffExpires; },
  signoffRemaining() {
    if (!this.signoffExpires) return 0;
    return Math.max(0, Math.ceil(this.signoffExpires - this.signoffNowAt()));
  },
  signoffCountdownText() {
    const s = this.signoffRemaining(), p = n => String(n).padStart(2, '0');
    return p(Math.floor(s / 60)) + ':' + p(s % 60);
  },
  signoffTick() {
    this.signoffNow = Math.floor(Date.now() / 1000);
    // 到期就停表，但**不自动关面板**：员工需要看到「链接已失效，请重新生成」
    // 并当场点重新生成。自动关掉的话员工只会看到面板消失，以为二维码发出去了。
    if (this.signoffExpired()) this.stopSignoffTimer();
  },

  // ===== 客户签认：二维码 =====
  // 复用本页已有的 window.qrcode（用法同 drawAddressCard），不调任何外部二维码 API。
  async drawSignoffQr() {
    const canvas = document.getElementById('signoff-qr-canvas');
    if (!canvas) return;
    if (typeof window.qrcode !== 'function') throw new Error('二维码组件未就绪，请改用下方链接');
    if (!this.signoffUrl) throw new Error('签认链接为空，请重新生成');
    const W = 560, pad = 40;
    canvas.width = W; canvas.height = W;
    canvas.style.width = '260px'; canvas.style.height = '260px';
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, W);
    const qr = window.qrcode(0, 'M');
    qr.addData(this.signoffUrl); qr.make();
    const n = qr.getModuleCount(), inner = W - pad * 2, cell = inner / n;
    ctx.fillStyle = '#1F3D2A';
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        if (qr.isDark(r, c)) ctx.fillRect(pad + c * cell, pad + r * cell, cell + 0.5, cell + 0.5);
      }
    }
  },
  async copySignoffUrl() {
    const text = this.signoffUrl;
    if (!text) { this.showToast('签认链接为空，请重新生成', 'error', 6000); return; }
    try { await navigator.clipboard.writeText(text); this.showToast('✅ 签认链接已复制'); }
    catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); this.showToast('✅ 签认链接已复制'); }
      catch (e2) { this.showToast('复制失败，请手动复制：' + text, 'error', 8000); }
      ta.remove();
    }
  },

  // ===== 客户签认：记录区（契约 A2）=====
  // GET /api/share/addresses/<aid>/signoffs → {ok, items[]}，按 created 倒序，含已撤回。
  async loadSignoffs(addressId) {
    this.signoffLoading = true;
    this.signoffError = '';
    try {
      const data = await this.accountJSON('/addresses/' + addressId + '/signoffs');
      // 迟到的旧响应不能覆盖新地址的清单（切地址时两个请求会并发）。
      if (!this.addressDetail || this.addressDetail.id !== addressId) return;
      this.signoffItems = data.items || [];
      // 撤回表单指向的那条已经不在清单里时收起表单，
      // 免得留下一个「撤回签认：」后面什么都不写的输入框。
      if (this.signoffRevokeId && !this.signoffItems.some(r => r.id === this.signoffRevokeId)) {
        this.cancelSignoffRevoke();
      }
    } catch (e) {
      if (!this.addressDetail || this.addressDetail.id !== addressId) return;
      this.signoffItems = [];
      this.signoffError = e.message || '签认记录读取失败';
    } finally {
      if (this.addressDetail && this.addressDetail.id === addressId) this.signoffLoading = false;
    }
  },
  // 签认范围：整址竣工验收 / 阶段显示名。
  // **后端 stage_label 优先**——它是唯一真源（整址竣工那一条后端给的是
  // 「整址竣工验收签认」，阶段给的是 stages.display()）。本地显示名只在后端没给时兜底，
  // 否则会出现「列表里叫一个名字、二维码面板里叫另一个名字」。
  signoffRangeLabel(row) {
    if (!row) return '';
    if (row.stage_label) return row.stage_label;
    if (row.kind === 'final') return '整址竣工验收';
    return this.addressStageLabel(row.stage_key) || row.stage_key || '未指定阶段';
  },
  signoffTimeText(seconds) {
    if (!seconds) return '—';
    const d = new Date(seconds * 1000), p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
      + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  },
  // 笔迹图：同源 img，session cookie 自动带上（契约 A3 要求 require_session）。
  signoffStrokeUrl(row) { return '/api/share/signoffs/' + row.id + '/stroke'; },

  // ===== 客户签认：撤回（契约 A4）=====
  // POST /api/share/signoffs/<sid>/revoke body {note}，note 必填 2–500 字。
  // 下限是 2 而不是 1：撤回会作废一份业主已签的凭证，「误」「错」这种一个字
  // 的事后毫无价值，等于没写。前端先按同一下限挡下，别让员工等一个来回。
  openSignoffRevoke(row) {
    this.signoffRevokeId = row.id;
    this.signoffRevokeNote = '';
  },
  // 撤回表单上方那一句「撤回签认：<范围> · <签字人>」。
  // 撤回是不可逆的留痕动作，表单必须写清楚它作用在哪一条上。
  signoffRevokeLabel() {
    const row = (this.signoffItems || []).find(r => r.id === this.signoffRevokeId);
    if (!row) return '';
    return this.signoffRangeLabel(row) + ' · ' + (row.signer_name || '');
  },
  cancelSignoffRevoke() { this.signoffRevokeId = ''; this.signoffRevokeNote = ''; },
  signoffRevokeNoteLength() { return (this.signoffRevokeNote || '').length; },
  async submitSignoffRevoke(row) {
    if (this.signoffRevokeBusy) return;
    const sid = (row && row.id) || this.signoffRevokeId;
    if (!sid) return;
    const note = (this.signoffRevokeNote || '').trim();
    // 撤回原因是这条记录唯一的解释字段。空着提交，日后没人知道为什么撤的。
    // 所以原因不足下限**不发请求**，直接挡下（后端也会 400，但员工不该等一个来回才知道）。
    if (note.length < this.SIGNOFF_REVOKE_NOTE_MIN) {
      this.showToast('请填写撤回原因（' + this.SIGNOFF_REVOKE_NOTE_MIN + '–' + this.SIGNOFF_REVOKE_NOTE_MAX + ' 字）', 'error', 6000);
      return;
    }
    if (note.length > this.SIGNOFF_REVOKE_NOTE_MAX) {
      this.showToast('撤回原因最多 ' + this.SIGNOFF_REVOKE_NOTE_MAX + ' 字，当前 ' + note.length + ' 字', 'error', 6000);
      return;
    }
    this.signoffRevokeBusy = true;
    try {
      await this.accountJSON('/signoffs/' + sid + '/revoke', { note });
      this.showToast('✅ 签认已撤回，可重新发起签认');
      this.cancelSignoffRevoke();
      if (this.addressDetail) await this.loadSignoffs(this.addressDetail.id);
    } catch (e) {
      // 403「非 admin 的撤回者不得是原见证员工」/ 409「已撤回」等，原样透出后端文案。
      this.showToast(e.message || '撤回失败', 'error', 8000);
    } finally { this.signoffRevokeBusy = false; }
  },

  // ===== 隐蔽工程验收：DELETE 通道 =====
  //
  // 【为什么不走 accountJSON】
  // `accountJSON(path, payload)` 只实现了两种调用形态（见 auth-client.js）：
  // 不传 payload = GET，传 payload = POST。契约 H4 删照片是 **DELETE**，
  // 走 accountJSON 只能发出一个 POST —— 而后端 H4 明确判了 `self.command!='DELETE'`
  // 就 405（errata HW-3：不判的话一个 POST 就能删照片）。
  // 所以这里直接用 sessionRequest，它同样会给非 GET 请求带上 X-CSRF-Token
  // （H4 是 require_session(write=True)），与「删除客户 LOGO」是同一范式。
  async accountDelete(path) {
    const response = await this.sessionRequest(path, { method: 'DELETE' });
    let data = {};
    try { data = await response.json(); } catch (e) { data = {}; }
    // 与 accountJSON 同一套错误语义：后端 error 文案原样透出，带上状态码供上层判 409/405。
    if (!response.ok || data.ok === false) {
      const error = new Error(data.error || '操作未完成，请重试');
      error.status = response.status;
      throw error;
    }
    return data;
  },

  // ===== 隐蔽工程验收：日期 =====
  // <input type="date"> 用 'YYYY-MM-DD'，契约 H2 要 epoch 秒。
  // 用**本地时区**换算：员工选「9 月 24 日」，界面上就该是 9 月 24 日。
  // 用 Date.UTC 的话，东八区用户在晚上 8 点后选到的日期会显示成前一天。
  hiddenDateInput(seconds) { return seconds ? this.addressStamp(seconds) : ''; },
  hiddenDateEpoch(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || '').trim());
    if (!m) return 0;
    const at = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).getTime();
    // 2026-02-31 这种 JS 会静默顺延到 3 月 3 日 —— 回写一次比对，对不上就是非法日期。
    if (this.addressStamp(Math.floor(at / 1000)) !== m[0]) return 0;
    return Math.floor(at / 1000);
  },
  hiddenTodayInput() { return this.hiddenDateInput(Math.floor(Date.now() / 1000)); },

  // ===== 隐蔽工程验收：展示口径 =====
  hiddenResultLabel(result) { return this.HIDDEN_RESULT_LABELS[result] || '未填写'; },
  // 面板顶部那一行汇总（团队给的样例：「2 项合格 · 1 项不适用」）。
  // 口径只看当前 items 的结论；一项都没填时明说「尚未填写」，不留空白。
  // 填了一半也要说清楚还差几项——「2 项合格」看不出第三项还没填。
  hiddenSummary() {
    const count = { pass: 0, fail: 0, na: 0 };
    let blank = 0;
    for (const item of this.hiddenItems || []) {
      if (count[item.result] === undefined) blank++;
      else count[item.result]++;
    }
    if (!count.pass && !count.fail && !count.na) return '尚未填写';
    const parts = [];
    if (count.pass) parts.push(count.pass + ' 项合格');
    if (count.fail) parts.push(count.fail + ' 项不合格');
    if (count.na) parts.push(count.na + ' 项不适用');
    if (blank) parts.push(blank + ' 项未填');
    return parts.join(' · ');
  },
  // 汇总行下面那一小行：已保存 → 「验收日期 2026-05-29 · 验收人 王工」；
  // 还没保存 → 交代业主看得到什么（员工得知道这一屏会外发）。
  //
  // 【验收人姓名为什么只在员工侧显示】
  // 契约 public_visibility 写死了：业主可见「三项结论 + 验收时间 + 照片 + 每项说明」，
  // **不含**验收人姓名与用户 id。员工侧是登录态、本来就有该地址权限，显示它是信息不是泄漏。
  hiddenAcceptanceLine() {
    if (!this.hiddenAcceptance) return '保存后业主可在地址页看到三项结论、验收时间与照片';
    const parts = ['验收日期 ' + this.hiddenAcceptedAt];
    if (this.hiddenAcceptance.acceptor_name) parts.push('验收人 ' + this.hiddenAcceptance.acceptor_name);
    return parts.join(' · ');
  },
  // 照片展示走**公开**路由（契约 H5）：单数 `address`，不是 `addresses`。
  // 员工侧也用这一条，不再加一条鉴权路由——同一张图两个入口，迟早有一个
  // 漏掉鉴权校验或漏掉 Cache-Control（契约要求 private, max-age=3600）。
  hiddenPhotoUrl(mid) {
    const aid = this.addressDetail && this.addressDetail.id;
    if (!aid || !mid) return '';
    return '/api/share/address/' + aid + '/hidden-media/' + mid;
  },
  hiddenPhotoCount(item) { return (item && item.photos ? item.photos : []).length; },
  hiddenCanAddPhoto(item) { return this.hiddenPhotoCount(item) < this.HIDDEN_PHOTOS_PER_ITEM_MAX; },
  openHiddenPreview(mid) { this.hiddenPreview = mid || ''; },
  closeHiddenPreview() { this.hiddenPreview = ''; },

  // ===== 隐蔽工程验收：读取（契约 H1）=====
  //
  // GET /api/share/addresses/<aid>/hidden-acceptance
  //   → {ok, items:[{item_key,label,hint,result,na_reason,note,photos:[mid]}], acceptance:null|{...}}
  //
  // 【为什么三项必须由后端给】
  // 三项是 GB 50210-2018 6.1.4 的强制项，名字必须能一一对上标准原文。前端再抄一份的结果是：
  // 后端改了名，界面上还印着旧名字，而员工正拿着它去对标准。所以这里只渲染后端返回的 items。
  async loadHiddenAcceptance(addressId) {
    this.hiddenLoading = true;
    this.hiddenError = '';
    try {
      const data = await this.accountJSON('/addresses/' + addressId + '/hidden-acceptance');
      // 迟到的旧响应不能覆盖新地址（切地址时两个请求会并发）。
      if (!this.addressDetail || this.addressDetail.id !== addressId) return;
      const items = Array.isArray(data.items) ? data.items : [];
      if (items.map((i) => i && i.item_key).sort().join(',') !== this.HIDDEN_ITEM_KEYS.slice().sort().join(',')) {
        // 少一项就渲染少一行，员工会在不知情的情况下存下一份「不完整」的记录。
        // 与其静默渲染半张表，不如当场说清楚（这是形状兜底，不是真源）。
        this.hiddenItems = [];
        this.hiddenError = '隐蔽工程验收项目与标准不符（后端返回 ' + items.length + ' 项），请联系管理员';
        return;
      }
      // 归一化：契约里「未填写」的 result 是 null，但 <select> 的 x-model 拿 null 会
      // 找不到匹配项（`select.value = null` 被强制成字符串 "null"），显示成空白选项。
      // 统一成 '' 后，`<option value="">请选择</option>` 能正常选中，校验里的 `!i.result`
      // 语义也不变。na_reason / note / photos 同理兜底，模板里就不用到处写 `|| ''`。
      this.hiddenItems = items.map((i) => ({
        item_key: i.item_key,
        label: i.label,
        hint: i.hint || '',
        result: i.result || '',
        na_reason: i.na_reason || '',
        note: i.note || '',
        photos: Array.isArray(i.photos) ? i.photos.slice() : [],
      }));
      this.hiddenAcceptance = data.acceptance || null;
      this.hiddenRevision = this.hiddenAcceptance ? (Number(this.hiddenAcceptance.revision) || 0) : 0;
      // 已保存的用记录里的验收日；还没有记录时默认今天——绝大多数验收就是当天填的。
      this.hiddenAcceptedAt = this.hiddenAcceptance && this.hiddenAcceptance.accepted_at
        ? this.hiddenDateInput(this.hiddenAcceptance.accepted_at)
        : this.hiddenTodayInput();
      this.hiddenNote = (this.hiddenAcceptance && this.hiddenAcceptance.note) || '';
    } catch (e) {
      if (!this.addressDetail || this.addressDetail.id !== addressId) return;
      this.hiddenItems = [];
      this.hiddenAcceptance = null;
      this.hiddenError = e.message || '隐蔽工程验收读取失败';
    } finally {
      if (this.addressDetail && this.addressDetail.id === addressId) this.hiddenLoading = false;
    }
  },

  // ===== 隐蔽工程验收：保存前的校验 =====
  //
  // 【为什么前端要再校验一遍】
  // 后端会拒（400），但员工得白等一个来回才知道是哪一项缺照片；而且 H2 的规则是
  // 「三项必须齐全」，在界面上直接指出缺哪一项比让后端回一句笼统的 400 有用得多。
  //
  // 【但这**不是**安全边界】
  // 照片齐全性后端会在**事务内**复查：上传照片与保存是两次请求，中间可能有人把照片删了。
  // 这里只是提前报错，真正说了算的是后端。
  hiddenValidate() {
    const items = this.hiddenItems || [];
    // 项目还没加载出来（形状兜底报错、或刚进详情）时别放行，也别给出
    // 「缺少：（空）」。这一句是兜底，正常情况下 loadHiddenAcceptance 已经拦在前面。
    if (!items.length) return '隐蔽工程验收项目尚未加载，请点「刷新」重试';
    const missing = items.filter((i) => !i.result).map((i) => i.label);
    if (missing.length) return '请填写全部三项验收结论，缺少：' + missing.join('、');
    for (const item of items) {
      if (item.result === 'pass' || item.result === 'fail') {
        // 隐蔽部位封板后拍不到了。没有照片的「已验收」在事后争议里等于没有记录。
        if (!this.hiddenPhotoCount(item)) return '请为「' + item.label + '」至少上传 1 张照片';
      } else if (item.result === 'na') {
        // 「不适用」和「没做」是两件事：理由空着的话，日后没人记得为什么不该做这一项。
        if ((item.na_reason || '').trim().length < this.HIDDEN_NA_REASON_MIN) {
          return '请写明「' + item.label + '」不适用的理由（至少 ' + this.HIDDEN_NA_REASON_MIN + ' 字）';
        }
      }
      if (this.hiddenPhotoCount(item) > this.HIDDEN_PHOTOS_PER_ITEM_MAX) {
        return '「' + item.label + '」最多上传 ' + this.HIDDEN_PHOTOS_PER_ITEM_MAX + ' 张照片';
      }
      if ((item.note || '').length > this.HIDDEN_NOTE_LIMIT) {
        return '「' + item.label + '」说明不能超过 ' + this.HIDDEN_NOTE_LIMIT + ' 字';
      }
      if ((item.na_reason || '').length > this.HIDDEN_NA_REASON_LIMIT) {
        return '「' + item.label + '」不适用理由不能超过 ' + this.HIDDEN_NA_REASON_LIMIT + ' 字';
      }
    }
    if ((this.hiddenNote || '').length > this.HIDDEN_NOTE_LIMIT) {
      return '整单备注不能超过 ' + this.HIDDEN_NOTE_LIMIT + ' 字';
    }
    if (!this.hiddenDateEpoch(this.hiddenAcceptedAt)) return '请选择验收日期';
    return '';
  },
  hiddenPayload() {
    return {
      revision: this.hiddenRevision,
      accepted_at: this.hiddenDateEpoch(this.hiddenAcceptedAt),
      note: (this.hiddenNote || '').trim(),
      items: (this.hiddenItems || []).map((item) => ({
        item_key: item.item_key,
        result: item.result,
        // 结论不是「不适用」时理由必须清空：留着它会生成「合格 + 不适用理由：本户非高层」
        // 这种自相矛盾的记录。后端也会清，但前端留着的话员工在提交前看到的就是那份矛盾状态。
        na_reason: item.result === 'na' ? (item.na_reason || '').trim() : '',
        note: (item.note || '').trim(),
      })),
    };
  },

  // ===== 隐蔽工程验收：整单保存（契约 H2，POST 不是 PUT）=====
  //
  // 【为什么是 POST】
  // 契约 errata HW-1：两个部署入口都没有 PUT（Flask 405 / stdlib 501），
  // 且请求体上限链只实现了一份。为 PUT 再抄一份就是 client-logos 那次
  // 「两处限制必须一起改」的翻版。语义不变，仍是整单保存 + revision 乐观并发。
  async saveHiddenAcceptance() {
    if (this.hiddenBusy) return;                       // 防重复提交：连点两下只发一次
    if (!this.addressDetail) { this.showToast('请先打开一个地址', 'error', 6000); return; }
    const problem = this.hiddenValidate();
    if (problem) { this.showToast(problem, 'error', 8000); return; }
    this.hiddenBusy = true;
    const aid = this.addressDetail.id;
    try {
      const data = await this.accountJSON('/addresses/' + aid + '/hidden-acceptance', this.hiddenPayload());
      this.hiddenRevision = Number(data.revision) || this.hiddenRevision;
      this.showToast('✅ 隐蔽工程验收已保存');
      await this.loadHiddenAcceptance(aid);
    } catch (e) {
      if (e.status === 409) {
        // 【不静默重试】静默重试会把对方刚存的那一版用我这一份覆盖掉，
        // 而两边都以为自己的版本生效了。刷新 + 明确告知，让员工自己核对。
        await this.loadHiddenAcceptance(aid);
        this.showToast('记录已被其他设备更新，已刷新，请核对后重新保存', 'error', 9000);
      } else {
        this.showToast(e.message || '隐蔽工程验收保存失败', 'error', 8000);
      }
    } finally { this.hiddenBusy = false; }
  },

  // ===== 隐蔽工程验收：照片（契约 H3 上传 / H4 删除 / H5 展示）=====
  //
  // 【为什么上传前要压】
  // 契约 PHOTO_MAX_BYTES 是 10MB，而 base64 会放大 4/3。现场手机原图动辄 4–8MB，
  // 先压到长边 1280 / JPEG 0.78（沿用本页既有的 compressDataUrl）后通常只有几百 KB：
  // 员工少等、后端少存。后端还会再规范化一次（剥 EXIF/GPS、缩到 1920、重编码 JPEG），
  // 那是**证据链**要求（隐蔽工程照片常带定位信息，不能原样外发），不是重复劳动。
  async uploadHiddenPhoto(item, file) {
    if (!file || !item) return;
    if (this.hiddenPhotoBusy) return;                  // 同一时刻只允许一张，避免交错覆盖
    if (!this.addressDetail) { this.showToast('请先打开一个地址', 'error', 6000); return; }
    if (!this.hiddenCanAddPhoto(item)) {
      this.showToast('「' + item.label + '」最多上传 ' + this.HIDDEN_PHOTOS_PER_ITEM_MAX + ' 张照片', 'error', 6000);
      return;
    }
    this.hiddenPhotoBusy = item.item_key;
    const aid = this.addressDetail.id;
    try {
      const dataUrl = await this.compressDataUrl(await this.fileToDataUrl(file));
      if (!/^data:image\/(png|jpeg|webp);base64,/.test(String(dataUrl || ''))) {
        throw new Error('这个文件不是支持的图片格式（PNG / JPG / WebP）');
      }
      if (dataUrl.length > this.HIDDEN_PHOTO_DATA_URL_CEILING) {
        throw new Error('这张照片太大，请换一张或先压缩后再上传');
      }
      const data = await this.accountJSON('/addresses/' + aid + '/hidden-media', {
        item_key: item.item_key, dataUrl, filename: (file.name || ''),
      });
      if (this.addressDetail && this.addressDetail.id === aid) {
        // 只把新 id 追加到本地列表，不重新拉整单：上传与保存是两条路径，
        // 重新拉会把员工正在填的结论/说明一起覆盖掉。
        if (!item.photos) item.photos = [];
        if (data.id && !item.photos.includes(data.id)) item.photos.push(data.id);
      }
      this.showToast(data.duplicate ? '这张照片已经传过了，不用重复上传' : '✅ 照片已上传');
    } catch (e) {
      this.showToast(e.message || '照片上传失败', 'error', 8000);
    } finally { this.hiddenPhotoBusy = ''; }
  },
  async removeHiddenPhoto(item, mid) {
    if (!item || !mid) return;
    if (this.hiddenPhotoBusy) return;
    if (!this.addressDetail) return;
    this.hiddenPhotoBusy = item.item_key;
    const aid = this.addressDetail.id;
    try {
      await this.accountDelete('/addresses/' + aid + '/hidden-media/' + mid);
      if (this.addressDetail && this.addressDetail.id === aid && item.photos) {
        item.photos = item.photos.filter((x) => x !== mid);
      }
      if (this.hiddenPreview === mid) this.hiddenPreview = '';
      this.showToast('照片已删除');
    } catch (e) {
      this.showToast(e.message || '照片删除失败', 'error', 8000);
    } finally { this.hiddenPhotoBusy = ''; }
  },

  // 切地址 / 关详情时把隐蔽工程状态全部复位。
  //
  // 【为什么比签认那边更要紧】
  // 签认记录错了是几行文字；隐蔽工程错了是**照片**，而照片比文字更容易让人
  // 以为「这是我家」。A 户的照片出现在 B 户详情里，员工不会察觉，业主更不会。
  resetHiddenState() {
    this.hiddenLoading = false;
    this.hiddenError = '';
    this.hiddenItems = [];
    this.hiddenAcceptance = null;
    this.hiddenRevision = 0;
    this.hiddenAcceptedAt = '';
    this.hiddenNote = '';
    this.hiddenBusy = false;
    this.hiddenPhotoBusy = '';
    this.hiddenPreview = '';
  }
};
