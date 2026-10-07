#!/usr/bin/env python3
"""变异测试：故意打坏 LOGO 上传代码，验证 test-logo-upload.cjs 真的会失败。

【为什么必须做这一步】
断言「通过」有两种可能：代码是对的，或者断言根本没在检查东西。
后一种更危险——它让人以为有守卫，其实一直绿灯。
所以这里把每个守卫对应的代码逐个打坏，**每一个都必须让测试变红**。
如果某个变异没被抓到，说明那条守卫是空转的，要补断言。

【2026-10-07 重写：本脚本与 test-logo-upload.cjs 是同一处债】
它原先写死 `SRC = <某个沙箱目录>/sitelog-p1-verify`、`NODE = .../22.22.2-2/bin/node`
（版本号是错的），并且把**所有**变异都打在 `index.html` 上——而 2026-10-05 的
P2 拆分已经把 `prepareLogoUpload` / `fileToDataUrl` / `uploadClientLogo` 搬到了
**app-main.js**。也就是说：它和 `test-logo-upload.cjs` 一起在拆分当天就失效了，
只是它不在 `npm test` 里（要 `npm run test:logo:mutate`），所以一直没人发现。
两者必须一起修，否则「测试全绿」只是没人在跑。

现在：源文件 = 本脚本所在仓库，变异按 target 分别打在 `app-main.js` 或
`index.html` 上，临时目录里两个文件都放，`SITELOG_BACKEND` 默认指向同级
的 `chujiang-sitelog-share`（`~/repos/` 下的实际布局）。

用法：python3 mutate-logo-upload.py
      SITELOG_BACKEND=/path/to/cj-share python3 mutate-logo-upload.py
      SITELOG_NODE=/path/to/node python3 mutate-logo-upload.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent
# ⚠️ 本机 node 是 22.22.2-3（不是 -2）。playwright 之类不在这里用，但版本号写错
# 会让脚本以「找不到解释器」的形式失败，看起来像测试挂了。
NODE = os.environ.get("SITELOG_NODE") or "/Users/chujiangai/.workbuddy-ai/binaries/node/versions/22.22.2-3/bin/node"
# 跨文件守卫（前端目标体积 < 后端 MAX_BYTES、界面文案 == 后端上限）需要后端源码。
# 临时目录里没有仓库的相对布局，必须显式告诉它去哪儿找。
ENV = {**os.environ,
       "SITELOG_BACKEND": os.environ.get("SITELOG_BACKEND") or str(SRC.parent / "chujiang-sitelog-share")}

# (说明, 目标文件, 原文, 替换后)
#
# 片段一律**不带行首缩进**——子串匹配即可，缩进改了也不会让变异静默跳过。
MUTATIONS = [
    (
        "PNG 改成按 JPEG 编码（透明底会变黑）",
        "app-main.js",
        "const shrunk = type === 'image/png' ? canvas.toDataURL('image/png') : canvas.toDataURL(type, 0.9);",
        "const shrunk = type === 'image/png' ? canvas.toDataURL('image/jpeg', 0.8) : canvas.toDataURL(type, 0.9);",
    ),
    (
        "复用固定输出 JPEG 的 compressDataUrl",
        "app-main.js",
        "const shrunk = type === 'image/png' ? canvas.toDataURL('image/png') : canvas.toDataURL(type, 0.9);",
        "const shrunk = await this.compressDataUrl(original);",
    ),
    (
        "上传时绕过 prepareLogoUpload，直接传原图",
        "app-main.js",
        "const dataUrl = await this.prepareLogoUpload(file);",
        "const dataUrl = await this.fileToDataUrl(file);",
    ),
    (
        "缩完更大也采用压缩结果（白掉一次画质）",
        "app-main.js",
        "return shrunk.length < original.length ? shrunk : original;",
        "return shrunk;",
    ),
    (
        "JPEG 不铺白底（透明区域变黑）",
        "app-main.js",
        "if (type === 'image/jpeg') { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, tw, th); }",
        "if (false) { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, tw, th); }",
    ),
    (
        "重新引入 createObjectURL",
        "app-main.js",
        "img.src = original;",
        "img.src = URL.createObjectURL(file);",
    ),
    (
        "去掉 MIME 白名单校验",
        "app-main.js",
        "if (!/^image\\/(png|jpeg|webp)$/.test(type)) throw new Error('仅支持 PNG、JPG、WebP 格式的图片');",
        "if (false) throw new Error('仅支持 PNG、JPG、WebP 格式的图片');",
    ),
    (
        "缩放长边从 1200 改成 4000（等于不缩）",
        "app-main.js",
        "async prepareLogoUpload(file, maxEdge = 1200, maxDataUrl = 1400000)",
        "async prepareLogoUpload(file, maxEdge = 4000, maxDataUrl = 1400000)",
    ),
    (
        # ⚠️ 这条的落点是 index.html：文案在模板里，方法在 app-main.js。
        # 「两个文件都要读」正是本次修法的一半，这条变异就是它的守卫。
        "界面文案改成 20MB（与后端 8MB 不一致）",
        "index.html",
        "最大 8MB）",
        "最大 20MB）",
    ),
]

TARGETS = ("app-main.js", "index.html")

work = Path(tempfile.mkdtemp(prefix="logo-mutation-"))
originals = {name: (SRC / name).read_text(encoding="utf-8") for name in TARGETS}
shutil.copy(SRC / "test-logo-upload.cjs", work / "test-logo-upload.cjs")


def write_all(overrides=None):
    """把（可能被变异的）文件写进临时目录，供测试读取。"""
    for name in TARGETS:
        text = (overrides or {}).get(name, originals[name])
        (work / name).write_text(text, encoding="utf-8")


def run_test():
    return subprocess.run([NODE, "test-logo-upload.cjs"], cwd=work,
                          capture_output=True, text=True, env=ENV)


# 先确认未变异的基线是通过的
write_all()
baseline = run_test()
if baseline.returncode != 0:
    print("❌ 基线就没过，变异测试无意义：")
    print(baseline.stdout, baseline.stderr)
    shutil.rmtree(work, ignore_errors=True)
    sys.exit(2)
print("✅ 基线通过\n")

escaped = 0
for label, target, old, new in MUTATIONS:
    source = originals[target]
    if old not in source:
        print(f"⚠️  跳过（{target} 里没找到原文，可能又被搬走了）：{label}")
        print(f"     期望片段：{old[:70]}...")
        escaped += 1
        continue
    write_all({target: source.replace(old, new, 1)})
    run = run_test()
    caught = run.returncode != 0
    marks = [line.strip() for line in run.stdout.splitlines() if line.strip().startswith("✗")]
    print(("✅ 被抓到  " if caught else "❌ 漏掉了  ") + f"[{target}] " + label)
    if caught:
        for m in marks[:3]:
            print("             " + m)
    else:
        escaped += 1

write_all()
shutil.rmtree(work, ignore_errors=True)

print()
if escaped:
    print(f"有 {escaped} 个变异没被抓到——对应的守卫是空转的，需要补断言。")
    sys.exit(1)
print(f"全部 {len(MUTATIONS)} 个变异都被抓到，守卫有效。")
