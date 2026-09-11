# sitelog-ai · 施格归档

门窗行业「现场施工归档 AI 助手」- 拖入照片 AI 自动归类整理，一键导出 PDF 给业主

## 在线访问

主应用：https://chujiang886.github.io/sitelog-ai/
共享 Key 配置（老板用）：https://chujiang886.github.io/sitelog-ai/share-key.html

## 老板部署

1. 打开 share-key.html → 填 Key → 生成工友链接
2. 微信群发给工友
3. 工友点开链接即用（自动保存 Key 到浏览器）

## 工程记录分享（v4.6.1）

在「设置 → 工程分享凭据」中导入管理员提供的私有 JSON 配置，或填写分享凭据。配置仅保存在当前浏览器，通过 X-Share-Token 发送到初匠分享服务；不得把真实凭据提交到仓库或放入公开链接。

创建、列表、撤回与恢复请求统一携带凭据。缺失或失效时引导重新配置。验证命令：`npm test`。
