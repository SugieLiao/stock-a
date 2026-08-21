#!/usr/bin/env python3
# 东方财富 行业板块资金流向（主力净流入）同日排名，取前10 / 后10。
# 输出 /Users/sugieliao/WorkBuddy/A股每日复盘/data/YYYY-MM-DD_eastmoney.json
# 主源：东方财富 push2 行业板块（可同日取前10）。
# 备选：东方财富被限流且取空时，自动回退到 同花顺 thsdk（游客模式）collect_section4_ths.py，
#       遍历 90 个同花顺行业取主力净流入/涨幅/成交额，排名前10/后10（板块口径为同花顺行业）。
import json, os, sys, datetime, subprocess, urllib.parse

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
FS = "m:90+t:2"  # 行业板块

def fetch(fs, fid, po, pz=10):
    fields = "f12,f14,f2,f3,f6,f62,f184"  # 代码,名称,价,涨跌幅,成交额(元),主力净流入(元),主力净流入占比
    url = "https://push2.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode({
        "pn": "1", "pz": str(pz), "po": str(po), "np": "1", "fltt": "2", "invt": "2",
        "fid": fid, "fs": fs, "fields": fields})
    out = subprocess.run(["curl", "-s", "--max-time", "40", url, "-H", "User-Agent: Mozilla/5.0"],
                         capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
    except Exception:
        return []
    diff = (d.get("data") or {}).get("diff") or []
    res = []
    for x in diff:
        res.append({
            "code": x.get("f12"),
            "name": x.get("f14"),
            "pct": x.get("f3"),
            "turnover_yi": round((x.get("f6") or 0) / 1e8, 2),  # 成交额(元) -> 亿元
            "zljlr_yi": round((x.get("f62") or 0) / 1e8, 2),  # 元 -> 亿元
        })
    return res

def main():
    os.makedirs(DATA, exist_ok=True)
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
    top = fetch(FS, "f62", 1, 10)   # 主力净流入降序
    bot = fetch(FS, "f62", 0, 10)   # 主力净流入升序（= 净流出前10）
    if not top and not bot:
        # 主源被限流：绝不覆盖已有数据（避免把已渲染好的板块四清空），
        # 自动回退到同花顺 thsdk 备选，保证板块四不空白。
        print(f"[WARN] 东方财富 push2 限流/空返回，自动回退同花顺 thsdk 备选...", file=sys.stderr)
        try:
            subprocess.run([sys.executable, os.path.join(BASE, "collect_section4_ths.py"), date],
                           check=True)
            print(f"[INFO] 已用同花顺 thsdk 备选写出 {date}_eastmoney.json", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] 同花顺 thsdk 备选亦失败：{e}；板块四将暂缺", file=sys.stderr)
        return
    result = {
        "date": date,
        "source": "东方财富 push2 行业板块资金流向（当日）",
        "net_inflow_sectors": {"top": top, "bottom": bot},
    }
    path = os.path.join(DATA, f"{date}_eastmoney.json")
    json.dump(result, open(path, "w"), ensure_ascii=False, indent=2)
    print("已写出", path, "| top:", len(top), "bottom:", len(bot))

if __name__ == "__main__":
    main()
