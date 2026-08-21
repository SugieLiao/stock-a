#!/usr/bin/env python3
# 同花顺(hithink-finance / fuyao) REST 数据采集：A股每日复盘所需全部同花顺侧数据。
# 输出 /Users/sugieliao/WorkBuddy/A股每日复盘/data/YYYY-MM-DD_hithink.json
# 新高新低(high_new/low_new) 与 资金流向(fund_flow) 留 null，由自动化用 westock 补。
# Key 从 ~/.workbuddy/hithink_finance_key 读取（600 权限，不进代码/日志）。
import json, subprocess, sys, os, time, datetime

BASE = "https://fuyao.aicubes.cn"
KEYFILE = "/Users/sugieliao/.workbuddy/hithink_finance_key"
OUTDIR = "/Users/sugieliao/WorkBuddy/A股每日复盘/data"
NAMEMAP = "/Users/sugieliao/WorkBuddy/A股每日复盘/name_map.json"

INDICES = [
    ("000001.SH", "上证指数"), ("399001.SZ", "深证成指"), ("399006.SZ", "创业板指"),
    ("000688.SH", "科创50"), ("000300.SH", "沪深300"), ("000905.SH", "中证500"),
    ("000852.SH", "中证1000"), ("000016.SH", "上证50"),
]
# 风格指数（短线风格/情绪）：同花顺特色指数 tszs，与宽基指数同源（hithink）
# 目录 tag=tszs 可查全部（883xxx.TI）。北证50（899050）不在其中，source=tencent 走腾讯行情。
# 顺序即页面展示顺序：全A → 创历史新高 → 昨日成交前10 → 微盘股 → 北证50 → 北交所昨日涨停 → 昨日涨停
STYLE_INDICES = [
    ("883957.TI", "全A（沪深京）", "hithink"),
    ("883911.TI", "创历史新高", "hithink"),
    ("883902.TI", "昨日成交前10", "hithink"),
    ("883418.TI", "微盘股", "hithink"),
    ("899050", "北证50", "tencent"),
    ("883422.TI", "北交所昨日涨停", "hithink"),
    ("883900.TI", "昨日涨停", "hithink"),
]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def get_key():
    return open(KEYFILE).read().strip()

