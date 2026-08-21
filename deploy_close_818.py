#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重发布 8/18 收盘版（名称修正后）：更新静态 HTML + close dyn + wrangler deploy。"""
import os, shutil, subprocess

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
PUB = "/tmp/cfpub"
PUB_STOCK = os.path.join(PUB, "stock-a")
SYS_PY = "/usr/bin/python3"
DATE = "2026-08-18"

# 1. 静态 HTML（收盘版 → 根）
close_html = os.path.join(BASE, f"A股复盘_{DATE}.html")
shutil.copy(close_html, os.path.join(PUB_STOCK, "index.html"))
shutil.copy(close_html, os.path.join(PUB_STOCK, f"A股复盘_{DATE}.html"))

# 2. close dyn 子树
dyn_root = os.path.join(PUB_STOCK, "dyn")
os.makedirs(os.path.join(dyn_root, "data"), exist_ok=True)
shutil.copy(os.path.join(BASE, "app.html"), os.path.join(dyn_root, "index.html"))
shutil.copy(os.path.join(BASE, "web", "chart.umd.min.js"), os.path.join(dyn_root, "chart.umd.min.js"))
r = subprocess.run([SYS_PY, "extract_dyn.py", close_html, dyn_root], cwd=BASE, capture_output=True, text=True)
if r.returncode != 0:
    print("extract_dyn(close) warning:", r.stderr[:300])
shutil.copy(os.path.join(DATA, "manifest_close.json"), os.path.join(dyn_root, "manifest.json"))
shutil.copy(os.path.join(DATA, f"{DATE}_close_bundle.json"), os.path.join(dyn_root, "data", f"{DATE}_close_bundle.json"))

# 3. 部署
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
