#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_sector_rps.py — 计算全市场板块的 5/10/20/50 日 RPS，筛出强共振板块。

RPS（相对价格强度，欧奈尔定义）:
    RPS(周期N) = (1 - 板块N日涨幅在全市场板块中的排名 ÷ 板块总数) × 100
即：板块N日涨幅超过了多少百分比的板块。值越高＝越强。

数据来源（2026-08-21 起：去掉东方财富，改用 TDX 主源 + 同花顺备用源）：
    主源 1：通达信 TDX（pytdx 直连公共行情服务器，无鉴权）
            概念板块指数 881xxx 的日K（get_index_bars，命令 0x8c，前复权）。
            板块名从 TDX get_security_list(1, start) 全量 88xxx 列表获取；
            服务器缺失的（如 881019=化纤）由 data/tdx_concept_names_patch.json 补充表兜底。
    备用源 2：同花顺 THS（AKShare 封装 + 官网 line 接口，无鉴权）
            概念板块列表 stock_board_concept_name_ths()（{名称: code}），
            详情页 q.10jqka.com.cn/gn/detail/code/{code} 取 clid，
            d.10jqka.com.cn/v4/line/bk_{clid}/01/{year}.js 取当年日K。
            东财被封时同花顺官网是已验证的替代方案（见 china-stock-data skill）。
    弃用：东方财富 push2/push2his（2026-08-21 起对当前 IP 全面封锁，且用户要求不再使用）。

板块范围（默认概念板块，让市场自己走出来；不预设名单）：
    RPS_UNIVERSE=concept   仅概念板块（TDX 881xxx 全枚举）—— 默认
    RPS_UNIVERSE=watchlist 自选板块：data/sector_watchlist.txt（每行一个板块名，如「半导体」）
                           —— 仅当你自己有固定观察池时再用，默认不用
    （TDX 主源只支持概念板块 881xxx；industry/all 已不再支持，因东财板块列表已弃用）

流动性预筛选（在「拉日K 算 RPS」之前，先从板块列表里剔除低成交板块）：
    目的：① 聚焦有真实成交参与的板块，本就是更值得看的「市场状态」。
    开关/参数（环境变量）：
        PRE_FILTER=0            关闭预筛选（拉全部概念板块日K，请求最多）
        PRE_FILTER_KEEP=0.65    按「成交额」降序，保留前 65%（默认）
        PRE_FILTER_MIN=150      即便比例算出来很少，也至少保留 150 个（保底）
    注意：RPS 是在【预筛选后的板块集合】内排名的，等于「在流动性够好的概念板块里，
          谁的相对强度最高」——强板块照样会自己走出来，只是分母不含死水板块。
筛选条件：5/10/20/50 日 RPS 中，至少 3 个 > THRESHOLD(默认87)。

输出：data/sector_rps.json
    {
      ok, date, periods:[5,10,20,50], threshold, min_pass,
      universe, universe_label,
      total_boards, n_passed,
      passed:[ {code,name,rps5,rps10,rps20,rps50,n_pass,close,ret5,ret10,ret20,ret50} ]
    }
失败/无数据写 ok:false，render 显示占位，下次自动重试。

用法：
    python3 collect_sector_rps.py                       # 默认：TDX 概念板块 + 流动性预筛（失败自动切同花顺）
    RPS_SOURCE=ths python3 collect_sector_rps.py        # 强制用同花顺备用源
    RPS_SOURCE=tdx python3 collect_sector_rps.py        # 强制用 TDX 主源
    RPS_UNIVERSE=watchlist python3 collect_sector_rps.py# 自选板块(data/sector_watchlist.txt)
    SAMPLE=20 python3 collect_sector_rps.py             # 仅前20个板块（调试）
