#!/usr/bin/env python3
# 把 westock-data CLI 输出的 3 个 markdown 表格（8 指数 60 天日 K）解析为干净 JSON。
# 输出 data/_kline_clean.json: {symbol: [{"date","close","amount"}, ...]} （按文件顺序，后排序）
import re, json, os
DATA = "/Users/sugieliao/WorkBuddy/A股每日复盘/data"

def parse_table(path, symbol=None):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            # 跳过表头与分隔行
            if cells[0] in ("symbol", "date") or set(cells[0]) <= set("-"):
                continue
            if symbol is None:
                # 批量文件：首列为 symbol
                sym = cells[0]; date = cells[1]; last = cells[3]; amount = cells[7]
            else:
                sym = symbol; date = cells[0]; last = cells[2]; amount = cells[6]
            try:
                rows.append({"symbol": sym, "date": date,
                             "close": float(last), "amount": float(amount)})
            except (ValueError, IndexError):
                continue
    return rows

all_rows = []
all_rows += parse_table(os.path.join(DATA, "_raw_kline.json"))           # 批量：6 个指数
all_rows += parse_table(os.path.join(DATA, "_raw_kline_sz399006.json"), "sz399006")
all_rows += parse_table(os.path.join(DATA, "_raw_kline_sh000688.json"), "sh000688")

by_sym = {}
for r in all_rows:
    by_sym.setdefault(r["symbol"], []).append(
        {"date": r["date"], "close": r["close"], "amount": r["amount"]})
for s in by_sym:
    by_sym[s].sort(key=lambda x: x["date"])

out = os.path.join(DATA, "_kline_clean.json")
json.dump(by_sym, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("symbols:", sorted(by_sym))
for s in sorted(by_sym):
    print(f"  {s}: {len(by_sym[s])} rows, {by_sym[s][0]['date']}..{by_sym[s][-1]['date']}")
print("written", out)
