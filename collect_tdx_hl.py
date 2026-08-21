#!/usr/bin/env python3
# 将通达信 tdx_screener 的两次选股结果（MCP 返回 JSON）归一化为 data/YYYY-MM-DD_tdxhl.json。
# 用法（由自动化 agent 调用）：
#   1) 调 tdx_screener(message="今日创一年新高", rang="AG", pageSize=50) -> 存 high.json
#   2) 调 tdx_screener(message="今日创一年新低", rang="AG", pageSize=50) -> 存 low.json
#   3) python3 collect_tdx_hl.py YYYY-MM-DD high.json low.json
# 输出结构：{date, source, query_note, high_new:{count,stocks:[{code,name,price,chg}]}, low_new:{...}}
import json, sys, os

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")

def parse(path):
    """从 tdx_screener 结果 JSON 提取 count 与个股列表。"""
    raw = json.load(open(path, encoding="utf-8"))
    # tdx_screener 返回在 data[].meta.total；兼容直接给 {meta,data} 或 {total,stocks}
    meta = raw.get("meta") or {}
    total = meta.get("total")
    rows = raw.get("data") or []
    if total is None:
        total = len(rows)
    stocks = []
    for r in rows:
        code = r.get("sec_code") or r.get("code")
        name = r.get("sec_name") or r.get("name")
        price = r.get("now_price")
        chg = r.get("chg")
        # 兼容字符串型数值
        try: price = float(price) if price not in (None, "") else None
        except Exception: price = None
        try: chg = float(chg) if chg not in (None, "") else None
        except Exception: chg = None
        stocks.append({"code": code, "name": name, "price": price, "chg": chg})
    return total, stocks

def main():
    if len(sys.argv) < 4:
        print("用法: collect_tdx_hl.py <YYYY-MM-DD> <high.json> <low.json>")
        sys.exit(1)
    date, high_path, low_path = sys.argv[1], sys.argv[2], sys.argv[3]
    hc, hs = parse(high_path)
    lc, ls = parse(low_path)
    out = {
        "date": date,
        "source": "通达信 tdx_screener 条件选股（当日）",
        "query_note": "今日创一年新高 / 今日创一年新低（前复权，A股全市场）",
        "high_new": {"count": hc, "stocks": hs},
        "low_new": {"count": lc, "stocks": ls},
    }
    dest = os.path.join(DATA, f"{date}_tdxhl.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已生成 {dest} | 新高 {hc} 只 / 新低 {lc} 只")

if __name__ == "__main__":
    main()
