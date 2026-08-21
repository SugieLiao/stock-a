#!/usr/bin/env python3
"""给 sector_rps.json 的 passed 板块补上 hist_dates/hist_close（hover 迷你K线用）"""
import json, os, time, random, urllib.request

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
OUT = os.path.join(BASE, "data", "sector_rps.json")

def fetch_closes(code, need=60):
    ts = int(time.time() * 1000)
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=90.{code}&fields1=f1,f2,f3"
           f"&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1"
           f"&lmt={need}&end=20500101&_={ts}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read())
    except Exception as e:
        print(f"  {code} 失败: {e}")
        return None, None
    if not d or not d.get("data") or not d["data"].get("klines"):
        return None, None
    rows = [r.split(",") for r in d["data"]["klines"]]
    dates = [r[0] for r in rows]
    closes = [float(r[2]) for r in rows]
    return dates, closes

def main():
    data = json.load(open(OUT, encoding="utf-8"))
    if not data.get("ok") or not data.get("passed"):
        print("sector_rps.json 无有效数据")
        return
    passed = data["passed"]
    print(f"共 {len(passed)} 个通过板块，开始补充 hist 数据...")
    for i, p in enumerate(passed):
        code = p["code"]
        if p.get("hist_dates") and p.get("hist_close") and len(p["hist_close"]) >= 20:
            continue  # 已有数据
        dates, closes = fetch_closes(code)
        if dates and closes:
            p["hist_dates"] = dates
            p["hist_close"] = [round(c, 2) for c in closes]
            print(f"  [{i+1}/{len(passed)}] {code} {p['name']} → {len(closes)} 根")
        else:
            p["hist_dates"] = []
            p["hist_close"] = []
            print(f"  [{i+1}/{len(passed)}] {code} {p['name']} → 失败")
        time.sleep(random.uniform(0.3, 0.5))
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ok = sum(1 for p in passed if p.get("hist_close") and len(p["hist_close"]) >= 20)
    print(f"完成：{ok}/{len(passed)} 个板块有 hist 数据")

if __name__ == "__main__":
    main()
