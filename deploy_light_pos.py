#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重发布指定日期的收盘+午间静态 HTML + 动态页子树 + functions，wrangler deploy。

用法：
  python3 deploy_light_pos.py [YYYY-MM-DD]   # 不传日期则默认今天（工作日）

与 daily_pipeline.py 的区别：只做「暂存 + 部署」，不重新采集、不渲染。
动态页子树（stock-a/dyn/）逻辑与 daily_pipeline.stage_dyn 一致。
"""
import os, sys, shutil, subprocess, datetime, json
try:
    import fcntl
except ImportError:
    fcntl = None

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
PUB = "/tmp/cfpub"
PUB_STOCK = os.path.join(PUB, "stock-a")
SYS_PY = "/usr/bin/python3"
LOCK_FILE = os.path.join(BASE, ".pipeline.lock")  # 与流水线共用互斥锁，防并发部署竞态
CF_ACCOUNT_DEFAULT = "99acfa35cfa82fb90d916516a1ed0a2e"

if len(sys.argv) > 1:
    DATE = sys.argv[1]
else:
    today = datetime.date.today()
    if today.weekday() >= 5:  # 周末回退最近周五
        DATE = (today - datetime.timedelta(days=today.weekday() - 4)).strftime("%Y-%m-%d")
    else:
        DATE = today.strftime("%Y-%m-%d")

# 预装 wrangler 二进制路径（避免 npx 每次临时拉取导致超时/ENOTEMPTY 竞态）
NODE_BIN = "/Users/sugieliao/.workbuddy/binaries/node/versions/22.22.2/bin/node"
WRANGLER_JS = "/Users/sugieliao/.workbuddy/binaries/node/workspace/node_modules/wrangler/bin/wrangler.js"


def load_cloud_env():
    """CF_TOKEN 优先取环境变量，否则读 secrets.env（与 daily_pipeline 相同来源）。"""
    if os.environ.get("CF_TOKEN"):
        return os.environ["CF_TOKEN"], os.environ.get("CF_ACCOUNT", CF_ACCOUNT_DEFAULT)
    sp = os.path.join(BASE, "secrets.env")
    env = {}
    if os.path.exists(sp):
        for line in open(sp, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env.get("CF_TOKEN", ""), env.get("CF_ACCOUNT", CF_ACCOUNT_DEFAULT)


def stage_dyn(midday, date):
    """从本次渲染 HTML 抽取 JS + 复制 manifest/bundle 到动态页子树（与 daily_pipeline.stage_dyn 一致）。"""
    variant = "midday" if midday else "close"
    dyn_root = os.path.join(PUB_STOCK, "dyn")
    target = os.path.join(dyn_root, "午盘") if midday else dyn_root
    os.makedirs(os.path.join(target, "data"), exist_ok=True)
    # 1) 外壳 HTML（含 boot 逻辑 + 本地 Chart.js 引用）
    shutil.copy(os.path.join(BASE, "app.html"), os.path.join(target, "index.html"))
    # 2) 自托管 Chart.js
    web_chart = os.path.join(BASE, "web", "chart.umd.min.js")
    if os.path.exists(web_chart):
        shutil.copy(web_chart, os.path.join(target, "chart.umd.min.js"))
    # 3) 从本次渲染的静态 HTML 抽取图表逻辑 + 控制按钮逻辑
    html_path = os.path.join(BASE, ("A股午盘" if midday else "A股复盘") + f"_{date}.html")
    if os.path.exists(html_path):
        r = subprocess.run([SYS_PY, "extract_dyn.py", html_path, target],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("  x extract_dyn:", (r.stderr or r.stdout)[-400:], flush=True)
    # 4) manifest（指向最新 bundle）+ bundle（数据）
    msrc = os.path.join(DATA, f"manifest_{variant}.json")
    bundle_rel = f"data/{date}_bundle.json"
    if os.path.exists(msrc):
        shutil.copy(msrc, os.path.join(target, "manifest.json"))
        m = json.load(open(msrc, encoding="utf-8"))
        bundle_rel = m.get("bundle", bundle_rel)
        bsrc = os.path.join(DATA, os.path.basename(bundle_rel))
        ddir = os.path.join(target, "data")
        if os.path.isdir(ddir):
            for old in os.listdir(ddir):
                if old.endswith("_bundle.json"):
                    try:
                        os.remove(os.path.join(ddir, old))
                    except OSError:
                        pass
        if os.path.exists(bsrc):
            shutil.copy(bsrc, os.path.join(target, bundle_rel))
    print(f"  [dyn] 已暂存动态页子树 → {target} (bundle: {bundle_rel})", flush=True)


def main():
    # 复用流水线 flock：另一实例在跑时跳过本次（避免并发写 /tmp/cfpub 与部署竞态）
    if fcntl is not None:
        try:
            lf = open(LOCK_FILE, "w")
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(f"⚠ 检测到流水线/部署实例正在运行（{LOCK_FILE} 被占用），本次重发跳过", flush=True)
            return
    print(f"===== 重发布 {DATE}（静态 + 动态页子树） =====", flush=True)

    # 1. 收盘版 → 根
    close_html = os.path.join(BASE, f"A股复盘_{DATE}.html")
    if not os.path.exists(close_html):
        print(f"! 收盘 HTML 不存在：{close_html}", flush=True)
        return
    shutil.copy(close_html, os.path.join(PUB_STOCK, "index.html"))
    shutil.copy(close_html, os.path.join(PUB_STOCK, f"A股复盘_{DATE}.html"))
    print(f"[deploy] 收盘版 → 根 (index.html = {DATE})", flush=True)

    # 2. 午间版 → 午盘/
    mid_html = os.path.join(BASE, f"A股午盘_{DATE}.html")
    out_mid = os.path.join(PUB_STOCK, "午盘")
    os.makedirs(out_mid, exist_ok=True)
    if os.path.exists(mid_html):
        shutil.copy(mid_html, os.path.join(out_mid, "index.html"))
        shutil.copy(mid_html, os.path.join(out_mid, f"A股午盘_{DATE}.html"))
        print(f"[deploy] 午间版 → 午盘/ (index.html = {DATE})", flush=True)

    # 3. 动态页子树（收盘 + 午间）
    stage_dyn(False, DATE)
    if os.path.exists(mid_html):
        stage_dyn(True, DATE)

    # 4. Pages Functions（触发队列 API）
    src_func = os.path.join(BASE, "functions")
    if os.path.isdir(src_func):
        shutil.copytree(src_func, os.path.join(PUB, "functions"), dirs_exist_ok=True)
        print("[deploy] 已同步 functions/", flush=True)

    # 5. 部署
    token, account = load_cloud_env()
    if not token:
        print("⚠ 未配置 CF_TOKEN，跳过部署（本地暂存已完成）", flush=True)
        return
    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CLOUDFLARE_ACCOUNT_ID"] = account
    print("[deploy] 开始 wrangler deploy ...", flush=True)
    if os.path.isfile(WRANGLER_JS):
        deploy_cmd = [NODE_BIN, WRANGLER_JS, "pages", "deploy", PUB,
                      "--project-name=stock-a", "--branch=main", "--commit-dirty=true"]
    else:
        deploy_cmd = ["npx", "wrangler", "pages", "deploy", PUB,
                      "--project-name=stock-a", "--branch=main", "--commit-dirty=true"]
    r = subprocess.run(deploy_cmd, cwd=BASE, env=env, capture_output=True, text=True, timeout=600)
    print(r.stdout[-1500:] if r.stdout else "", flush=True)
    if r.returncode != 0:
        print("DEPLOY FAILED:", r.stderr[-800:], flush=True)
        sys.exit(1)
    print("[deploy] 完成", flush=True)


if __name__ == "__main__":
    main()
