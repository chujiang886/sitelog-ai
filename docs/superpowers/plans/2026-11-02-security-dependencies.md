# 前端依赖安全补丁计划

用户已授权三项独立修复并回归归档、分享、客户签认；不推送、不发布、不增加功能。
本纯修复候选从现役生产前端 686c736 建立 hotfix/production-security-only-20261102；原 main 候选和归档质量审阅分支完整保留，不合入埋点或合规模板。

1. DOMPurify 3.4.15 → 3.4.17：先用版本/本地 vendor 一致性与真实浏览器影子树测试复现，再升级依赖及实际加载的 vendor。保持编辑器净化配置及业务流程不变，独立提交。
2. postcss-selector-parser 6.1.4 → 兼容的 6.1.5：用独立子进程有超时保护地测试大平面选择器，并核对常规报告选择器及构建，独立提交。
3. source-map-js 1.2.1 → 1.2.2：测试非法及超大索引偏移拒绝、正常映射往返，独立提交。
4. 后端已有备份修复候选分支更新配套前端 SHA 与候选清单，另行提交；不改生产版本指针。
5. 干净安装、完整依赖审计、单测、构建、前后端跨仓库守卫、隔离浏览器归档/分享/客户签认及密钥扫描。证据放仓库外，禁止读取或改写真实归档。

公告依据：
- https://github.com/advisories/GHSA-cg2g-xh64-v4q7 （DOMPurify，其他同版本公告也由 3.4.17 修复）
- https://github.com/advisories/GHSA-rj75-hqrm-r3gf （选择器解析）
- https://github.com/advisories/GHSA-68fv-2mgg-jv7q （索引 source map 偏移）

本轮升级最小兼容补丁，不使用全量 npm audit fix 扩大改动范围。