def apiget(path, params=""):
    url = BASE + path + (("?" + params) if params else "")
    out = subprocess.run(["curl", "-s", "--max-time", "40", url, "-H", f"X-api-key: {KEY}"],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return {"code": -1, "message": "JSON解析失败", "_raw": out[:200]}

def load_name_map():
    # 缓存全量名称映射（约5550只，3页），2天以上重建
    need = True
    if os.path.exists(NAMEMAP):
        age = time.time() - os.path.getmtime(NAMEMAP)
        if age < 2 * 86400:
            need = False
    if not need:
        return json.load(open(NAMEMAP))
    m = {}
    for off in (0, 2000, 4000, 6000):
        d = apiget("/api/meta/tickers/list", f"asset_type=a-share&limit=2000&offset={off}")
        if d.get("code") != 0:
            break
        for it in d["data"]["item"]:
            m[it["thscode"]] = it.get("name", it["thscode"])
        if len(d["data"]["item"]) < 2000:
            break
    json.dump(m, open(NAMEMAP, "w"), ensure_ascii=False)
    return m

def collect_market(nm, date):
    # 全市场快照：全A等权 / 总成交额 / 涨跌家数 / 涨停跌停 / 前100个股 / 涨跌停个股清单
    pcts, turns = [], []
    up = down = flat = lu = ld = 0
    stocks = []
    lu_list = []   # (code, pct, turnover)
    ld_list = []
    off = 0
    while True:
        d = apiget("/api/a-share/prices/snapshot", f"limit=2000&offset={off}")
        if d.get("code") != 0:
            fb = collect_market_fallback_eastmoney(date)
            if fb is not None:
                return fb
            return {"error": f"snapshot code={d.get('code')} msg={d.get('message')}"}
        items = d["data"]["item"]
        for it in items:
            p = it.get("price_change_ratio_pct")
            tv = it.get("turnover")
            if p is None or tv is None:
                continue
            pcts.append(p)
            turns.append(tv)
            if p > 0: up += 1
            elif p < 0: down += 1
            else: flat += 1
            if p >= 9.9: lu += 1
            if p <= -9.9: ld += 1
            stocks.append((it["thscode"], tv, p))
            if p >= 9.9: lu_list.append((it["thscode"], p, tv))
            if p <= -9.9: ld_list.append((it["thscode"], p, tv))
        if len(items) < 2000:
            break
        off += 2000
    n = len(pcts)
    pcts.sort()
    mid = n // 2
    median = pcts[mid] if n % 2 == 1 else (pcts[mid - 1] + pcts[mid]) / 2
    equal_w = sum(pcts) / n
    total_turn_yi = sum(turns) / 1e8
    stocks.sort(key=lambda x: x[1], reverse=True)
    top100 = [{"code": s[0], "name": nm.get(s[0], s[0]), "turnover_yi": round(s[1] / 1e8, 2), "pct": round(s[2], 2)} for s in stocks[:100]]
    # 涨跌停清单按成交额降序
    lu_list.sort(key=lambda x: x[2], reverse=True)
    ld_list.sort(key=lambda x: x[2], reverse=True)
    lu_out = [{"code": c, "name": nm.get(c, c), "pct": round(p, 2), "turnover_yi": round(tv / 1e8, 2)} for c, p, tv in lu_list]
    ld_out = [{"code": c, "name": nm.get(c, c), "pct": round(p, 2), "turnover_yi": round(tv / 1e8, 2)} for c, p, tv in ld_list]
    return {
        "equal_weight_pct": round(equal_w, 4),
        "median_pct": round(median, 4),
        "total_turnover_yi": round(total_turn_yi, 1),
        "total_stocks": n,
        "up": up, "down": down, "flat": flat, "limit_up": lu, "limit_down": ld,
        "top_stocks": top100,
        "limit_up_list": lu_out,
        "limit_down_list": ld_out,
    }

def collect_market_fallback_eastmoney(date):
    """hithink 快照失败时的兜底：东方财富 push2ex(涨跌分布/涨停池/跌停池) + push2(指数成交额)。
    全部免 key REST（脚本可直调，无需 agent/MCP）。push2ex 的 date 参数被忽略、永远返回当日，
    故仅用于「当日采集时 hithink 挂掉」的场景；历史缺口由 render.py 的 {dt}_westock.json 兜底链负责。
    返回与 collect_market() 相同结构的 market dict；关键字段缺失时返回 None（由上层保留原始错误）。
    """
    import urllib.request
    UT = "7eea3edcaed734bea9cbfc24409ed989"  # 东财通用公共 ut（与 collect_sector_rps.py 同源）
    def get(url):
        # 用 curl subprocess（与 apiget 同款）：push2 对 urllib 偶发断开，curl 更稳；失败重试 2 次
        for _ in range(3):
            try:
                out = subprocess.run(["curl", "-s", "--max-time", "15",
                                      "-H", "User-Agent: Mozilla/5.0",
                                      "-H", "Referer: https://quote.eastmoney.com/", url],
                                     capture_output=True, text=True, timeout=20).stdout
                return json.loads(out)
            except Exception:
                continue
        return {}
    # 1) 涨跌分布：band 正=上涨、负=下跌、0=平；band 求和=参与统计的股票总数
    d = get(f"https://push2ex.eastmoney.com/getTopicZDFenBu?ut={UT}&dpt=wz.ztzt")
    fenbu = ((d.get("data") or {}).get("fenbu")) or []
    up = down = flat = total = 0
    for item in fenbu:
        for k, v in item.items():
            ki = int(k)
            total += v
            if ki > 0: up += v
            elif ki < 0: down += v
            else: flat += v
    if not fenbu:
        return None
    # 2) 涨停/跌停家数：官方涨停池/跌停池 tc（东财口径「触及涨停/跌停」）；池接口失败时用 fenbu 的 11/-11 档粗估
    ymd = date.replace("-", "")
    lu = ld = None
    zp = get(f"https://push2ex.eastmoney.com/getTopicZTPool?ut={UT}&dpt=wz.ztzt&Pageindex=0&pagesize=1&sort=fbt%3Aasc&date={ymd}")
    ztc = ((zp.get("data") or {}).get("tc"))
    if ztc is not None:
        lu = ztc
    dp = get(f"https://push2ex.eastmoney.com/getTopicDTPool?ut={UT}&dpt=wz.ztzt&Pageindex=0&pagesize=1&sort=fund%3Aasc&date={ymd}")
    dtc = ((dp.get("data") or {}).get("tc"))
    if dtc is not None:
        ld = dtc
    band11 = sum(v for item in fenbu for k, v in item.items() if int(k) == 11)
    band_11 = sum(v for item in fenbu for k, v in item.items() if int(k) == -11)
    if lu is None:
        lu = band11
    if ld is None:
        ld = band_11
    # 3) 全市场成交额 = 上证综指 + 深证综指 + 北证50（万元→亿）
    #    主：腾讯行情 qt.gtimg.cn（本文件 fetch_bj50 同源，稳定免 key）；备：东财 push2 ulist（偶发限流）
    turn = None
    try:
        req = urllib.request.Request("https://qt.gtimg.cn/q=sh000001,sz399106,bj899050",
                                     headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=15).read().decode("gbk", errors="ignore")
        wan = 0.0
        for line in raw.strip().split(";"):
            if "=" not in line:
                continue
            p = line.split('"')[1].split("~")
            if len(p) > 37 and p[37]:
                wan += float(p[37])
        if wan:
            turn = round(wan / 1e4, 1)  # 万→亿
    except Exception:
        pass
    if turn is None:
        tu = get("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=1.000001,0.399106,0.899050&fields=f6")
        diff = ((tu.get("data") or {}).get("diff")) or []
        if len(diff) == 3:
            turn = round(sum(float(x.get("f6") or 0) for x in diff) / 1e8, 1)
    if turn is None:
        return None
    return {
        "equal_weight_pct": None, "median_pct": None,
        "total_turnover_yi": turn, "total_stocks": total,
        "up": up, "down": down, "flat": flat,
        "limit_up": lu, "limit_down": ld,
        "top_stocks": [], "limit_up_list": [], "limit_down_list": [],
        "source_fallback": "hithink 快照失败兜底: 东财 push2ex 涨跌分布/涨停跌停池 + 腾讯gtimg成交额 (仅当日)",
    }


def collect_indices():
    # 今日快照 + 近 60 交易日历史(指数曲线固定 60 日窗口)
    codes = ",".join(c for c, _ in INDICES)
    d = apiget("/api/a-share-index/prices/snapshot", f"thscodes={codes}")
    snap = {}
    if d.get("code") == 0:
        for it in d["data"]["item"]:
            snap[it["thscode"]] = it
    end = int(time.time() * 1000)
    start = end - 110 * 86400 * 1000  # ~70 交易日，下面裁到 60
    out = []
    for code, name in INDICES:
        it = snap.get(code, {})
        # 历史
        hd = apiget("/api/a-share-index/prices/historical",
                   f"thscode={code}&interval=1d&start={start}&end={end}")
        dates, closes = [], []
        if hd.get("code") == 0:
            for b in hd["data"]["item"]:
                dt = datetime.datetime.fromtimestamp(b["date_ms"] / 1000).strftime("%Y-%m-%d")
                dates.append(dt)
                closes.append(round(b.get("close_price", 0), 2))
        if len(dates) > 60:  # 裁到最近 60 交易日
            dates, closes = dates[-60:], closes[-60:]
        out.append({
            "code": code, "name": name,
            "close": round(it.get("last_price", 0), 2),
            "pct": round(it.get("price_change_ratio_pct", 0), 4) if it.get("price_change_ratio_pct") is not None else None,
            "turnover_yi": round((it.get("turnover") or 0) / 1e8, 1),
            "hist_dates": dates, "hist_close": closes,
        })
    return out

def fetch_bj50():
    # 北证50（899050）：hithink 指数接口不支持，走腾讯行情（qt.gtimg.cn，GBK，无需 key）。
    # 字段：p[3]=收盘价 p[31]=涨跌额 p[32]=涨跌幅% p[30]=行情时间
    import urllib.request
    try:
        req = urllib.request.Request("https://qt.gtimg.cn/q=bj899050",
                                     headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=15).read().decode("gbk", errors="ignore")
        p = raw.split("~")
        return {"name": "北证50", "code": "899050",
                "close": round(float(p[3]), 2), "pct": round(float(p[32]), 2),
                "source": "腾讯行情", "ts": p[30] if len(p) > 30 else ""}
    except Exception as e:
        return {"name": "北证50", "code": "899050", "close": None, "pct": None,
                "source": "腾讯行情", "error": str(e)}

def fetch_bj50_hist(days=70):
    # 北证50（899050）历史日线：新浪 CN_MarketDataService。
    # 腾讯 fqkline 对北证指数只回当日 1 条、hithink 不支持 899050，故走新浪。
    # 返回 (dates, closes) 各 ≤60 条；失败返回 ([], [])（曲线自动跳过该指数）。
    import urllib.request, re
    url = (f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_bj899050=/"
           f"CN_MarketDataService.getKLineData?symbol=bj899050&scale=240&ma=no&datalen={days}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                   "Referer": "https://finance.sina.com.cn"})
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        m = re.search(r"\((\[.*\])\)", raw, re.S)
        arr = json.loads(m.group(1)) if m else []
        dates = [r["day"] for r in arr]
        closes = [round(float(r["close"]), 2) for r in arr]
        if len(dates) > 60:  # 裁到最近 60 交易日
            dates, closes = dates[-60:], closes[-60:]
        return dates, closes
    except Exception:
        return [], []


def collect_styles():
    # 风格指数：hithink tszs 特色指数快照 + 北证50（腾讯行情）+ 近 60 交易日历史（曲线）
    codes = ",".join(c for c, _, _ in STYLE_INDICES if c != "899050")
    d = apiget("/api/a-share-index/prices/snapshot", f"thscodes={codes}")
    by_code = {}
    if d.get("code") == 0:
        for it in d["data"]["item"]:
            by_code[it["thscode"]] = it
    bj50 = fetch_bj50()
    end = int(time.time() * 1000)
    start = end - 110 * 86400 * 1000  # ~70 交易日，下面裁到 60
    out = []
    for code, name, source in STYLE_INDICES:
        if source == "tencent":
            it = bj50
            dates, closes = fetch_bj50_hist()
        else:
            it = by_code.get(code, {})
            # 历史（与宽基指数同一接口/窗口，保证曲线同源可比）
            hd = apiget("/api/a-share-index/prices/historical",
                       f"thscode={code}&interval=1d&start={start}&end={end}")
            dates, closes = [], []
            if hd.get("code") == 0:
                for b in hd["data"]["item"]:
                    dt = datetime.datetime.fromtimestamp(b["date_ms"] / 1000).strftime("%Y-%m-%d")
                    dates.append(dt)
                    closes.append(round(b.get("close_price", 0), 2))
            if len(dates) > 60:  # 裁到最近 60 交易日
                dates, closes = dates[-60:], closes[-60:]
        out.append({
            "name": name, "code": code, "source": "腾讯行情" if source == "tencent" else "hithink tszs",
            "close": round(it.get("last_price", 0), 2) if it.get("last_price") is not None
                     else (it.get("close") if source == "tencent" else None),
            "pct": round(it["price_change_ratio_pct"], 2) if it.get("price_change_ratio_pct") is not None
                   else (it.get("pct") if source == "tencent" else None),
            "error": it.get("error") if source == "tencent" else None,
            "hist_dates": dates, "hist_close": closes,
        })
    return out


def collect_sectors():
    # 行业板块(320) → 分批快照 → 按成交额排序取前10
    cat = apiget("/api/a-share-index/catalog/ths-index-list", "tag=industry")
    if cat.get("code") != 0:
        return {"error": f"catalog code={cat.get('code')}"}
    items = cat["data"]["item"]
    name_of = {i["thscode"]: i["name"] for i in items}
    codes = [i["thscode"] for i in items]
    rows = []
    for i in range(0, len(codes), 50):
        chunk = ",".join(codes[i:i + 50])
        d = apiget("/api/a-share-index/prices/snapshot", f"thscodes={chunk}")
        if d.get("code") != 0:
            continue
        for it in d["data"]["item"]:
            tv = it.get("turnover")
            if tv is None:
                continue
            rows.append({"name": name_of.get(it["thscode"], it["thscode"]),
                         "turnover_yi": round(tv / 1e8, 1),
                         "pct": round(it["price_change_ratio_pct"], 2) if it.get("price_change_ratio_pct") is not None else None})
    rows.sort(key=lambda x: x["turnover_yi"], reverse=True)
    return rows[:10]

def main():
    global KEY
    KEY = get_key()
    os.makedirs(OUTDIR, exist_ok=True)
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
    wd = WEEKDAYS[datetime.date.fromisoformat(date).weekday()]
    nm = load_name_map()
    result = {"date": date, "weekday": wd, "source": "同花顺 hithink-finance",
              "high_new": None, "low_new": None, "fund_flow": {"top": [], "bottom": []}}
    print("采集市场宽度/前50个股...", file=sys.stderr)
    result["market"] = collect_market(nm, date)
    print("采集宽基指数...", file=sys.stderr)
    result["indices"] = collect_indices()
    print("采集风格指数（tszs 特色指数 + 北证50）...", file=sys.stderr)
    result["style_indices"] = collect_styles()
    print("采集行业板块成交额...", file=sys.stderr)
    result["top_sectors"] = collect_sectors()
    path = os.path.join(OUTDIR, f"{date}_hithink.json")
    json.dump(result, open(path, "w"), ensure_ascii=False, indent=2)
    print("已写出", path, file=sys.stderr)

if __name__ == "__main__":
    main()