"""
import json
import os
import sys
import time
import re
import random
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "sector_rps.json")

PERIODS = [5, 10, 20, 50]
THRESHOLD = 87.0
MIN_PASS = 3
NEED_BARS = max(PERIODS) + 1      # 至少需要 51 根日线才能算 50 日收益

# ---- 板块宇宙（默认概念板块，不预设名单，让市场自己走出来）----
# 取值（环境变量 RPS_UNIVERSE 可覆盖）：concept / watchlist
UNIVERSE = os.environ.get("RPS_UNIVERSE", "concept").lower()

# ---- 流动性预筛选（拉日K 之前，先按成交额剔除低成交板块，聚焦真实市场）----
PRE_FILTER = os.environ.get("PRE_FILTER", "1") != "0"
PRE_FILTER_KEEP = float(os.environ.get("PRE_FILTER_KEEP", "0.65"))   # 保留成交额前 65%
PRE_FILTER_MIN = int(os.environ.get("PRE_FILTER_MIN", "150"))        # 保底至少保留 150 个

WATCHLIST_FILE = os.path.join(BASE, "data", "sector_watchlist.txt")

# ---- 双源容错：通达信 TDX(主, 概念板块指数 881xxx 日K) + 同花顺 THS(备, 官网 line 接口) ----
# RPS_SOURCE: auto(默认, TDX 失败自动切 THS) / tdx(强制 TDX) / ths(强制同花顺)
RPS_SOURCE = os.environ.get("RPS_SOURCE", "auto").lower()
# TDX 公共行情服务器（沙箱可直连的其中之一）
TDX_HOSTS = [
    ("115.238.90.165", 7709),
    ("119.147.212.81", 7709),
    ("124.74.236.94", 7709),
    ("180.153.39.20", 7709),
    ("218.108.98.18", 7709),
]
TDX_MARKET = 1                 # 概念板块指数(881xxx) 在 TDX 的 market
TDX_CONCEPT_START = 881000     # 概念板块指数代码区间（通达信约定）
TDX_CONCEPT_END = 882000
NAME_CACHE_FILE = os.path.join(BASE, "data", "tdx_concept_names.json")
# 补充名称表：TDX 公共服务器 get_security_list 只返回部分 881xxx 名称（如缺 881019 化纤），
# 人工核验的公开对照表（data/tdx_concept_names_patch.json）兜底。解析顺序：
# 实时 get_security_list > 名称缓存 > 补充名称表 > code 兜底。
NAME_PATCH_FILE = os.path.join(BASE, "data", "tdx_concept_names_patch.json")
THS_CLID_CACHE_FILE = os.path.join(BASE, "data", "ths_clid_cache.json")

UNIVERSE_LABELS = {
    "concept": "概念板块",
    "watchlist": "自选板块",
}

THS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36")


def load_watchlist_names():
    """读取 data/sector_watchlist.txt：每行一个板块名（# 开头为注释）。"""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    out = []
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.append(line)
    return out


def liquidity_prefilter(boards):
    """boards: [(cat, code, name, amount), ...]。按成交额降序保留前 PRE_FILTER_KEEP，
    至少保留 PRE_FILTER_MIN 个。返回筛选后的列表（含 amount）。"""
    valid = [b for b in boards if b[3] is not None]
    if not valid:
        return boards
    valid.sort(key=lambda b: (b[3] or 0), reverse=True)
    keep_n = max(PRE_FILTER_MIN, int(round(len(valid) * PRE_FILTER_KEEP)))
    kept = valid[:keep_n]
    dropped = len(boards) - len(kept)
    print(f"[sector_rps] 流动性预筛选：{len(boards)} -> {len(kept)} "
          f"(保留成交额前 {PRE_FILTER_KEEP*100:.0f}%，剔除 {dropped} 个低成交板块)")
    return kept


def compute_returns(closes):
    """返回 {5:ret,10:ret,20:ret,50:ret}；不足长度返回 None。"""
    out = {}
    L = len(closes)
    for n in PERIODS:
        if L > n:
            out[n] = closes[-1] / closes[-1 - n] - 1.0
        else:
            out[n] = None
    return out


