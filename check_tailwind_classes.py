#!/usr/bin/env python3
"""比对 index.html 用到的类，与项目里实际存在的样式定义。

【为什么需要这个检查】
项目里有**两套**样式来源，缺任何一套都会静默失效（浏览器不报错、页面只是少了样式）：

  1. `vendor/app.css` —— Tailwind CLI 预构建产物：
         npm run build
         # tailwindcss -i app.css -o vendor/app.css --content ./index.html,./app-main.js,
         #   ./html2pdf-glue.js,./auth-client.js,./frame-client.js,./gallery-client.js
     它只包含「构建那一刻被扫描文件里出现过」的类。改了模板却忘了 build，
     新加的 Tailwind 类在 CSS 里根本不存在。

  2. `styles.css` —— 手写的自定义类（`.addr-*` 等）。
     ⚠️ 2026-10-05 的 P2 拆分把原本内联在 index.html `<style>` 里的自定义 CSS
     外置到了这个文件，而**本脚本当时没有跟着改扫描范围** —— 于是 84 个自定义类
     被误报成「缺失」，把真正的 3 个问题淹没了。2026-10-07 修。
     （教训：文件拆分后，所有「只扫某个文件」的守卫都要重新核对范围。
       否定型断言的失效是**静默**的，比变红更危险。）

【与 Tailwind 的 JIT 无关的坑】
Tailwind 的 content 扫描是纯文本匹配：它会把 JS 字符串里的 `'bg-red-50'` 也算作
「用过」，但不会识别运行时拼接出来的类名。所以这里只扫 `class="..."` 属性，
避免把 `:class` 里的变量名当成类名报出来。

【两档输出 —— 处理方式完全不同，别混】
  A. 缺 Tailwind 类 → 跑一次 `npm run build` 就能全部补齐
  B. 缺自定义类   → build 补不出来，必须手写进 styles.css

用法：
    python3 check_tailwind_classes.py [index.html]
退出码 0 = 全部命中；1 = 有缺失。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "index.html"
tailwind_path = ROOT / "vendor" / "app.css"
custom_path = ROOT / "styles.css"

# 自定义类的命名空间。styles.css 里的类靠这个前缀与 Tailwind 工具类区分开；
# 新增自定义命名空间（例如 `gal-*`）时同步加到这里。
CUSTOM_PREFIXES = ("addr-", "material-")

IGNORE = {"no-print", "x-cloak"}


def classes_in_css(text):
    """收集 CSS 里真实存在的类名 —— 只在「选择器位置」找，
    避免把 content:"..." 里的点号误当类名。"""
    out = set()
    clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # 每条规则是 "选择器{声明}"，@media 只是包一层，选择器里没有 '{'
    for chunk in clean.split("{"):
        selector = chunk.rsplit("}", 1)[-1]
        for m in re.finditer(r"\.((?:[A-Za-z0-9_-]|\\.)+)", selector):
            out.add(m.group(1).replace("\\", ""))
    return out


html = html_path.read_text(encoding="utf-8")
tailwind_classes = classes_in_css(tailwind_path.read_text(encoding="utf-8")) if tailwind_path.exists() else set()
custom_classes = classes_in_css(custom_path.read_text(encoding="utf-8")) if custom_path.exists() else set()

# HTML 内联 <style> 里自己定义的类也算存在（P2 拆分后已为空，保留以兼容）
inline_defined = set()
for m in re.finditer(r"<style[^>]*>(.*?)</style>", html, flags=re.S):
    for cm in re.finditer(r"\.([A-Za-z][A-Za-z0-9_-]*)", m.group(1)):
        inline_defined.add(cm.group(1))

# 只扫 class="..."；负向后顾排除 :class= / x-bind:class=（Alpine 表达式）
used = {}
for m in re.finditer(r'(?<![:\w-])class="([^"]*)"', html):
    for cls in m.group(1).split():
        used[cls] = used.get(cls, 0) + 1

known = tailwind_classes | custom_classes | inline_defined | IGNORE
missing = sorted(c for c in used if c not in known)


def is_custom(cls):
    return any(cls.startswith(p) for p in CUSTOM_PREFIXES)


missing_custom = [c for c in missing if is_custom(c)]
missing_tw = [c for c in missing if not is_custom(c)]

print(f"HTML: {html_path.name}")
print(f"  来源：vendor/app.css {len(tailwind_classes)} 个类"
      f" | styles.css {len(custom_classes)} 个类"
      f" | 内联 <style> {len(inline_defined)} 个")
print(f"  HTML class 属性用到 {len(used)} 个类，"
      f"缺失 {len(missing)} 个（Tailwind {len(missing_tw)} / 自定义 {len(missing_custom)}）")

if missing_tw:
    print()
    print("A) 缺 Tailwind 类 —— 跑 `npm run build` 即可全部补齐：")
    for c in missing_tw:
        print(f"   ✗ {c}  （用了 {used[c]} 次）")

if missing_custom:
    print()
    print("B) 缺自定义类 —— `npm run build` 补不出来，必须手写进 styles.css：")
    for c in missing_custom:
        print(f"   ✗ {c}  （用了 {used[c]} 次）")

if missing:
    sys.exit(1)

print("全部命中。")
