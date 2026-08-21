#!/usr/bin/env python3
# 取「均占系统」(ghxb.site/jzxt) 均线占用率 日线数据，写 data/jzxt_history.json。
# 来源：均占系统 实时/历史接口。均线占用率＝站上对应周期均线的股票占比(%)，是衡量市场宽度/情绪的指标。
#   - 实时：GET /api/admin/tick/realtime（含日内分时序列）
#   - 历史/日线：GET /api/admin/daily/range?from=dxb&marketType=sub&startTime=<ms>&endTime=<ms>
# 鉴权：Authorization: Bearer <token>，token 存于 data/.jzxt_token（或环境变量 JZXT_TOKEN）。
# 本脚本取 daily/range（#/history 页同款数据），拉取最近 ~180 天窗口。
import json, os, sys, datetime, subprocess

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
TOKEN_FILE = os.path.join(DATA, ".jzxt_token")
OUT = os.path.join(DATA, "jzxt_history.json")
HOST = "http://www.ghxb.site"
API = "/api/admin/daily/range"
WINDOW_DAYS = 180

def get_token():
    t = os.environ.get("JZXT_TOKEN")
    if t and t.strip():
        return t.strip()
    if os.path.exists(TOKEN_FILE):
        try:
            return open(TOKEN_FILE, encoding="utf-8").read().strip()
        except Exception:
            return None
    return None

def ms(y, mo, d, h=0, mi=0, se=0):
    dt = datetime.datetime(y, mo, d, h, mi, se,
                           tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    return int(dt.timestamp() * 1000)

def fetch(token):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    start = now - datetime.timedelta(days=WINDOW_DAYS)
    S = ms(start.year, start.month, start.day)
    E = ms(now.year, now.month, now.day, 23, 59, 59)
    url = (f"{HOST}{API}?from=dxb&marketType=sub&startTime={S}&endTime={E}")
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "40",
                            "-H", f"Authorization: Bearer {token}", url],
                           capture_output=True, text=True, timeout=60)
        if not r.stdout.strip():
            return None, "接口返回空"
        j = json.loads(r.stdout)
        if j.get("code") == "0000" and j.get("data"):
            return j["data"], None
        return None, f"接口异常 code={j.get('code')} msg={j.get('message')}"
    except Exception as e:
        return None, f"请求异常：{e}"

def main():
    token = get_token()
    if not token:
        out = {"ok": False, "reason": "缺少 token：请写入 data/.jzxt_token 或设置环境变量 JZXT_TOKEN",
               "updated": datetime.date.today().strftime("%Y-%m-%d")}
        json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)
        print("[jzxt] 缺少 token，已写 ok:false 占位；请在 data/.jzxt_token 放入均占系统 Bearer token 后重试。")
        return
    data, err = fetch(token)
    if err or not data:
        # 失败保护：若已有 ok:true 的历史数据，保留旧文件不覆盖（页面继续显示上一交易日），
        # 仅当无旧数据或旧数据本身是失败占位时才写 ok:false。
        if os.path.exists(OUT):
            try:
                old = json.load(open(OUT, encoding="utf-8"))
                if old.get("ok") and old.get("dates"):
                    print(f"[jzxt] 取数失败（{err}），保留上次数据"
                          f"（截至 {old['dates'][-1]}），不覆盖。")
                    return
            except Exception:
                pass
        out = {"ok": False, "reason": err or "无数据",
               "updated": datetime.date.today().strftime("%Y-%m-%d")}
        json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)
        print(f"[jzxt] 取数失败（{err}），无可用旧数据，已写 ok:false 占位；下次运行自动重试。")
        return
    dates = data.get("dates") or []
    out = {
        "ok": True,
        "marketType": data.get("marketType"),
        "source": "均占系统 ghxb.site/jzxt（/api/admin/daily/range，Bearer 鉴权）",
        "updated": datetime.date.today().strftime("%Y-%m-%d"),
        "dates": dates,
        "cdx": data.get("cdx"), "dx": data.get("dx"),
        "zx": data.get("zx"), "cx": data.get("cx"),
        "kx": data.get("kx"), "mx": data.get("mx"),
    }
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"[jzxt] 已写 {len(dates)} 个交易日 均线占用率，范围 {dates[0]} → {dates[-1]}"
          f"（最新 5/13/50/120 = {out['cdx'][-1]:.2f}/{out['dx'][-1]:.2f}/{out['zx'][-1]:.2f}/{out['cx'][-1]:.2f}）")

if __name__ == "__main__":
    main()
