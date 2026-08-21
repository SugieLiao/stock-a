#!/usr/bin/env python3
# 板块四「主力净流入」备选数据源：腾讯自选股 westock（不同 provider，绕开东方财富 push2 限流）。
#
# 为什么需要它：
#   东方财富 push2 行业板块资金流向接口容易被 IP 限流（返回空），导致板块四空白。
#   腾讯自选股 westock 的 data_sector(mode=ranking) 的 fundflow.plate 也提供「主力净流入(zljlr)」，
#   且为不同数据源；缺点：该接口仅返回 TOP3 / BOTTOM3（非完整前10）。
#
# 用法（由 agent 执行，因为 westock 是 MCP 工具，无法在独立脚本里直接调用）：
#   1) agent 调用 westock data_sector(mode=ranking, scope=sw1, date=YYYY-MM-DD)
#      取返回里 fundflow.plate.top / fundflow.plate.bottom（每项含 name, zljlr(万元), cje(万元), zdf(涨跌幅%)）
#   2) 抽取成如下 input.json：
#        {"date":"YYYY-MM-DD",
#         "top":[{"name":"通信设备","zljlr":210442.86,"cje":7500011.00,"zdf":3.09}, ...],
#         "bottom":[{"name":"工业金属","zljlr":-273910.94,"cje":2273926.00,"zdf":-1.89}, ...]}
#   3) python3 collect_section4_backup.py <input.json> YYYY-MM-DD
#      → 写出 data/YYYY-MM-DD_eastmoney.json（带 backup:true 标记，render.py 据此显示「备选」徽标）
#
# 单位：westock 的 zljlr / cje 为「万元」，这里统一换算成与东方财富一致的「亿元」。
import json, os, sys

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")

def conv(lst):
    out = []
    for x in lst:
        out.append({
            "name": x["name"],
            "pct": float(x.get("zdf", 0)),
            "turnover_yi": round(float(x.get("cje", 0)) / 1e4, 2),   # 万元 -> 亿元
            "zljlr_yi": round(float(x.get("zljlr", 0)) / 1e4, 2),    # 万元 -> 亿元
        })
    return out

def main():
    if len(sys.argv) < 3:
        print("usage: collect_section4_backup.py <input.json> <YYYY-MM-DD>")
        return
    inp, date = sys.argv[1], sys.argv[2]
    raw = json.load(open(inp, encoding="utf-8"))
    top, bot = conv(raw.get("top", [])), conv(raw.get("bottom", []))
    result = {
        "date": date,
        "source": "腾讯自选股 westock（备选·仅 TOP3/BOTTOM3 主力净流入）",
        "backup": True,
        "net_inflow_sectors": {"top": top, "bottom": bot},
    }
    path = os.path.join(DATA, f"{date}_eastmoney.json")
    json.dump(result, open(path, "w"), ensure_ascii=False, indent=2)
    print("备选已写出", path, "| top:", len(top), "bottom:", len(bot))

if __name__ == "__main__":
    main()
