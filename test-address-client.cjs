#!/usr/bin/env node
/*
 * address-client.js 纯逻辑单元测试。
 *
 * 【为什么单独测这几个函数】
 * `buildAddressStageGroups` / `buildAddressPendingStages` / `addressDoneStageCount`
 * 都是「算错了不会报错、只是界面文案自相矛盾」的地方：
 *
 *   「已归档 5 个阶段」而总共只有 6 个阶段、其中 4 个有档 —— 看着也像对的，
 *   但员工会以为自己数错了，业主更不可能发现。
 *
 * 这类问题截图看不出来（截图里 5 和 4 都像正常数字），只能靠断言钉住。
 * 三个函数都是纯函数，直接抽出来跑，不用启浏览器。
 *
 * 用法：node test-address-client.cjs
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SOURCE = path.join(__dirname, "address-client.js");
if (!fs.existsSync(SOURCE)) {
  console.error(`找不到 ${SOURCE}\n请在本文件所在目录运行（cj-sitelog-web/current）。`);
  process.exit(2);
}

const sandbox = { window: {}, location: { origin: "http://example.test" }, console };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SOURCE, "utf8"), sandbox, { filename: "address-client.js" });
const F = sandbox.window.addressFeatures;

if (!F || typeof F.buildAddressStageGroups !== "function") {
  console.error("address-client.js 没有正确挂载 window.addressFeatures");
  process.exit(2);
}

// ---------- 断言 ----------

let passed = 0;
const failures = [];
function check(name, condition, detail) {
  if (condition) passed++;
  else failures.push(`${name}${detail ? " —— " + detail : ""}`);
}
function same(actual, expected) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

const at = (day) => new Date(2026, 5, day, 10, 0, 0).getTime() / 1000;
const rec = (stage_key, slot, visible = true) => ({
  stage_key, slot, visible, created: at(slot + 1), publication_id: "f".repeat(32),
});

// 种子：4 个阶段有档（售后两次），其余未开始。
const STAGES = [
  rec("玻扇施工", 0), rec("吊装施工", 0), rec("售后保养", 1),
  rec("框架施工", 0), rec("售后保养", 0),
];

// ---------- buildAddressStageGroups ----------

{
  const groups = F.buildAddressStageGroups(STAGES);
  check("只列出有留档的阶段（未开始的不占列表）", groups.length === 4, `实际 ${groups.length}`);
  check("分组按施工顺序排列，不是按发布时间",
    same(groups.map((g) => g.key), ["吊装施工", "框架施工", "玻扇施工", "售后保养"]),
    JSON.stringify(groups.map((g) => g.key)));
  check("分组标题用业主可见的显示名",
    same(groups.map((g) => g.label), ["吊装施工归档", "框架归档记录", "玻扇施工归档", "售后保养施工归档"]),
    JSON.stringify(groups.map((g) => g.label)));
  const aftercare = groups.find((g) => g.key === "售后保养");
  check("同阶段的多次留档归到同一组", aftercare.items.length === 2, `实际 ${aftercare.items.length}`);
  check("组内按 slot 递增（第 1 次在前）",
    same(aftercare.items.map((i) => i.slot), [0, 1]),
    JSON.stringify(aftercare.items.map((i) => i.slot)));
}

{
  const groups = F.buildAddressStageGroups([]);
  check("没有留档时返回空数组（不返回 6 个空分组）", groups.length === 0, `实际 ${groups.length}`);
}

{
  // 兜底：后端出现前端清单没覆盖的历史阶段名，不能在界面上凭空消失。
  const groups = F.buildAddressStageGroups([rec("旧版阶段名", 0), rec("框架施工", 0)]);
  check("未知阶段名照样建组，不会被静默丢弃",
    groups.some((g) => g.key === "旧版阶段名"), JSON.stringify(groups.map((g) => g.key)));
  check("未知阶段排在已知阶段之后",
    groups[groups.length - 1].key === "旧版阶段名", JSON.stringify(groups.map((g) => g.key)));
}

// ---------- buildAddressPendingStages ----------

{
  const pending = F.buildAddressPendingStages(STAGES);
  check("未留档阶段与 STAGE_KEYS 同序",
    same(pending, ["框架1对1", "玻扇1对1", "五金安装", "离场自检"]), JSON.stringify(pending));
  check("同一阶段来过两次也只从待办里去掉一次",
    pending.filter((k) => k === "售后保养").length === 0, JSON.stringify(pending));
  check("全部阶段都有档时待办为空",
    F.buildAddressPendingStages(F.ADDRESS_STAGE_KEYS.map((k) => rec(k, 0))).length === 0);
}

// ---------- addressDoneStageCount（本文件存在的理由）----------

{
  check("进度按阶段数算，不是留档条数（5 条留档 → 4 个阶段）",
    F.addressDoneStageCount(STAGES) === 4, `实际 ${F.addressDoneStageCount(STAGES)}`);
  check("售后保养两条留档只算一个阶段",
    F.addressDoneStageCount([rec("售后保养", 0), rec("售后保养", 1)]) === 1,
    `实际 ${F.addressDoneStageCount([rec("售后保养", 0), rec("售后保养", 1)])}`);
  check("已隐藏的阶段不计入进度",
    F.addressDoneStageCount([rec("框架施工", 0), rec("玻扇施工", 0, false)]) === 1);
  check("没有留档时为 0", F.addressDoneStageCount([]) === 0);
  check("阶段数不会超过阶段总数",
    F.addressDoneStageCount(STAGES) <= F.ADDRESS_STAGE_KEYS.length);
}

// ---------- addressStageRecords ----------

{
  const client = Object.create(F);
  client.addressDetail = { stages: STAGES };
  check("按阶段取留档，按 slot 递增",
    same(client.addressStageRecords("售后保养").map((s) => s.slot), [0, 1]));
  check("没有该阶段时返回空数组", client.addressStageRecords("五金安装").length === 0);
  check("addressDetail 为空时不报错", (() => {
    const empty = Object.create(F);
    empty.addressDetail = null;
    return empty.addressStageRecords("框架施工").length === 0;
  })());
}

// ---------- 阶段常量 ----------

{
  check("前端阶段清单是 8 个", F.ADDRESS_STAGE_KEYS.length === 8, `实际 ${F.ADDRESS_STAGE_KEYS.length}`);
  check("每个阶段都有显示名",
    F.ADDRESS_STAGE_KEYS.every((k) => typeof F.ADDRESS_STAGE_DISPLAY[k] === "string"));
}

// ---------- 结构守卫：别再退回「按留档条数算阶段数」 ----------

{
  const htmlPath = path.join(__dirname, "index.html");
  const html = fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, "utf8") : "";
  const source = fs.readFileSync(SOURCE, "utf8");

  check("index.html 已改用 addressDoneStages 展示已归档阶段数",
    html.includes("addressDoneStages"), "没找到预期的绑定");
  check("index.html 里没有残留「按可见留档条数当阶段数」的写法",
    !/filter\(\s*s\s*=>\s*s\.visible\s*\)\.length\s*\+\s*['"] 个阶段/.test(html));
  check("address-client.js 的二维码卡片不再按留档条数算阶段数",
    !/const done\s*=\s*\(address\.stages\s*\|\|\s*\[\]\)\.filter/.test(source));
  check("address-client.js 的二维码卡片改用 addressDoneStageCount",
    /addressDoneStageCount\(address\.stages\)/.test(source));
}

// ---------- 存量归类：候选清单的勾选规则 ----------
//
// 【为什么这些也要测】
// 批量归类一次会往一个地址页上挂 N 份档案。这里每一个判断错了，
// 后果都不是「界面难看」，而是「挂错地址」或「提交了必然失败的批次」：
//   - 允许勾选没选阶段的条目 → 提交时后端逐条 400，员工只看到「N 条失败」
//   - 目标地址没选就能提交 → 后端 404/403，同样说不清
//   - 「全选」把不可提交的条目也勾上 → 员工以为全好了，实际有一半没归位

const bulkItem = (sid, stage_key, title) => ({
  publication_id: sid, stage_key, stage_label: stage_key ? stage_key + "归档" : "",
  project_title: title || "某工程", version_number: 1, published_at: at(1),
  expires: null, site_location: "", project_name: "",
});

{
  const client = Object.create(F);
  client.addressBulkStage = { a: "框架施工", b: "" };
  check("有阶段的条目才允许勾选",
    client.addressBulkPickable(bulkItem("a", "框架施工")) === true);
  check("没选阶段的条目不允许勾选（勾了提交必然 400）",
    client.addressBulkPickable(bulkItem("b", "")) === false);

  client.addressBulkItems = [bulkItem("a", "框架施工"), bulkItem("b", ""), bulkItem("c", "售后保养")];
  client.addressBulkStage = { a: "框架施工", b: "", c: "售后保养" };
  client.addressBulkPicked = {};

  client.addressBulkToggleAll(true);
  check("全选只勾可提交的条目，跳过没选阶段的",
    same(Object.keys(client.addressBulkPicked).filter((k) => client.addressBulkPicked[k]), ["a", "c"]),
    JSON.stringify(client.addressBulkPicked));
  check("全选后 addressBulkPickedCount 只数勾上的",
    client.addressBulkPickedCount() === 2, `实际 ${client.addressBulkPickedCount()}`);
  check("有不可提交条目时 addressBulkAllPicked 仍为真（它们本来就不该被勾）",
    client.addressBulkAllPicked() === true);

  client.addressBulkToggleAll(false);
  check("取消全选清空所有勾选", client.addressBulkPickedCount() === 0);

  // 一条可勾的都没有时，「全选」不能显示成已全选，否则按钮文案会自相矛盾。
  const stuck = Object.create(F);
  stuck.addressBulkItems = [bulkItem("x", "")];
  stuck.addressBulkStage = { x: "" };
  stuck.addressBulkPicked = {};
  check("没有任何可勾条目时 addressBulkAllPicked 为假", stuck.addressBulkAllPicked() === false);

  // 目标地址名要能念出来——二次确认框里必须出现它。
  const named = Object.create(F);
  named.addressItems = [{ id: "addr1", label: "观海花园 3 栋 2201" }];
  named.addressBulkTarget = "addr1";
  check("能取到目标地址名（二次确认要念出来）",
    named.addressBulkTargetLabel() === "观海花园 3 栋 2201");
  named.addressBulkTarget = "";
  check("未选目标地址时返回空串", named.addressBulkTargetLabel() === "");
}

// ---------- 统计总览的展示口径 ----------

{
  const client = Object.create(F);
  client.addressOverview = {
    total: 12, active: 12, archived: 0, not_started: 5, in_progress: 6, complete: 1,
    drifted: 0, records_total: 30, stages_total: 6, stall_days: 14, unassigned: 3, stalled: [],
  };
  const line = client.addressOverviewLine();
  check("总览一句话包含地址总数", line.includes("共 12 个地址"), line);
  check("总览一句话包含完工/进行中/未开始", /完工 1/.test(line) && /进行中 6/.test(line) && /未开始 5/.test(line), line);
  check("归档数为 0 时不显示「已归档 0」",
    !line.includes("已归档 0"), line);

  check("阶段总数优先用后端回传值", client.addressStageTotal() === 6);
  const fallback = Object.create(F);
  fallback.addressOverview = null;
  check("统计拿不到时退回前端阶段清单长度，而不是写死数字",
    fallback.addressStageTotal() === fallback.ADDRESS_STAGE_KEYS.length);

  // 停滞口径必须写在界面上。只显示「落后」而把阈值藏起来，
  // 员工就无从判断这个名单可不可信。
  check("停滞名单标题里写明「N 天没有更新」",
    client.addressStallTitle().includes("14 天没有更新"), client.addressStallTitle());
  const noData = Object.create(F);
  noData.addressOverview = null;
  check("统计拿不到时总览文案为空串（不抛错）", noData.addressOverviewLine() === "");
  check("统计拿不到时停滞标题为空串（不抛错）", noData.addressStallTitle() === "");
}

// ---------- 结构守卫：存量归类 ----------

{
  const htmlPath = path.join(__dirname, "index.html");
  const html = fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, "utf8") : "";
  const source = fs.readFileSync(SOURCE, "utf8");

  // 批量挂错地址 = 把 A 客户的档案挂到 B 客户门口。
  // 所以提交前必须 confirm，且确认文案里必须出现目标地址名。
  check("批量归类提交前有二次确认",
    /submitAddressBulk\(\)[\s\S]{0,2200}?confirm\(/.test(source), "submitAddressBulk 里没找到 confirm");
  check("二次确认文案里念出目标地址名",
    /submitAddressBulk\(\)[\s\S]{0,2200}?addressBulkTargetLabel\(\)/.test(source),
    "确认框里没念地址名——这正是批量操作最容易选错的一项");
  check("二次确认文案里说明「不会覆盖已有记录」",
    /submitAddressBulk\(\)[\s\S]{0,2600}?不会覆盖/.test(source));

  // 批量入口只发 publication_id + stage_key。带上 slot 就等于给了一个
  // 「批量覆盖」的后门——批量场景没人会逐条核对会覆盖哪一次。
  check("批量入口不向后端发送 slot",
    /attach-many[\s\S]{0,400}?publication_id[\s\S]{0,200}?stage_key/.test(source) &&
    !/attach-many[\s\S]{0,400}?slot:/.test(source),
    "attach-many 的请求体里出现了 slot");

  check("index.html 有未归类入口（按后端回传的 unassigned 数显示）",
    html.includes("addressOverview.unassigned"), "没找到 unassigned 的绑定");
  check("index.html 展示「已挂接但业主看不到」的漂移提醒",
    html.includes("addressOverview.drifted"));
  check("index.html 的地址列表不再用「N 个阶段已归档」这种会算错的文案",
    !html.includes("a.stage_count + ' 个阶段已归档"),
    "旧文案会显示「5 个阶段已归档」而总共只有 6 个阶段");
  check("地址列表用 addressEnabledCount(a) 取该地址的类目数当分母，不写死数字",
    html.includes("addressEnabledCount(a)") && !/\/\s*6\s*\+\s*' 个阶段/.test(html));
  check("逐条回执遍历的是后端返回的 items 字段",
    /x-for="[^"]*in\s+addressBulkResult\.items"/.test(html),
    "回执循环没读 addressBulkResult.items——字段名改了会渲染出空列表且不报错");
  check("逐条回执渲染了失败原因（不能只显示「N 条失败」）",
    /addressBulkResult\.items[\s\S]{0,600}?row\.error/.test(html),
    "失败原因没渲染出来，员工不知道哪条要重做");
}

// ---------- P4-B：展示类目（后台选择性展示） ----------
//
// 【为什么这些也要测】
// 「未勾选的类目业主看不到」这条红线一旦破，就是把公司不想给业主看的阶段
// 悄悄放了出去；而分母算错（用系统总类目数当某地址的分母）会让业主
// 以为「还有 6 步没做」。两者都不会报错，只能靠断言钉住。

{
  // 待办提示只该覆盖**启用**的类目。未勾选的步骤本就不该出现在业主页上。
  const pending = F.buildAddressPendingStages(STAGES, ["吊装施工", "框架施工", "框架1对1"]);
  check("待办只列启用类目里的未留档项",
    same(pending, ["框架1对1"]), JSON.stringify(pending));
  check("启用类目都已留档 → 待办为空",
    F.buildAddressPendingStages(STAGES, ["吊装施工", "框架施工"]).length === 0);
  check("不传启用清单时退回全部类目（老地址）",
    F.buildAddressPendingStages(STAGES).length === F.ADDRESS_STAGE_KEYS.length - 4);

  // addressEnabledCount：优先列表项 enabled_count，其次详情 enabled_stages，最后全类目。
  check("列表项用 enabled_count 当分母", F.addressEnabledCount({ enabled_count: 3 }) === 3);
  check("详情用 enabled_stages 长度当分母",
    F.addressEnabledCount({ enabled_stages: ["框架施工", "玻扇施工"] }) === 2);
  check("老地址（无勾选记录）退回全部类目",
    F.addressEnabledCount({}) === F.ADDRESS_STAGE_KEYS.length);
  check("传 null 不报错", F.addressEnabledCount(null) === F.ADDRESS_STAGE_KEYS.length);
  check("enabled_count 为 0（存量地址）时不用 0 当分母",
    F.addressEnabledCount({ enabled_count: 0 }) === F.ADDRESS_STAGE_KEYS.length);
}

{
  // 表单：新建默认全选，编辑回填已勾选，老地址编辑时不被误清空。
  const client = Object.create(F);
  client.openAddressForm(null);
  check("新建地址默认全选类目",
    same(client.addressForm.enabled_stages, F.ADDRESS_STAGE_KEYS),
    JSON.stringify(client.addressForm.enabled_stages));

  client.openAddressForm({ id: "a1", label: "某地址", enabled_stages: ["框架施工", "玻扇施工"] });
  check("编辑地址回填已勾选类目",
    same(client.addressForm.enabled_stages, ["框架施工", "玻扇施工"]),
    JSON.stringify(client.addressForm.enabled_stages));

  client.openAddressForm({ id: "a2", label: "老地址" });
  check("老地址编辑时默认全选（不会被误清空）",
    same(client.addressForm.enabled_stages, F.ADDRESS_STAGE_KEYS));
}

{
  const htmlPath = path.join(__dirname, "index.html");
  const html = fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, "utf8") : "";
  const source = fs.readFileSync(SOURCE, "utf8");

  check("保存地址时把展示类目一起提交",
    /saveAddressForm[\s\S]{0,1200}?enabled_stages/.test(source), "saveAddressForm 没提交 enabled_stages");
  check("一个类目都不勾时保存被挡下（不给业主看空白页）",
    /saveAddressForm[\s\S]{0,1200}?请至少勾选一个/.test(source), "没找到「至少勾选一个」的校验");
  check("地址表单渲染了类目勾选框（绑定到 enabled_stages 数组）",
    /x-model="addressForm\.enabled_stages"/.test(html) && /:value="k"/.test(html),
    "没找到勾选框的数组绑定");
  check("勾选框按 ADDRESS_STAGE_KEYS 渲染，不写死类目名",
    /x-for="k in ADDRESS_STAGE_KEYS"/.test(html), "勾选框没走 ADDRESS_STAGE_KEYS");
}

// ---------- P4-C：1 对 1 类目的洞口/窗位名称 ----------
//
// 「1 对 1」按门洞逐个建档。洞口名没填/没传，业主端就只剩「第 N 次」，
// 分不清哪个是主卧、哪个是阳台。这里钉住「必须填」这条规则。

{
  check("1 对 1 类目需要洞口名",
    F.addressNeedsLabel("框架1对1") && F.addressNeedsLabel("玻扇1对1"));
  check("普通阶段不需要洞口名",
    !F.addressNeedsLabel("框架施工") && !F.addressNeedsLabel("售后保养"));
  check("洞口名阶段清单是 2 个", F.ADDRESS_LABELED_STAGES.length === 2);
  check("每个洞口名阶段都是真实阶段",
    F.ADDRESS_LABELED_STAGES.every((k) => F.ADDRESS_STAGE_KEYS.includes(k)));
}

{
  // 批量：1 对 1 类目没填洞口名时该行不可勾选，否则提交必然逐条失败。
  const client = Object.create(F);
  client.addressBulkStage = { a: "框架1对1", b: "框架1对1", c: "框架施工" };
  client.addressBulkLabel = { a: "主卧飘窗", b: "" };
  check("1 对 1 填了洞口名才允许勾选", client.addressBulkPickable(bulkItem("a", "框架1对1")) === true);
  check("1 对 1 没填洞口名不允许勾选", client.addressBulkPickable(bulkItem("b", "框架1对1")) === false);
  check("普通阶段不受洞口名影响", client.addressBulkPickable(bulkItem("c", "框架施工")) === true);
}

{
  // 同洞口内的「第几次」（unitSeq / unitTotal）。
  //
  // 起因：真机截图里后台详情出现两行一模一样的「主卧 C1 洞口」，
  // 员工点「移除」时不知道在动哪一次。补「第 N 次」时又不能用 stage.slot + 1——
  // slot 是**整个类目**内的序号：主卧占 0/1、次卧占 2，次卧那条会被写成「第 3 次」。
  const stages = [
    { stage_key: "框架1对1", label: "主卧 C1 洞口", slot: 0, visible: true, created: at(1), publication_id: "a".repeat(32) },
    { stage_key: "框架1对1", label: "主卧 C1 洞口", slot: 1, visible: true, created: at(2), publication_id: "b".repeat(32) },
    { stage_key: "框架1对1", label: "次卧 C2 洞口", slot: 2, visible: true, created: at(3), publication_id: "c".repeat(32) },
  ];
  const groups = F.buildAddressStageGroups(stages);
  const items = groups[0].items;
  check("同洞口内序号按洞口独立计数",
    same(items.map((i) => i.unitSeq), [1, 2, 1]), JSON.stringify(items.map((i) => i.unitSeq)));
  check("同洞口条数按洞口独立计数",
    same(items.map((i) => i.unitTotal), [2, 2, 1]), JSON.stringify(items.map((i) => i.unitTotal)));
  check("只做过一次的洞口不会被写成「第 3 次」（slot+1 的坑）",
    items[2].unitSeq === 1 && items[2].unitTotal === 1);
  check("普通阶段不带 unitSeq（模板仍按 slot 显示「第 N 次」）",
    F.buildAddressStageGroups([rec("售后保养", 0), rec("售后保养", 1)])
      .every((g) => g.items.every((i) => i.unitSeq === undefined)));
}

{
  const htmlPath = path.join(__dirname, "index.html");
  const html = fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, "utf8") : "";
  const source = fs.readFileSync(SOURCE, "utf8");
  check("补挂时把洞口名一起提交",
    /submitAddressAttach[\s\S]{0,2000}?body\.label/.test(source), "submitAddressAttach 没带 label");
  check("补挂 1 对 1 缺洞口名时前端先挡下（别等后端 400）",
    /submitAddressAttach[\s\S]{0,2000}?addressNeedsLabel/.test(source));
  check("补挂界面按 addressNeedsLabel 显隐洞口名输入框",
    html.includes("addressNeedsLabel(addressAttachStage)"));
  check("分享弹窗也有洞口名输入框",
    html.includes("addressNeedsLabel(addressStage)"));
  check("地址详情里 1 对 1 显示洞口名而不是「第 N 次」",
    /x-show="stage\.label"/.test(html));
  check("同洞口多次留档在后台也标「第 N 次」（否则两行一模一样）",
    /stage\.unitTotal\s*>\s*1[\s\S]{0,80}?stage\.unitSeq/.test(html),
    "模板没用 unitTotal/unitSeq");
}

// ---------- 汇总 ----------

console.log(`\naddress-client 纯逻辑检查：${passed} 项通过，${failures.length} 项失败。`);
if (failures.length) {
  failures.forEach((f) => console.log(`  ✗ ${f}`));
  process.exit(1);
}
