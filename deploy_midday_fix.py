#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手动 staging 午盘版并部署到 Cloudflare Pages（只更新静态文件和 dyn）。"""
import os, shutil, subprocess, json

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
PUB = "/tmp/cfpub"
PUB_STOCK = os.path.join(PUB, "stock-a")
SYS_PY = "/usr/bin/python3"

# 1. 创建目录
os.makedirs(os.path.join(PUB_STOCK, "午盘"), exist_ok=True)

# 2. 收盘版（不更新，保留线上已有）
close_html = os.path.join(BASE, "A股复盘_2026-08-17.html")
shutil.copy(close_html, os.path.join(PUB_STOCK, "index.html"))
shutil.copy(close_html, os.path.join(PUB_STOCK, "A股复盘_2026-08-17.html"))

# 3. 午盘版（新渲染的）
midday_html = os.path.join(BASE, "A股午盘_2026-08-18.html")
shutil.copy(midday_html, os.path.join(PUB_STOCK, "午盘", "index.html"))
shutil.copy(midday_html, os.path.join(PUB_STOCK, "午盘", "A股午盘_2026-08-18.html"))

# 4. CNAME / .nojekyll
for f in ("CNAME", ".nojekyll"):
    src = os.path.join(BASE, f)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(PUB, f))

# 5. dyn 目录（收盘版）
dyn_root = os.path.join(PUB_STOCK, "dyn")
os.makedirs(os.path.join(dyn_root, "data"), exist_ok=True)
shutil.copy(os.path.join(BASE, "app.html"), os.path.join(dyn_root, "index.html"))
shutil.copy(os.path.join(BASE, "web", "chart.umd.min.js"), os.path.join(dyn_root, "chart.umd.min.js"))
r = subprocess.run([SYS_PY, "extract_dyn.py", close_html, dyn_root], cwd=BASE, capture_output=True, text=True)
if r.returncode != 0:
    print("extract_dyn(close) warning:", r.stderr[:200])
shutil.copy(os.path.join(DATA, "manifest_close.json"), os.path.join(dyn_root, "manifest.json"))
shutil.copy(os.path.join(DATA, "2026-08-17_close_bundle.json"), os.path.join(dyn_root, "data", "2026-08-17_close_bundle.json"))

# 6. dyn 目录（午盘版）
dyn_midday = os.path.join(dyn_root, "午盘")
os.makedirs(os.path.join(dyn_midday, "data"), exist_ok=True)
shutil.copy(os.path.join(BASE, "app.html"), os.path.join(dyn_midday, "index.html"))
shutil.copy(os.path.join(BASE, "web", "chart.umd.min.js"), os.path.join(dyn_midday, "chart.umd.min.js"))
r = subprocess.run([SYS_PY, "extract_dyn.py", midday_html, dyn_midday], cwd=BASE, capture_output=True, text=True)
if r.returncode != 0:
    print("extract_dyn(midday) warning:", r.stderr[:200])
shutil.copy(os.path.join(DATA, "manifest_midday.json"), os.path.join(dyn_midday, "manifest.json"))
shutil.copy(os.path.join(DATA, "2026-08-18_midday_bundle.json"), os.path.join(dyn_midday, "data", "2026-08-18_midday_bundle.json"))

# 7. 部署
print("[deploy] 开始 wrangler deploy ...")
env = dict(os.environ)
env["CLOUDFLARE_API_TOKEN"] = env.get("CF_TOKEN", "")
env["CLOUDFLARE_ACCOUNT_ID"] = env.get("CF_ACCOUNT", "99acfa35cfa82fb90d916516a1ed0a2e")
r = subprocess.run(
    ["npx", "wrangler", "pages", "deploy", PUB, "--project-name=stock-a", "--branch=main", "--commit-dirty=true"],
    cwd=BASE, env=env, capture_output=True, text=True, timeout=120
)
print(r.stdout[-800:] if r.stdout else "")
if r.returncode != 0:
    print("DEPLOY FAILED:", r.stderr[-800:])
    exit(1)
print("[deploy] 完成")
