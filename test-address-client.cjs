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
    same(pending, ["五金安装", "离场自检"]), JSON.stringify(pending));
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
  check("前端阶段清单是 6 个", F.ADDRESS_STAGE_KEYS.length === 6, `实际 ${F.ADDRESS_STAGE_KEYS.length}`);
  check("每个阶段都有显示名",
    F.ADDRESS_STAGE_KEYS.every((k) => typeof F.ADDRESS_STAGE_DISPLAY[k] === "string"));
}

// ---------- 结构守卫：别再退回「按留档条数算阶段数」 ----------

{
  const htmlPath = path.join(__dirname, "index.html");
  const html = fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, "utf8") : "";
  const source = fs.readFileSync(SOURCE, "utf8");

  check("index.html 已改用 addressDoneStages 展示已归档阶段数",
    html.includes("addressDoneStages + ' 个阶段"), "没找到预期的绑定");
  check("index.html 里没有残留「按可见留档条数当阶段数」的写法",
    !/filter\(\s*s\s*=>\s*s\.visible\s*\)\.length\s*\+\s*['"] 个阶段/.test(html));
  check("address-client.js 的二维码卡片不再按留档条数算阶段数",
    !/const done\s*=\s*\(address\.stages\s*\|\|\s*\[\]\)\.filter/.test(source));
  check("address-client.js 的二维码卡片改用 addressDoneStageCount",
    /addressDoneStageCount\(address\.stages\)/.test(source));
}

// ---------- 汇总 ----------

console.log(`\naddress-client 纯逻辑检查：${passed} 项通过，${failures.length} 项失败。`);
if (failures.length) {
  failures.forEach((f) => console.log(`  ✗ ${f}`));
  process.exit(1);
}
