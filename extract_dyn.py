#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_dyn.py — 从每日渲染的静态 HTML 中抽取动态页所需的 JS 资源。

静态 HTML 内联了两类脚本：
  1) 图表/图例/缩放/排序/截止戳逻辑：以 `const D = {...}` 开头的大脚本
     （render.py 在静态页里把数据内联成 const D）。动态页里数据改为运行时
     从 bundle.json 注入，所以这个脚本里的 `const D = {...};` 首句必须剥离，
     由 shell 在运行时以 `var D = <payload>` 注入。剥离后得到 chartlogic.js。
  2) 控制按钮逻辑（saTrigger / reextractCheck 等）：独立 <script> 块，
     动态页里 body_html 经 innerHTML 注入、其中的 <script> 不会执行，
     因此单独抽成 ctrl.js，由 shell 作为真实 <script> 加载。

用法：
  python3 extract_dyn.py <static_html> <out_dir>
    <static_html> 例如 A股复盘_2026-08-13.html
    <out_dir>     抽出的 chartlogic.js / ctrl.js 写入此目录（通常为 dyn 暂存子树）
"""
import sys, os


def extract_scripts(html):
    """返回所有无 src 属性的 <script> 块内容列表。"""
    out = []
    i, n = 0, len(html)
    while True:
        j = html.find("<script", i)
        if j == -1:
            break
        k = html.find(">", j)
        if k == -1:
            break
        open_tag = html[j:k]
        if "src=" in open_tag:
            end = html.find("</script>", k)
            i = end + len("</script>") if end != -1 else n
            continue
        end = html.find("</script>", k)
        if end == -1:
            break
        out.append(html[k + 1:end])
        i = end + len("</script>")
    return out


def strip_const_d(content):
    """剥离脚本首句 `const D = {...};`（大对象，括号配对），返回剩余逻辑。"""
    idx = content.find("const D =")
    if idx == -1:
        return content
    b = content.find("{", idx)
    if b == -1:
        return content
    depth, p = 0, b
    while p < len(content):
        c = content[p]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        p += 1
    semi = content.find(";", p)
    cut = semi + 1 if semi != -1 else p + 1
    return content[cut:].lstrip("\n")


def main():
    if len(sys.argv) < 3:
        print("usage: extract_dyn.py <static_html> <out_dir>")
        sys.exit(1)
    html_path, out_dir = sys.argv[1], sys.argv[2]
    if not os.path.exists(html_path):
        print("x 静态 HTML 不存在:", html_path)
        sys.exit(1)
    html = open(html_path, encoding="utf-8").read()
    scripts = extract_scripts(html)

    chartlogic, ctrl = None, None
    for s in scripts:
        if "const D =" in s:
            chartlogic = strip_const_d(s)
        elif "function saTrigger" in s:
            ctrl = s

    if chartlogic is None:
        print("x 未找到图表逻辑脚本（含 const D =）")
        sys.exit(1)
    if ctrl is None:
        print("x 未找到控制按钮脚本（含 function saTrigger）")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    cl_path = os.path.join(out_dir, "chartlogic.js")
    cj_path = os.path.join(out_dir, "ctrl.js")
    open(cl_path, "w", encoding="utf-8").write(chartlogic)
    open(cj_path, "w", encoding="utf-8").write(ctrl)
    print("ok 抽出 chartlogic.js (%d 字符) + ctrl.js (%d 字符) → %s"
          % (len(chartlogic), len(ctrl), out_dir))


if __name__ == "__main__":
    main()
