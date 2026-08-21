#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_pipeline.py — A股每日复盘「采集 → 渲染 → 发布」同一天流水线。

设计目标（对应决策 B：等待完整同日采集，绝不发布跨天错配的报告）：
  板块三（成交额前10）/ 板块四（主力净流入前10/后10）统一用同花顺 thsdk 90 行业，
  必须与其余板块（hithink 等）在同一天（date=today）采集，render 后才能日期一致。

流程：
  1) 同日采集：hithink（市场宽度/指数/板块成交额）、sectors_ths（三/四统一口径）、
     sector_rps（板块RPS）、wande（平均股价）、build_classify（个股→板块映射，缓存<7天才重建）。
  2) render.py 生成 A股复盘_{date}.html（若 hithink 当日文件缺失则跳过渲染）。
  3) 质量闸门：hithink 市场数据 / sectors_ths 前10 / HTML 生成 全部通过才允许发布。
  4) 发布（token 门槛）：仅当 secrets.env 含非空 CF_TOKEN 才复制到 /tmp/cfpub 并部署。
     无 token 时只生成本地报告，绝不触碰线上站点（安全）。

用法：
  python3 daily_pipeline.py                 # 默认今天
  python3 daily_pipeline.py 2026-08-13     # 指定日期
"""
import os, sys, json, shutil, subprocess, datetime, time
try:
    import fcntl  # Unix 互斥锁
except ImportError:
    fcntl = None

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
PUB = "/tmp/cfpub"
LOCK_FILE = os.path.join(BASE, ".pipeline.lock")  # 互斥锁：防止多个自动化并发跑流水线
PUB_STOCK = os.path.join(PUB, "stock-a")
VENV_PY = "/Users/sugieliao/.workbuddy/binaries/python/envs/default/bin/python"
SYS_PY = "/usr/bin/python3"
SECRETS = os.path.join(BASE, "secrets.env")
DEPLOY = os.path.join(BASE, "deploy_cf.py")
CF_ACCOUNT_DEFAULT = "99acfa35cfa82fb90d916516a1ed0a2e"

# 预装 wrangler 二进制路径（避免 npx 每次临时拉取导致 ENOTEMPTY 竞态）
NODE_BIN = "/Users/sugieliao/.workbuddy/binaries/node/versions/22.22.2/bin/node"
WRANGLER_JS = "/Users/sugieliao/.workbuddy/binaries/node/workspace/node_modules/wrangler/bin/wrangler.js"
# 若预装 wrangler 不可用则 fallback 到 npx
if not os.path.isfile(WRANGLER_JS):
    WRANGLER_JS = None


def run(cmd, label, timeout=600):
    print(f"[run] {label}: {' '.join(cmd)}", flush=True)
    try:
        r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            print(f"  x {label} 失败 (rc={r.returncode})", flush=True)
            print((r.stderr or r.stdout)[-800:], file=sys.stderr, flush=True)
            return False
        print(f"  ok {label} 完成", flush=True)
        return True
    except Exception as e:
        print(f"  x {label} 异常: {e}", flush=True)
        return False


def load_secrets():
    env = {}
    if os.path.exists(SECRETS):
        for line in open(SECRETS, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def stage_dyn(midday, date):
    """动态页（Path A）暂存：把本次渲染产出的 shell + 抽取 JS + bundle + manifest
    写入 stock-a/dyn/（收盘）或 stock-a/dyn/午盘/（午间）。
    页面运行时自行 fetch manifest → bundle 渲染，无需改 HTML；更新只需重新部署小 JSON。
    仅更新当前 variant 子树，另一 variant 子树保留在 /tmp/cfpub 中不被触碰。"""
    variant = "midday" if midday else "close"
    dyn_root = os.path.join(PUB_STOCK, "dyn")
    target = os.path.join(dyn_root, "午盘") if midday else dyn_root
    os.makedirs(os.path.join(target, "data"), exist_ok=True)
    # 1) 外壳 HTML（含 boot 逻辑 + 本地 Chart.js 引用）
    shutil.copy(os.path.join(BASE, "app.html"), os.path.join(target, "index.html"))
    # 2) 自托管 Chart.js（避免 jsdelivr 在中国大陆不稳定）
    web_chart = os.path.join(BASE, "web", "chart.umd.min.js")
    if os.path.exists(web_chart):
        shutil.copy(web_chart, os.path.join(target, "chart.umd.min.js"))
    # 3) 从本次渲染的静态 HTML 抽取图表逻辑 + 控制按钮逻辑
    html_path = os.path.join(BASE, ("A股午盘" if midday else "A股复盘") + f"_{date}.html")
    if os.path.exists(html_path):
        run([SYS_PY, "extract_dyn.py", html_path, target], "extract_dyn_assets")
    # 4) manifest（指向最新 bundle）+ bundle（数据）
    #    bundle 路径从 manifest 读取，兼容带 variant 的文件名，避免硬编码
    msrc = os.path.join(DATA, f"manifest_{variant}.json")
    if os.path.exists(msrc):
        shutil.copy(msrc, os.path.join(target, "manifest.json"))
        m = json.load(open(msrc, encoding="utf-8"))
        bundle_rel = m.get("bundle", f"data/{date}_bundle.json")
        bsrc = os.path.join(DATA, os.path.basename(bundle_rel))
        # 清理目标 data 目录下旧的 bundle，避免同名/旧命名文件残留导致混淆
        ddir = os.path.join(target, "data")
        if os.path.isdir(ddir):
            for old in os.listdir(ddir):
                if old.endswith("_bundle.json"):
                    try: os.remove(os.path.join(ddir, old))
                    except OSError: pass
        if os.path.exists(bsrc):
            shutil.copy(bsrc, os.path.join(target, bundle_rel))
    print(f"  [dyn] 已暂存动态页子树 → {target} (bundle: {bundle_rel})", flush=True)


def acquire_lock():
    """互斥锁：已有实例在跑时返回 None（调用方应跳过本次），否则持有锁返回文件对象。
    用 flock 而非文件存在判断——flock 在进程退出/崩溃后自动释放，不会残留死锁。"""
    if fcntl is None:
        return object()  # 非 Unix 环境退化为无锁（正常不会发生，本机为 macOS）
    try:
        f = open(LOCK_FILE, "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write(str(os.getpid()))
        f.flush()
        return f
    except OSError:
        return None


def main():
    # 互斥锁：同一时刻只允许一个流水线实例（午间版/收盘版/轮询触发 共享同一套 data 与部署目录）
    lock = acquire_lock()
    if lock is None:
        print("⚠ 检测到另一个 daily_pipeline.py 实例正在运行，本次跳过"
              "（避免并发写 data/ 与 wrangler 部署竞态）", flush=True)
        return  # 正常退出（rc=0）：调用方不视为失败，命令留在队列下轮再试
    args = sys.argv[1:]
    no_deploy = "--no-deploy" in args
    if no_deploy:
        args.remove("--no-deploy")
    midday = "--midday" in args
    if midday:
        args.remove("--midday")
    skip_rps = "--skip-rps" in args
    if skip_rps:
        args.remove("--skip-rps")
        print("  [mode] --skip-rps：跳过板块RPS采集（源被限流时，沿用 data/sector_rps.json 现有数据）", flush=True)
    date = args[0] if args else None
    if not date:
        today = datetime.date.today()
        if today.weekday() >= 5:  # Sat=5, Sun=6 → 回退到最近周五
            date = (today - datetime.timedelta(days=today.weekday() - 4)).strftime("%Y-%m-%d")
            print(f"  [weekend] 今天是非交易日，自动使用上一个交易日 {date}", flush=True)
        else:
            date = today.strftime("%Y-%m-%d")
    variant = "午间" if midday else "收盘"
    print(f"===== A股每日复盘流水线[{variant}] {date} =====", flush=True)
    if no_deploy:
        print("  [mode] --no-deploy：仅生成本地报告，绝不发布到 Cloudflare", flush=True)
    if midday:
        print("  [mode] 午间版：渲染 A股午盘_{date}.html，部署到 stock-a/午盘/", flush=True)

    # 1) 同日采集
    run([SYS_PY, "collect_hithink.py", date], "hithink(市场/指数/板块成交额)")
    run([VENV_PY, "collect_sectors_ths.py", date], "sectors_ths(同花顺90行业·三/四统一口径)")  # 关键：同日
    # 板块五 RPS 共振：仅收盘版当日重算；午间版不更新 RPS，沿用上一交易日收盘结果
    if midday:
        print("[skip] 午间版不更新 RPS，沿用上一交易日 sector_rps.json（不运行 collect_sector_rps.py）", flush=True)
    elif skip_rps:
        print("[skip] --skip-rps：不运行 collect_sector_rps.py，沿用现有 sector_rps.json", flush=True)
    else:
        run([VENV_PY, "collect_sector_rps.py"], "sector_rps(板块RPS)")
    run([VENV_PY, "collect_wande.py", date], "wande(平均股价·pytdx)")
    # 均线占用率（均占系统）：午间版/收盘版都尝试刷新；token 过期或接口失败时
    # collect_jzxt.py 保留上一交易日数据不覆盖（页面继续显示旧数据，不显示"暂不可达"）
    run([SYS_PY, "collect_jzxt.py"], "jzxt(均线占用率)")
    # TR情绪监测（通达信扩展数据 38/39/40）：从 Parallels VM 复制扩展数据文件并解析
    run([SYS_PY, "collect_tr_emotion.py"], "tr_emotion(通达信扩展数据·TR情绪监测)")
    # build_classify 仅缓存>7天才重建
    cf = os.path.join(DATA, "stock_classify.json")
    do_classify = True
    if os.path.exists(cf) and (time.time() - os.path.getmtime(cf)) < 7 * 86400:
        do_classify = False
        print("[skip] stock_classify 缓存<7天，跳过 build_classify", flush=True)
    if do_classify:
        run([SYS_PY, "build_classify.py"], "build_classify")

    # 2) 渲染（hithink 当日文件缺失则无法渲染，跳过）
    hithink = os.path.join(DATA, f"{date}_hithink.json")
    base_name = "A股午盘" if midday else "A股复盘"
    html = os.path.join(BASE, f"{base_name}_{date}.html")
    if os.path.exists(hithink):
        rcmd = [SYS_PY, "render.py", date]
        if midday:
            rcmd.append("--midday")
        run(rcmd, "render")
    else:
        print("⚠ 当日 hithink 文件缺失，跳过渲染（其余采集结果保留）", flush=True)

    # 3) 质量闸门
    sth = os.path.join(DATA, f"{date}_sectors_ths.json")
    gates = []
    if os.path.exists(hithink):
        try:
            hj = json.load(open(hithink, encoding="utf-8"))
            gates.append(("hithink市场数据", bool((hj.get("market") or {}).get("total_turnover_yi"))))
        except Exception:
            gates.append(("hithink市场数据", False))
    else:
        gates.append(("hithink文件", False))
    if os.path.exists(sth):
        try:
            sj = json.load(open(sth, encoding="utf-8"))
            gates.append(("sectors_ths前10", len(sj.get("top_sectors") or []) > 0))
        except Exception:
            gates.append(("sectors_ths解析", False))
    else:
        gates.append(("sectors_ths文件", False))
    gates.append(("HTML生成", os.path.exists(html)))
    allok = all(v for _, v in gates)
    for name, v in gates:
        print(f"  [gate] {name}: {'ok' if v else 'x'}", flush=True)
    if not allok:
        print("⚠ 关键数据缺失，跳过发布（报告已生成本地）", flush=True)
        return

    # 4) 发布（仅当配置了 CF_TOKEN 且未指定 --no-deploy）
    if no_deploy:
        print(f"⚠ 指定 --no-deploy，跳过 Cloudflare 发布（仅本地报告）：{html}", flush=True)
        return
    secrets = load_secrets()
    token = secrets.get("CF_TOKEN")
    if not token:
        print(f"⚠ 未配置 CF_TOKEN（secrets.env），跳过 Cloudflare 发布。"
              f"本地报告：{html}", flush=True)
        return
    os.environ["CF_TOKEN"] = token
    os.environ["CF_ACCOUNT"] = secrets.get("CF_ACCOUNT", CF_ACCOUNT_DEFAULT)
    # wrangler 用不同的环境变量名
    os.environ["CLOUDFLARE_API_TOKEN"] = token
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = secrets.get("CF_ACCOUNT", CF_ACCOUNT_DEFAULT)

    # 目标子目录：午间版 → stock-a/午盘/；收盘版 → stock-a/（站点根）
    sub = "午盘" if midday else ""
    out_dir = os.path.join(PUB_STOCK, sub) if sub else PUB_STOCK
    os.makedirs(out_dir, exist_ok=True)
    for f in ("CNAME", ".nojekyll"):
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(PUB, f))
    # Pages Functions（按钮触发队列 API）：部署时一并带上
    src_func = os.path.join(BASE, "functions")
    if os.path.isdir(src_func):
        shutil.copytree(src_func, os.path.join(PUB, "functions"), dirs_exist_ok=True)
        print("  [deploy] 已同步 functions/（触发队列 API）", flush=True)
    # 日期文件 + 该版本自己的 index.html（互不影响）
    shutil.copy(html, os.path.join(out_dir, os.path.basename(html)))
    if sub:
        shutil.copy(html, os.path.join(out_dir, "index.html"))
        print(f"  [deploy] 午间版 → stock-a/午盘/ （{os.path.basename(html)} + index.html）", flush=True)
    else:
        shutil.copy(html, os.path.join(PUB_STOCK, "index.html"))
        print(f"  [deploy] 收盘版 → stock-a/ 根（index.html = 最新日报）", flush=True)
    # 动态页（Path A）：随本次渲染一起暂存 dyn 子树，使页面运行时自行 fetch 最新数据
    stage_dyn(midday, date)
    # 用 wrangler 部署（正确编译 _worker.js 为 Pages Function，Assets API 不会激活 Worker）
    if WRANGLER_JS:
        deploy_cmd = [NODE_BIN, WRANGLER_JS, "pages", "deploy", PUB,
                      "--project-name=stock-a", "--branch=main", "--commit-dirty=true"]
    else:
        deploy_cmd = ["npx", "wrangler", "pages", "deploy", PUB,
                      "--project-name=stock-a", "--branch=main", "--commit-dirty=true"]
    run(deploy_cmd, "cloudflare-deploy(wrangler)")
    print("===== 完成（已发布） =====", flush=True)


if __name__ == "__main__":
    main()
