#!/usr/bin/env python3
# 取 平均股价(880003) 近 ~60 交易日日K（OHLC），写 data/wande.json。
# 来源：通达信 平均股价（880003，沪市板块指数）= 全市场个股价格的等权平均，
#       作为「全A等权」的可视化代理（比市值加权的 万得全A(881001) 更贴近等权口径）。
# 取数走 pytdx 直连通达信行情服务器（get_index_bars，指数专用命令 0x8c）；
# 若全部行情服务器不可达则写 ok:false，render 显示占位，下次运行自动重试。
import json, os, sys, datetime, time

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
SECID = "880003"            # 平均股价（通达信代码，沪市板块指数）
NAME = "平均股价"
MARKET = 1                 # 沪市
LIMIT = 60                 # 保留最近交易日数
TDX_HOSTS = [
    ("115.238.90.165", 7709),
    ("119.147.212.81", 7709),
    ("124.74.236.94", 7709),
    ("180.153.39.20", 7709),
    ("218.108.98.18", 7709),
]


def connect_tdx():
    try:
        from pytdx.hq import TdxHq_API
    except Exception as e:
        print(f"[wande] pytdx 不可用：{e}")
        return None
    api = TdxHq_API(multithread=False)
    for h, p in TDX_HOSTS:
        try:
            if api.connect(h, p, time_out=6):
                print(f"[wande] TDX 已连接 {h}:{p}")
                return api
        except Exception:
            continue
    print("[wande] TDX 所有服务器均不可达")
    return None


def write_fail(date, reason):
    out = {"ok": False, "code": SECID, "name": NAME,
           "reason": reason, "updated": date}
    json.dump(out, open(os.path.join(DATA, "wande.json"), "w"), ensure_ascii=False, indent=2)
    print(f"[wande] 取数失败（{reason}），已写 ok:false 占位；下次运行自动重试。")


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
    api = connect_tdx()
    if not api:
        write_fail(date, "通达信行情服务器不可达（网络受限）")
        return
    bars = None
    try:
        # 指数专用命令（区别于股票的 get_security_bars），category=4 日线
        bars = api.get_index_bars(4, MARKET, SECID, 0, LIMIT)
    except Exception as e:
        print(f"[wande] get_index_bars 异常：{e}")
    finally:
        try:
            api.disconnect()
        except Exception:
            pass
    if not bars or len(bars) < 2:
        write_fail(date, "通达信返回日K为空或不足")
        return
    dates, o, c, h, l = [], [], [], [], []
    for b in bars:
        dt = (b.get("datetime") or "")[:10]
        if not dt:
            continue
        dates.append(dt)
        try:
            o.append(float(b["open"])); c.append(float(b["close"]))
            h.append(float(b["high"])); l.append(float(b["low"]))
        except (ValueError, KeyError, TypeError):
            continue
    if len(dates) < 2:
        write_fail(date, "通达信日K 解析失败")
        return
    # 裁到最近 LIMIT 个交易日
    idx0 = max(0, len(dates) - LIMIT)
    out = {
        "ok": True, "code": SECID, "name": NAME,
        "source": "通达信 TDX 平均股价(880003) 指数日K（等权全A代理）",
        "updated": date,
        "dates": dates[idx0:], "open": o[idx0:], "close": c[idx0:],
        "high": h[idx0:], "low": l[idx0:],
    }
    json.dump(out, open(os.path.join(DATA, "wande.json"), "w"), ensure_ascii=False, indent=2)
    print(f"[wande] 已写 {len(out['dates'])} 个交易日 {NAME}({SECID}) 日K，"
          f"末日 {out['dates'][-1]} 收盘 {out['close'][-1]}")


if __name__ == "__main__":
    main()
