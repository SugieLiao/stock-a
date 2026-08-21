#!/usr/bin/env python3
# 板块四（主力净流入前10）的【同花顺 thsdk 备选】采集器。
# 当东方财富 push2 被限流、collect_eastmoney.py 拿不到数据时，用本脚本替代：
#   同花顺 thsdk（游客模式，无需账户）提供 行业板块 主力净流入 / 涨幅 / 成交额，
#   按主力净流入排序出前10 / 后10，写出带 backup 标记的 eastmoney.json，
#   render.py 检测到后把板块四标题切到「同花顺·备选」并显示⚠徽标。
# 用法：
#   collect_section4_ths.py 2026-08-12
#   collect_section4_ths.py 2026-08-12 --out /tmp/test.json
import json, sys, os, time, argparse, datetime

OUTDIR = "/Users/sugieliao/WorkBuddy/A股每日复盘/data"
BACKUP_SOURCE = "同花顺 thsdk（游客模式）"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=None, help="输出 json 路径（默认 data/YYYY_eastmoney.json）")
    args = ap.parse_args()
    date = args.date
    out = args.out or os.path.join(OUTDIR, f"{date}_eastmoney.json")

    from thsdk import THS
    rows = []  # {code, name, zljlr_yi, pct}
    with THS() as ths:
        print("获取同花顺行业列表...", file=sys.stderr)
        ind = ths.ths_industry()
        items = ind.data if hasattr(ind, "data") else []
        print(f"行业数: {len(items)}", file=sys.stderr)
        for it in items:
            code = it.get("代码"); name = it.get("名称")
            if not code:
                continue
            try:
                time.sleep(0.35)
                r = ths.market_data_block(code, "扩展")
                df = r.df
                if df is None or df.empty:
                    continue
                row = df.iloc[0]
                zljlr = float(row.get("主力净流入") or 0)   # 元
                pct = float(row.get("涨幅") or 0)            # %
                rows.append({"code": code, "name": name,
                             "zljlr_yi": round(zljlr / 1e8, 2),
                             "pct": round(pct, 2)})
            except Exception as e:
                print(f"  skip {name}({code}): {e}", file=sys.stderr)
                continue
    print(f"成功取到 {len(rows)} 个行业的 主力净流入", file=sys.stderr)
    if not rows:
        print("无任何行业数据，中止（不覆盖已有文件）", file=sys.stderr)
        return

    rows.sort(key=lambda x: x["zljlr_yi"], reverse=True)
    top = rows[:10]
    bottom = sorted(rows, key=lambda x: x["zljlr_yi"])[:10]

    # 为前10/后10 补抓 成交额（总金额，基础数据）
    need = {x["code"]: x for x in (top + bottom)}
    with THS() as ths:
        for code, rec in need.items():
            try:
                time.sleep(0.35)
                r = ths.market_data_block(code, "基础数据")
                df = r.df
                if df is not None and not df.empty:
                    rec["turnover_yi"] = round(float(df.iloc[0].get("总金额") or 0) / 1e8, 1)
            except Exception as e:
                print(f"  成交额 skip {rec['name']}: {e}", file=sys.stderr)

    for lst in (top, bottom):
        for x in lst:
            x.setdefault("turnover_yi", None)

    result = {
        "date": date,
        "source": "东方财富 push2 限流，已由同花顺 thsdk 备选替代",
        "backup": True,
        "backup_source": BACKUP_SOURCE,
        "net_inflow_sectors": {"top": top, "bottom": bottom},
    }
    json.dump(result, open(out, "w"), ensure_ascii=False, indent=2)
    print(f"已写出(备选) {out} | top:{len(top)} bottom:{len(bottom)}", file=sys.stderr)

if __name__ == "__main__":
    main()
