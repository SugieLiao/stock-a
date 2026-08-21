#!/usr/bin/env python3
# 板块三（成交额前10）+ 板块四（主力净流入前10/后10）【统一口径】采集器。
# 同花顺 AKShare 获取 90 个同花顺行业，
#   基础数据(总成交额 -> 板块成交额) + 扩展(主力净流入、涨幅) ，
# 板块三 = 按成交额排序取前 10，板块四 = 按主力净流入排序取前 10 / 后 10。
# 两节共用同一套 90 行业口径，渲染层可直接对照「同一行业」的成交额与主力净流入。
# 历史 K 线也用 AKShare 同花顺行业指数接口获取，确保与行业名称一致
# （旧版用 TDX get_index_bars，但同花顺与 TDX 的 881xxx 代码体系不兼容，导致 K 线数据错误）。
# 用法：
#   collect_sectors_ths.py 2026-08-12
#   collect_sectors_ths.py 2026-08-12 --out /tmp/test.json
import json, sys, os, time, argparse, datetime

OUTDIR = "/Users/sugieliao/WorkBuddy/A股每日复盘/data"
SOURCE = "同花顺 AKShare 行业板块"
NEED_BARS = 60  # hover 迷你K线显示天数


def fetch_sector_hist_ak(name, need=NEED_BARS):
    """用 AKShare 获取同花顺行业指数的历史 K 线（与行业名称严格对应）。"""
    try:
        import akshare as ak
        start = (datetime.date.today() - datetime.timedelta(days=90)).strftime('%Y%m%d')
        end = datetime.date.today().strftime('%Y%m%d')
        df = ak.stock_board_industry_index_ths(symbol=name, start_date=start, end_date=end)
        if df is None or df.empty or len(df) < 30:
            return None, None
        df = df.tail(need)
        dates = [str(d) for d in df["日期"].tolist()]
        closes = [round(float(x), 2) for x in df["收盘价"].tolist()]
        return dates, closes
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=None, help="输出 json 路径（默认 data/YYYY_sectors_ths.json）")
    args = ap.parse_args()
    date = args.date
    out = args.out or os.path.join(OUTDIR, f"{date}_sectors_ths.json")

    import akshare as ak

    # 1. 获取同花顺 90 行业实时摘要
    print("获取同花顺行业实时数据...", file=sys.stderr)
    df_spot = ak.stock_board_industry_summary_ths()
    items = df_spot.to_dict('records')
    print(f"行业数: {len(items)}", file=sys.stderr)

    # 2. 获取行业代码映射（用于填充 code 字段，保持与旧版格式兼容）
    name_to_code = {}
    try:
        df_code = ak.stock_board_industry_name_ths()
        name_to_code = dict(zip(df_code['name'], df_code['code']))
    except Exception as e:
        print(f"  获取代码表失败: {e}", file=sys.stderr)

    rows = []
    for idx, it in enumerate(items):
        name = it.get('板块')
        if not name:
            continue
        code = name_to_code.get(name, '')
        rec = {
            "code": f"URFI{code}" if code else None,
            "name": name,
            "turnover_yi": round(float(it.get('总成交额') or 0), 1),
            "zljlr_yi": round(float(it.get('净流入') or 0), 2),
            "pct": round(float(it.get('涨跌幅') or 0), 2),
        }
        # 用 AKShare 获取 60 日历史收盘（供 hover 迷你K线用）
        hd, hc = fetch_sector_hist_ak(name)
        if hd and hc:
            rec["hist_dates"] = hd
            rec["hist_close"] = hc
        rows.append(rec)

    n_hist = sum(1 for r in rows if r.get("hist_dates"))
    print(f"成功取到 {len(rows)} 个行业的板块数据（其中 {n_hist} 个有历史K线）", file=sys.stderr)
    if not rows:
        print("无任何行业数据，中止（不写出，保留已有文件）", file=sys.stderr)
        return
    for x in rows:
        x.setdefault("turnover_yi", None)
        x.setdefault("zljlr_yi", None)
        x.setdefault("pct", None)
    # 板块三：按成交额排序取前 10（成交额缺失的排不到前面）
    top_sectors = sorted([x for x in rows if x["turnover_yi"] is not None],
                         key=lambda x: x["turnover_yi"], reverse=True)[:10]
    # 板块四：按主力净流入排序
    net_rows = [x for x in rows if x["zljlr_yi"] is not None]
    net_top = sorted(net_rows, key=lambda x: x["zljlr_yi"], reverse=True)[:10]
    net_bot = sorted(net_rows, key=lambda x: x["zljlr_yi"])[:10]
    result = {
        "date": date,
        "source": SOURCE,
        "top_sectors": top_sectors,
        "net_inflow_sectors": {"top": net_top, "bottom": net_bot},
    }
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已写出 {out} | 板块三候选 {len(top_sectors)} 个 | 板块四 top {len(net_top)} bot {len(net_bot)}", file=sys.stderr)

if __name__ == "__main__":
    main()
