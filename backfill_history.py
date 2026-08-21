#!/usr/bin/env python3
# 回补历史 hithink.json：
#   涨跌/涨停/跌停/创250日新高新低  -> 腾讯自选股 westock updown (已落盘 _updown_<date>.json)
#   全市场成交额(合计)              -> 东方财富妙想 (已落盘 _raw_mx_breadth.json)
#   8 大宽基指数 60 日收盘          -> westock kline (已落盘 _kline_clean.json)
# 生成 data/YYYY-MM-DD_hithink.json（59 个历史交易日，不含 08-11 实时）。
# 同时把 08-11 实时文件的 indices 扩展为 60 日 hist_close（供 section 二曲线）。
import json, os, datetime

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
LIVE = "2026-08-11"

IDX_NAMES = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
             "sh000688": "科创50", "sh000300": "沪深300", "sh000905": "中证500",
             "sh000852": "中证1000", "sh000016": "上证50"}
WEEK = {"0": "周一", "1": "周二", "2": "周三", "3": "周四", "4": "周五", "5": "周六", "6": "周日"}

def parse_trillion(s):
    s = str(s).strip()
    try:
        if "万亿" in s:
            return round(float(s.replace("万亿", "")) * 10000, 1)
        if "亿" in s:
            return round(float(s.replace("亿", "")), 1)
        return round(float(s), 1)
    except Exception:
        return None

# --- 1. kline (8 indices, chronological 05-19..08-11) ---
kline = json.load(open(os.path.join(DATA, "_kline_clean.json")))
idx_series = {}
for code in IDX_NAMES:
    idx_series[code] = sorted(kline.get(code, []), key=lambda r: r["date"])
name_series = {IDX_NAMES[c]: idx_series[c] for c in IDX_NAMES}

# --- 2. 妙想 breadth ---
mx = json.load(open(os.path.join(DATA, "_raw_mx_breadth.json")))
d0, d1 = mx["data"][0], mx["data"][1]
cols0 = d0["columns"]; items0 = {r[0]: r[1:] for r in d0["items"]}
cols1 = d1["columns"]; items1 = {r[0]: r[1:] for r in d1["items"]}
dates_mx = [c.replace("(日)", "") for c in cols0[1:]]
assert len(dates_mx) == 59, f"妙想日期数异常: {len(dates_mx)}"
mx_map = {}
for i, dt in enumerate(dates_mx):
    mx_map[dt] = {
        "total_turnover_yi": parse_trillion(items0["成交额(合计)"][i]),
        "up": int(items0["上涨家数"][i]), "down": int(items0["下跌家数"][i]),
        "flat": int(items0["平盘家数"][i]),
        "limit_up": int(items1["涨停家数"][i]), "limit_down": int(items1["跌停家数"][i]),
    }

# --- 3. westock updown loader ---
def load_updown(date):
    p = os.path.join(DATA, f"_updown_{date}.json")
    if not os.path.exists(p):
        return None
    arr = json.load(open(p))
    if not isinstance(arr, list) or not arr or "row" not in arr[0]:
        return None  # 错误响应（如代理中断），跳过该日
    row = arr[0]["row"]
    return {
        "up": row["CNT_RED"], "down": row["CNT_GREEN"], "flat": row["CNT_ZERO"],
        "limit_up": row["CNT_REACH_UPLIMIT"], "limit_down": row["CNT_REACH_DNLIMIT"],
        "high_new": row["CNT_HIGH250"], "low_new": row["CNT_LOW250"],
    }

def build_indices(date):
    out = []
    for code, name in IDX_NAMES.items():
        series = idx_series[code]
        window = [r for r in series if r["date"] <= date]
        if not window:
            continue
        closes = [r["close"] for r in window]
        dates_w = [r["date"] for r in window]
        cur = window[-1]; prev = window[-2] if len(window) >= 2 else None
        pct = round((cur["close"] / prev["close"] - 1) * 100, 2) if prev else None
        out.append({
            "code": code, "name": name, "close": cur["close"], "pct": pct,
            "turnover_yi": round(cur["amount"] / 1e8, 1),
            "hist_close": closes, "hist_dates": dates_w,
        })
    return out

# --- 4. 生成历史 hithink.json ---
backfill = json.load(open(os.path.join(DATA, "_backfill_dates.json")))
made = 0
for date in backfill:
    up = load_updown(date)
    if up is None:
        print("SKIP (缺 updown):", date); continue
    mxd = mx_map.get(date, {})
    wd = WEEK[str(datetime.date.fromisoformat(date).weekday())]
    out = {
        "date": date, "weekday": wd,
        "source": "backfill: 腾讯自选股 westock updown(涨跌/涨停/跌停/创250日新高新低) ＋ 东方财富妙想(全市场成交额) ＋ westock kline(指数)",
        "market": {
            "equal_weight_pct": None, "median_pct": None,
            "total_turnover_yi": mxd.get("total_turnover_yi"),
            "up": up["up"], "down": up["down"], "flat": up["flat"],
            "limit_up": up["limit_up"], "limit_down": up["limit_down"],
        },
        "indices": build_indices(date),
        "top_sectors": [], "top_stocks": [],
        "high_new": up["high_new"], "low_new": up["low_new"],
    }
    json.dump(out, open(os.path.join(DATA, f"{date}_hithink.json"), "w"), ensure_ascii=False, indent=1)
    made += 1
print(f"已生成历史 hithink.json: {made} 个")

# --- 5. 把 08-11 实时文件 indices 扩展为 60 日 ---
live = json.load(open(os.path.join(DATA, f"{LIVE}_hithink.json")))
for i in live.get("indices", []):
    series = idx_series.get(i.get("code")) or name_series.get(i.get("name"))
    if not series:
        continue
    window = [r for r in series if r["date"] <= LIVE]
    i["hist_close"] = [r["close"] for r in window]
    i["hist_dates"] = [r["date"] for r in window]
    i["turnover_yi"] = round(window[-1]["amount"] / 1e8, 1)
json.dump(live, open(os.path.join(DATA, f"{LIVE}_hithink.json"), "w"), ensure_ascii=False, indent=1)
print(f"已扩展 {LIVE} indices 为 {len(live['indices'][0]['hist_dates'])} 日窗口")