def rps_from_returns(all_rets):
    """
    all_rets: list of dict {code,name,rets:{5:..,10:..,20:..,50:..}}
    对每个周期，按涨幅降序排名，RPS=(1-rank/N)*100。
    返回 {code: {5:rps,10:rps,20:rps,50:rps}}
    """
    result = {}
    for n in PERIODS:
        # 收集该周期有数据的板块
        pairs = [(b["code"], b["name"], b["rets"][n]) for b in all_rets if b["rets"].get(n) is not None]
        N = len(pairs)
        if N == 0:
            continue
        pairs.sort(key=lambda x: x[2], reverse=True)
        # 排名（1-based，ties 同排名）
        ranked = []
        prev_ret = None
        for i, (code, name, ret) in enumerate(pairs):
            rank = i + 1 if ret != prev_ret else ranked[-1][0]
            ranked.append((rank, code, name, ret))
            prev_ret = ret
        for rank, code, name, ret in ranked:
            result.setdefault(code, {})[n] = round((1.0 - rank / N) * 100, 2)
    return result


# ---------- 板块名缓存（TDX 公共服务器 get_security_list 全量 88xxx，跑一次即全量缓存）----------
def load_name_cache():
    if not os.path.exists(NAME_CACHE_FILE):
        return {}
    try:
        return json.load(open(NAME_CACHE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_name_cache(all_rets):
    """把本次拿到的真实板块名（name != code）写进缓存，供后续复用。"""
    cache = load_name_cache()
    added = 0
    for b in all_rets:
        if b.get("name") and b["name"] != b["code"]:
            if cache.get(b["code"]) != b["name"]:
                cache[b["code"]] = b["name"]
                added += 1
    if added:
        json.dump(cache, open(NAME_CACHE_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"[sector_rps] 名称缓存更新 +{added} -> {NAME_CACHE_FILE}")


def load_name_patch():
    """补充名称表（人工核验的公开对照表），见 NAME_PATCH_FILE。"""
    if not os.path.exists(NAME_PATCH_FILE):
        return {}
    try:
        return json.load(open(NAME_PATCH_FILE, encoding="utf-8"))
    except Exception:
        return {}


# ---------- 通达信 TDX 主源 ----------
def connect_tdx():
    try:
        from pytdx.hq import TdxHq_API
    except Exception as e:
        print(f"[sector_rps] pytdx 不可用：{e}")
        return None
    api = TdxHq_API(multithread=False)
    for h, p in TDX_HOSTS:
        try:
            if api.connect(h, p, time_out=6):
                print(f"[sector_rps] TDX 已连接 {h}:{p}")
                return api
        except Exception:
            continue
    print("[sector_rps] TDX 所有服务器均不可达")
    return None


def tdx_security_names(api):
    """全量拉取 TDX 88xxx 名称（不提前 break）：概念板块 881xxx 分散在 0..21000 列表区间，
    过早 break 会漏掉后半段名称，导致大量板块名 fallback 成代码。"""
    names = {}
    try:
        for start in range(0, 21000, 1000):
            lst = api.get_security_list(1, start)
            if not lst:
                continue
            hits = [x for x in lst if x.get('code', '').startswith('88')]
            for x in hits:
                names[x['code']] = x['name']
        print(f"[sector_rps] TDX 名称列表: {len(names)} 个 88xxx")
    except Exception as e:
        print(f"[sector_rps] TDX 名称列表获取失败: {e}")
    return names


def collect_via_tdx():
    """枚举概念板块指数(881xxx)，批量取日K，算收益。返回 all_rets 或 None。
    板块名优先通过 TDX get_security_list(1, start) 获取；名称缓存兜底。

    关键坑：概念板块指数是『指数』，必须用 get_index_bars（命令 0x8c）取日K；
    用 get_security_bars（命令 0x81，股票口径）取会返回错乱的垃圾数据
    （负数收盘、年份 296275、amount 数量级 e±90 等），据此算出的 RPS 全错。
    """
    api = connect_tdx()
    if not api:
        return None
    tdx_names = tdx_security_names(api)
    sample = int(os.environ.get("SAMPLE", "0") or 0)
    print(f"[sector_rps] TDX 枚举概念板块({TDX_CONCEPT_START}..{TDX_CONCEPT_END}) ...")
    boards = []  # (cat, code, name, amount, closes, dates)
    for code in range(TDX_CONCEPT_START, TDX_CONCEPT_END):
        c = f"{code}"
        try:
            # 指数专用命令（区别于股票的 get_security_bars）
            bars = api.get_index_bars(4, TDX_MARKET, c, 0, NEED_BARS + 5)
        except Exception:
            bars = None
        if not bars or len(bars) < NEED_BARS:
            continue
        try:
            closes = [float(b["close"]) for b in bars]
            dates = [b["datetime"][:10] for b in bars]
            amts = [float(b["amount"]) for b in bars if b.get("amount")]
        except (ValueError, KeyError, TypeError):
            continue
        avg_amt = (sum(amts[-20:]) / len(amts[-20:])) if amts else 0.0
        name = tdx_names.get(c, c)  # 优先用 TDX 名称，fallback 到 code
        boards.append(("概念", c, name, avg_amt, closes, dates))
        if sample and len(boards) >= sample:
            break
    api.disconnect()
    print(f"[sector_rps] TDX 枚举完成：有效概念板块 {len(boards)} 个")
    if not boards:
        return None
    # 流动性预筛选（按成交额）
    if PRE_FILTER:
        tuples = [(b[0], b[1], b[2], b[3]) for b in boards]
        kept = liquidity_prefilter(tuples)
        keep_codes = {t[1] for t in kept}
        boards = [b for b in boards if b[1] in keep_codes]
    # 计算收益
    all_rets = []
    for cat, code, name, amt, closes, dates in boards:
        rets = compute_returns(closes)
        if any(v is not None for v in rets.values()):
            all_rets.append({"code": code, "name": name, "cat": cat,
                             "rets": rets, "close": closes[-1], "date": dates[-1],
                             "dates": dates, "closes": closes})
    if not all_rets:
        return None
    return all_rets


# ---------- 同花顺 THS 备用源 ----------
def load_ths_clid_cache():
    if not os.path.exists(THS_CLID_CACHE_FILE):
        return {}
    try:
        return json.load(open(THS_CLID_CACHE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_ths_clid_cache(cache):
    json.dump(cache, open(THS_CLID_CACHE_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def ths_fetch_clid(session, code):
    """同花顺板块详情页取 clid（line 接口的真实板块代码，≠ 列表 code）。"""
    url = f"https://q.10jqka.com.cn/gn/detail/code/{code}"
    try:
        r = session.get(url, timeout=10)
        m = re.search(r'id="clid"\s+value="(\d+)"', r.text)
        if m:
            return m.group(1)
        # 兜底：BeautifulSoup 解析
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, features="lxml")
        inp = soup.find(name="input", attrs={"id": "clid"})
        return inp["value"] if inp else None
    except Exception as e:
        print(f"  clid 获取失败 {code}: {e}")
        return None


def ths_fetch_line(session, clid, year):
    """同花顺板块当年日K（JSONP 包装）。返回 (dates, closes, amts) 或 None。"""
    url = f"https://d.10jqka.com.cn/v4/line/bk_{clid}/01/{year}.js"
    try:
        r = session.get(url, timeout=10)
        m = re.search(r"\(\s*(\{.*\})\s*\)", r.text, re.S)
        if not m:
            return None
        data = json.loads(m.group(1)).get("data", "")
        rows = [x.split(",") for x in data.split(";") if x]
        if not rows:
            return None
        dates = [x[0] for x in rows]
        closes = [float(x[4]) for x in rows]   # 5 字段 = 收盘价
        amts = [float(x[6]) for x in rows]     # 7 字段 = 成交额
        return dates, closes, amts
    except Exception as e:
        print(f"  line 获取失败 {clid}/{year}: {e}")
        return None


def collect_via_ths():
    """备用源：同花顺概念板块历史日K（AKShare 名称列表 + 官网 line 接口，非东财）。
    链路：stock_board_concept_name_ths() 拿 {名称: code}
        -> 详情页 q.10jqka.com.cn/gn/detail/code/{code} 拿 clid（缓存）
        -> d.10jqka.com.cn/v4/line/bk_{clid}/01/{year}.js 拿当年日K（无鉴权）
    返回 all_rets 或 None。
    """
    try:
        import akshare as ak
        import requests
        from akshare.stock_feature.stock_board_concept_ths import _get_stock_board_concept_name_ths
    except Exception as e:
        print(f"[sector_rps] akshare/requests 不可用：{e}")
        return None
    sample = int(os.environ.get("SAMPLE", "0") or 0)
    try:
        name_code = _get_stock_board_concept_name_ths()   # {名称: code}，lru_cache 进程内一次
    except Exception as e:
        print(f"[sector_rps] THS 名称列表获取失败：{e}")
        return None
    print(f"[sector_rps] THS 概念板块 {len(name_code)} 个")
    if sample:
        name_code = dict(list(name_code.items())[:sample])

    session = requests.Session()
    session.headers.update({"User-Agent": THS_UA})
    clid_cache = load_ths_clid_cache()
    cur_year = datetime.now().year
    prev_year = cur_year - 1
    boards = []   # (cat, code, name, amount, closes, dates)
    for i, (name, code) in enumerate(name_code.items()):
        clid = clid_cache.get(name) or clid_cache.get(code)
        if not clid:
            clid = ths_fetch_clid(session, code)
            if clid:
                clid_cache[name] = clid
        if not clid:
            print(f"  skip {name}: 无 clid")
            continue
        # 去年 + 今年两份 line，按时间合并（去年在前）
        all_dates, all_closes, all_amts = [], [], []
        for y in (prev_year, cur_year):
            got = ths_fetch_line(session, clid, y)
            if got:
                d, c, a = got
                if not all_dates or (d and d[0] > all_dates[-1]):
                    all_dates += d; all_closes += c; all_amts += a
        if len(all_closes) < NEED_BARS:
            continue
        avg_amt = (sum(all_amts[-20:]) / len(all_amts[-20:])) if all_amts else 0.0
        boards.append(("概念", code, name, avg_amt, all_closes, all_dates))
        if (i + 1) % 50 == 0:
            print(f"  进度 {i+1}/{len(name_code)} (有效 {len(boards)})")
        time.sleep(0.15)
    save_ths_clid_cache(clid_cache)
    print(f"[sector_rps] THS 枚举完成：有效概念板块 {len(boards)} 个")
    if not boards:
        return None
    # 流动性预筛选（按成交额）
    if PRE_FILTER:
        tuples = [(b[0], b[1], b[2], b[3]) for b in boards]
        kept = liquidity_prefilter(tuples)
        keep_codes = {t[1] for t in kept}
        boards = [b for b in boards if b[1] in keep_codes]
    # 计算收益
    all_rets = []
    for cat, code, name, amt, closes, dates in boards:
        rets = compute_returns(closes)
        if any(v is not None for v in rets.values()):
            all_rets.append({"code": code, "name": name, "cat": cat,
                             "rets": rets, "close": closes[-1], "date": dates[-1],
                             "dates": dates, "closes": closes})
    if not all_rets:
        return None
    return all_rets


def main():
    source = RPS_SOURCE
    base_label = UNIVERSE_LABELS.get(UNIVERSE, UNIVERSE)
    label = (f"{base_label}（成交额前{int(PRE_FILTER_KEEP*100)}% 流动性预筛）"
             if (PRE_FILTER and UNIVERSE != "watchlist") else base_label)

    all_rets = None
    src_str = None
    total_boards = 0

    # ---- 源1：通达信 TDX（主源，概念板块指数 881xxx，名称全量自带）----
    if source in ("auto", "tdx"):
        print("[sector_rps] 源=通达信 TDX：枚举概念板块并取日K ...")
        all_rets = collect_via_tdx()
        if all_rets:
            src_str = "通达信 TDX（概念板块指数 881xxx，前复权；主源）"
            total_boards = len(all_rets)   # 已含流动性预筛
            save_name_cache(all_rets)      # TDX 自带名 -> 写缓存，供后续复用

    # ---- 源2：同花顺 THS（备用源，TDX 失败时兜底；官网 line 接口，非东财）----
    if not all_rets and source in ("auto", "ths"):
        print("[sector_rps] 源=同花顺 THS（备用源）：枚举概念板块并取日K ...")
        all_rets = collect_via_ths()
        if all_rets:
            src_str = "同花顺 THS（概念板块历史日K；备用源）"
            total_boards = len(all_rets)   # 已含流动性预筛

    if not all_rets:
        print("[sector_rps] 双源均不可用，写 ok:false")
        json.dump({"ok": False, "error": "both sources failed (tdx+ths)"},
                  open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return

    # ---- 用名称缓存补全板块名（TDX 名称列表未覆盖的）----
    cache = load_name_cache()
    patch = load_name_patch()
    hit = 0
    no_cache = []
    for b in all_rets:
        if b["name"] == b["code"] and b["code"] in cache:
            b["name"] = cache[b["code"]]
            hit += 1
        elif b["code"] in cache and cache[b["code"]] != b["name"]:
            b["name"] = cache[b["code"]]
            hit += 1
        elif b["name"] == b["code"] and b["code"] in patch:
            b["name"] = patch[b["code"]]
            hit += 1
            print(f"[sector_rps] 补充名称表命中: {b['code']} -> {b['name']}")
        elif b["name"] == b["code"]:
            no_cache.append(b["code"])
    print(f"[sector_rps] 名称缓存命中 {hit}/{len(all_rets)}")
    if no_cache:
        print(f"[sector_rps] 警告：{len(no_cache)} 个板块名未命中（显示为代码）："
              + ", ".join(no_cache[:20]))

    # ---- RPS 排名 + 筛选（≥3 个周期 > 阈值）----
    rps_map = rps_from_returns(all_rets)
    passed = []
    for b in all_rets:
        rps = rps_map.get(b["code"], {})
        vals = [rps.get(n) for n in PERIODS]
        n_pass = sum(1 for v in vals if v is not None and v > THRESHOLD)
        if n_pass >= MIN_PASS:
            passed.append({
                "code": b["code"], "name": b["name"], "cat": b["cat"],
                "rps5": rps.get(5), "rps10": rps.get(10),
                "rps20": rps.get(20), "rps50": rps.get(50),
                "n_pass": n_pass,
                "close": round(b["close"], 2),
                "ret5": round(b["rets"][5] * 100, 2) if b["rets"][5] is not None else None,
                "ret10": round(b["rets"][10] * 100, 2) if b["rets"][10] is not None else None,
                "ret20": round(b["rets"][20] * 100, 2) if b["rets"][20] is not None else None,
                "ret50": round(b["rets"][50] * 100, 2) if b["rets"][50] is not None else None,
                "date": b["date"],
                "hist_dates": b.get("dates") or [],
                "hist_close": [round(c, 2) for c in (b.get("closes") or [])],
            })

    # 排序：n_pass 降序，再 rps50 降序，再 rps20 降序
    passed.sort(key=lambda x: (x["n_pass"], x["rps50"] or 0, x["rps20"] or 0), reverse=True)

    latest = max((b["date"] for b in all_rets if b["date"]), default=None)
    out = {
        "ok": True,
        "source": src_str,
        "universe": UNIVERSE,
        "universe_label": label,
        "date": latest,
        "periods": PERIODS,
        "threshold": THRESHOLD,
        "min_pass": MIN_PASS,
        "total_boards": total_boards,
        "valid_boards": len(all_rets),
        "n_passed": len(passed),
        "passed": passed,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[sector_rps] 完成({src_str})：有效 {len(all_rets)} 板块，"
          f"通过筛选(≥{MIN_PASS}周期> {THRESHOLD}) {len(passed)} 个 -> {OUT}")
    for p in passed[:10]:
        print(f"   {p['name']:<10} rps5={p['rps5']} rps10={p['rps10']} "
              f"rps20={p['rps20']} rps50={p['rps50']} (n_pass={p['n_pass']})")


if __name__ == "__main__":
    main()
