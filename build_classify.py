#!/usr/bin/env python3
# 构建全市场「个股 -> 行业 / 概念板块」分类映射缓存。
# 数据源：同花顺 hithink-finance（ths-index-list 目录 + ths-stock-list 成分股）。
# 思路：枚举 行业(industry) + 概念(cn_concept) 全部板块，取各板块成分股，反查为 code->boards。
# 输出 data/stock_classify.json：{thscode: {"industry":[...], "concept":[...]}}（仅含实际出现的板块名）。
# 每天自动运行时若缓存 <7 天则跳过（加 --force 强制重建）。
import json, os, sys, time, datetime, urllib.request, urllib.error, concurrent.futures

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
KEYFILE = "/Users/sugieliao/.workbuddy/hithink_finance_key"
OUT = os.path.join(DATA, "stock_classify.json")
MAX_AGE_DAYS = 7
N_WORKERS = 16

def get_key():
    return open(KEYFILE).read().strip()

def api_get(path):
    url = "https://fuyao.aicubes.cn" + path
    req = urllib.request.Request(url, headers={"X-api-key": KEY})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(0.4)
    return {"code": -1, "message": "fail"}

def fetch_catalog(tag):
    d = api_get(f"/api/a-share-index/catalog/ths-index-list?tag={tag}")
    if d.get("code") != 0:
        return []
    return d.get("data", {}).get("item", [])

def fetch_constituents(thscode):
    d = api_get(f"/api/a-share-index/constituents/ths-stock-list?thscode={thscode}")
    if d.get("code") != 0 or not d.get("data"):
        return []
    return [it.get("thscode") for it in d["data"].get("item", []) if it.get("thscode")]

def load_cache_or_none(force):
    if force:
        return None
    if os.path.exists(OUT):
        age = time.time() - os.path.getmtime(OUT)
        if age < MAX_AGE_DAYS * 86400:
            return json.load(open(OUT, encoding="utf-8"))
    return None

def main():
    global KEY
    force = "--force" in sys.argv
    existing = load_cache_or_none(force)
    if existing is not None:
        print(f"缓存较新（<{MAX_AGE_DAYS}天），跳过重建。当前 {len(existing)} 只。用 --force 强制。")
        return
    KEY = get_key()
    print("拉取 行业 / 概念 板块目录…", file=sys.stderr)
    ind = fetch_catalog("industry")
    con = fetch_catalog("cn_concept")
    print(f"  行业板 {len(ind)} 个，概念板 {len(con)} 个", file=sys.stderr)
    boards = [(b["thscode"], b["name"], "industry") for b in ind] + \
             [(b["thscode"], b["name"], "concept") for b in con]
    print(f"拉取 {len(boards)} 个板块成分股（并发 {N_WORKERS}）…", file=sys.stderr)
    classify = {}  # thscode -> {"industry":set, "concept":set}
    def work(b):
        ts, nm, kind = b
        members = fetch_constituents(ts)
        return ts, nm, kind, members
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = [ex.submit(work, b) for b in boards]
        for f in concurrent.futures.as_completed(futs):
            ts, nm, kind, members = f.result()
            for m in members:
                e = classify.setdefault(m, {"industry": set(), "concept": set()})
                e[kind].add(nm)
            done += 1
            if done % 100 == 0:
                print(f"  …{done}/{len(boards)} 板块完成", file=sys.stderr)
    # 转 list 便于 JSON
    out = {k: {"industry": sorted(v["industry"]), "concept": sorted(v["concept"])}
           for k, v in classify.items()}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：{len(out)} 只个股写入 {OUT}", file=sys.stderr)

if __name__ == "__main__":
    main()
