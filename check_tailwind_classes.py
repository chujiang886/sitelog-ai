#!/usr/bin/env python3
"""比对 index.html 用到的 Tailwind 类，与预构建 vendor/app.css 里实际存在的类。

【为什么需要这个检查】
项目用 Tailwind CLI 预构建 CSS：
    tailwindcss -i app.css -o vendor/app.css --content ./index.html,./auth-client.js
也就是说 CSS 里只包含「构建那一刻 index.html 里出现过」的类。
后续改了 index.html 却忘了 `npm run build`，新加的类在 CSS 里根本不存在，
浏览器不报错、页面只是少了样式——静默失效，看截图才发现。

【与 Tailwind 的 JIT 无关的坑】
Tailwind 的 content 扫描是纯文本匹配。它会把 JS 字符串里的 `'bg-red-50'`
也算作「用过」，但不会识别运行时拼接出来的类名。所以这里只扫 class="..." 属性，
避免把 :class 里的变量名当成类名报出来。

用法：
    python3 check_tailwind_classes.py [index.html] [vendor/app.css]
退出码 0 = 全部命中；1 = 有缺失。
"""

import re
import sys
from pathlib import Path

html_path = Path(sys.argv[1] if len(sys.argv) > 1 else "index.html")
css_path = Path(sys.argv[2] if len(sys.argv) > 2 else "vendor/app.css")

html = html_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

# --- 1) 收集 CSS 里真实存在的类名 ---
# 只在「选择器位置」找，避免把 content:"..." 里的点号误当类名。
css_classes = set()
# 去掉注释
css_clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
# 逐个规则取选择器：每条规则是 "选择器{声明}"，@media 只是包一层，选择器里没有 '{'
for chunk in css_clean.split("{"):
    selector = chunk.rsplit("}", 1)[-1]
    for m in re.finditer(r"\.((?:[A-Za-z0-9_-]|\\.)+)", selector):
        css_classes.add(m.group(1).replace("\\", ""))

# --- 2) 收集 HTML 里用到的类名（只扫 class="..."）---
# 负向后顾排除 :class="..." / x-bind:class="..." —— 那些是 Alpine 表达式，
# 里面的 'bg-red-50' 是「可能用到的类」，混进来会淹没真正的问题。
used = {}
for m in re.finditer(r'(?<![:\w-])class="([^"]*)"', html):
    for cls in m.group(1).split():
        used[cls] = used.get(cls, 0) + 1

# --- 3) HTML 内联 <style> 里自己定义的类也算存在 ---
inline_defined = set()
for m in re.finditer(r"<style[^>]*>(.*?)</style>", html, flags=re.S):
    for cm in re.finditer(r"\.([A-Za-z][A-Za-z0-9_-]*)", m.group(1)):
        inline_defined.add(cm.group(1))

IGNORE = {"no-print", "x-cloak"}

missing = sorted(
    c for c in used
    if c not in css_classes and c not in inline_defined and c not in IGNORE
)

print(f"HTML: {html_path}")
print(f"CSS : {css_path}（{len(css_classes)} 个类；内联 style 另有 {len(inline_defined)} 个）")
print(f"HTML class 属性用到 {len(used)} 个类，其中 {len(missing)} 个在 CSS 里找不到：")
for c in missing:
    print(f"  ✗ {c}  （用了 {used[c]} 次）")

if missing:
    print()
    print("处理方式（二选一）：")
    print("  1. 跑 `npm run build` 重新生成 vendor/app.css —— 这是标准做法，能一次补齐所有新类；")
    print("  2. 无法构建时，把上面这些类换成 CSS 里已存在的等价类（下方给出候选）。")
    print()
    # 给几个常用替代候选，减少手工翻 CSS 的功夫
    print("CSS 里已有的近似类（供替换参考）：")
    groups = {
        "padding-x": sorted(c for c in css_classes if re.fullmatch(r"px-[\d.]+", c)),
        "padding-y": sorted(c for c in css_classes if re.fullmatch(r"py-[\d.]+", c)),
        "space-y": sorted(c for c in css_classes if re.fullmatch(r"space-y-[\d.]+", c)),
        "gap": sorted(c for c in css_classes if re.fullmatch(r"gap-[\d.]+", c)),
        "z-index": sorted(c for c in css_classes if re.fullmatch(r"z-[\d.]+", c)),
        "max-h": sorted(c for c in css_classes if re.fullmatch(r"max-h-[\d.]+", c)),
    }
    for name, items in groups.items():
        if items:
            print(f"  {name}: {', '.join(items)}")
    sys.exit(1)

print("全部命中。")
