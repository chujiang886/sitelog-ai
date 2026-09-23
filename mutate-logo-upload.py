#!/usr/bin/env python3
"""变异测试：故意打坏 index.html 的 LOGO 上传代码，验证 test-logo-upload.cjs 真的会失败。

【为什么必须做这一步】
断言「通过」有两种可能：代码是对的，或者断言根本没在检查东西。
后一种更危险——它让人以为有守卫，其实一直绿灯。
所以这里把每个守卫对应的代码逐个打坏，**每一个都必须让测试变红**。
如果某个变异没被抓到，说明那条守卫是空转的，要补断言。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path("/Users/chujiangai/WorkBuddy AI/2026-09-22-10-23-29/sitelog-p1-verify")
NODE = "/Users/chujiangai/.workbuddy-ai/binaries/node/versions/22.22.2-2/bin/node"
# 临时目录里没有 ../sitelog-p0-verify，跨文件守卫找不到后端 client_logos.py，
# 得显式告诉它去哪儿找。
ENV = {**os.environ, "SITELOG_BACKEND": str(SRC.parent / "sitelog-p0-verify")}

# (说明, 原文, 替换后)
MUTATIONS = [
    (
        "PNG 改成按 JPEG 编码（透明底会变黑）",
        "const shrunk = type === 'image/png' ? canvas.toDataURL('image/png') : canvas.toDataURL(type, 0.9);",
        "const shrunk = type === 'image/png' ? canvas.toDataURL('image/jpeg', 0.8) : canvas.toDataURL(type, 0.9);",
    ),
    (
        "复用固定输出 JPEG 的 compressDataUrl",
        "const shrunk = type === 'image/png' ? canvas.toDataURL('image/png') : canvas.toDataURL(type, 0.9);",
        "const shrunk = await this.compressDataUrl(original);",
    ),
    (
        "上传时绕过 prepareLogoUpload，直接传原图",
        "const dataUrl = await this.prepareLogoUpload(file);",
        "const dataUrl = await this.fileToDataUrl(file);",
    ),
    (
        "缩完更大也采用压缩结果（白掉一次画质）",
        "return shrunk.length < original.length ? shrunk : original;",
        "return shrunk;",
    ),
    (
        "JPEG 不铺白底（透明区域变黑）",
        "if (type === 'image/jpeg') { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, tw, th); }",
        "if (false) { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, tw, th); }",
    ),
    (
        "重新引入 createObjectURL",
        "img.src = original;",
        "img.src = URL.createObjectURL(file);",
    ),
    (
        "去掉 MIME 白名单校验",
        "if (!/^image\\/(png|jpeg|webp)$/.test(type)) throw new Error('仅支持 PNG、JPG、WebP 格式的图片');",
        "if (false) throw new Error('仅支持 PNG、JPG、WebP 格式的图片');",
    ),
    (
        "界面文案改成 20MB（与后端 8MB 不一致）",
        "最大 8MB）",
        "最大 20MB）",
    ),
    (
        "缩放长边从 1200 改成 4000（等于不缩）",
        "async prepareLogoUpload(file, maxEdge = 1200, maxDataUrl = 1400000)",
        "async prepareLogoUpload(file, maxEdge = 4000, maxDataUrl = 1400000)",
    ),
]

work = Path(tempfile.mkdtemp(prefix="logo-mutation-"))
original = (SRC / "index.html").read_text(encoding="utf-8")
shutil.copy(SRC / "test-logo-upload.cjs", work / "test-logo-upload.cjs")

# 先确认未变异的基线是通过的
(work / "index.html").write_text(original, encoding="utf-8")
baseline = subprocess.run([NODE, "test-logo-upload.cjs"], cwd=work, capture_output=True, text=True, env=ENV)
if baseline.returncode != 0:
    print("❌ 基线就没过，变异测试无意义：")
    print(baseline.stdout, baseline.stderr)
    sys.exit(2)
print("✅ 基线通过\n")

escaped = 0
for label, old, new in MUTATIONS:
    if old not in original:
        print(f"⚠️  跳过（原文没找到，可能已被重构）：{label}")
        print(f"     期望片段：{old[:70]}...")
        escaped += 1
        continue
    mutated = original.replace(old, new, 1)
    (work / "index.html").write_text(mutated, encoding="utf-8")
    run = subprocess.run([NODE, "test-logo-upload.cjs"], cwd=work, capture_output=True, text=True, env=ENV)
    caught = run.returncode != 0
    marks = [line.strip() for line in run.stdout.splitlines() if line.strip().startswith("✗")]
    print(("✅ 被抓到  " if caught else "❌ 漏掉了  ") + label)
    if caught:
        for m in marks[:3]:
            print("             " + m)
    else:
        escaped += 1

(work / "index.html").write_text(original, encoding="utf-8")
shutil.rmtree(work, ignore_errors=True)

print()
if escaped:
    print(f"有 {escaped} 个变异没被抓到——对应的守卫是空转的，需要补断言。")
    sys.exit(1)
print(f"全部 {len(MUTATIONS)} 个变异都被抓到，守卫有效。")
