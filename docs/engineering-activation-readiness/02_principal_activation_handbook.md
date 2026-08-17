# 主理人手动激活手册（仅主理人本人 · 在人类终端执行）

> 文件性质：**唯一由人类（主理人）执行的动作说明**。
> AI 不代执行、不伪造授权、不宣称"已帮你翻开关"。任何"AI 已代你翻开关/代你授权"的说法均属违规或伪造，请立即用下面的 `grep` 核对。
> 执行前必须先完成《01_四角色证据清单+就绪核对表》全部 ✓、四角色真实签署、且 `human_authorization` 已登记。

### 两件动作，地点不同（先分清）
| 动作 | 在哪里做 | 用什么文件 |
|---|---|---|
| ① 登记 `human_authorization`（授权） | **你自己的 Mac**（不用登服务器） | 《03_签署页+授权登记》第二节 |
| ② 翻 `engineering_enabled` 开关 | **登服务器 CVM**（终端敲命令） | 本手册第一节 |

> 你问的"终端登记 human_authorization 到底在哪"——答案就是：**在你 Mac 上填《03_签署页》第二节并保存**，那就是登记，没有别的隐藏入口。

---

## 〇、前置自检（执行前必须全 ✓，否则停止）

- [ ] 《01_…核对表》第三节 第 1、2、3、5、6 项全 ✓
- [ ] 四角色（production-owner / release-manager / security-owner / auditor）已在《03_签署页》第一节签齐
- [ ] `human_authorization` 已在《03_签署页》第二节由主理人本人填写并保存（= 已登记，USER）
- [ ] 已确认：此动作**真实激活工程层**，后果由主理人承担

任一不满足 → **停止**，先补齐，不得执行。

---

## 怎样打开"终端"来登服务器（非技术也能做）
1. 在你的 Mac 上，按 `Command(⌘) + 空格`，输入"**终端**"（或 Terminal），回车打开。
2. 终端窗口出来后，**整段复制下面"第一节"的代码块**，在窗口里右键"粘贴"，回车即可。
3. 每一步的返回结果按"第二节"的要点核对；看不懂就原样截图发我，我帮你判断。

---

## 一、执行步骤（整段复制即可，零输入）

```bash
# 1) 登录 CVM
ssh root@119.45.176.5

# 2) 备份治理开关（留退路，便于回滚）
cp /opt/boip/agents/config.yaml /opt/boip/agents/config.yaml.bak.$(date +%Y%m%d)

# 3) 仅改第 102 行：engineering_enabled: false → true（保留原有缩进）
sed -i '102s/engineering_enabled: false/engineering_enabled: true/' /opt/boip/agents/config.yaml

# 4) 立即核对改动（应只此一处变为 true，其他不得被误改）
grep -n 'engineering_enabled' /opt/boip/agents/config.yaml

# 5) 重启后端使开关生效
systemctl restart boip-backend

# 6) 确认后端已起
systemctl status boip-backend --no-pager | head -8

# 7) 生效验证（后端健康）
curl -s http://127.0.0.1:8000/health
```

---

## 二、生效确认要点（看返回，不猜）

- **步骤 4 的 `grep`**：应只显示 `  engineering_enabled: true` 一行；若 `config.yaml` 其他行也出现 `engineering_enabled`，说明误改，立即执行第三节回滚。
- **步骤 6**：`systemctl status` 显示 `active (running)`。
- **步骤 7**：`/health` 返回 `ok`（或后端约定的健康结构）。
- 工程层使能后，**前端仍是 Phase 0 占位看板、无登录入口**——这是产品当前进度，不是部署故障。

---

## 三、回滚（若执行后异常，随时可退）

```bash
# 还原备份（日期换成步骤 2 实际生成的日期）
cp /opt/boip/agents/config.yaml.bak.$(date +%Y%m%d) /opt/boip/agents/config.yaml
systemctl restart boip-backend
```

---

## 四、红线提醒（务必读）

- 此动作**真实激活工程层**，后果由主理人承担；AI 不参与执行与决策。
- 翻开关**不自动改变公网暴露**：前端 `:3000`、后端 `:8000`（仅 Mac IP）现状不变。
- 如需把工程能力公开给外部用户，属**另一独立决策**，须四角色另行评审，不在本手册范围。
- 完成后建议在《01_…核对表》记录：激活时间戳、执行人（主理人）、`grep` 结果快照，连同四角色签署一并归档。

---

## 五、与《01_核对表》的关系

本手册 = 核对表全部 ✓ 后的**最后一步动作**。
核对表负责"证据 + 签署 + 闸门放行"，本手册负责"主理人在人类终端翻开关 + 重启 + 验证"。
两者不可互换，也不可由 AI 代劳任一部分。
