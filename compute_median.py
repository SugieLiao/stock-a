#!/usr/bin/env python3
# 用同花顺(hithink-finance / fuyao)全市场行情快照，精确计算 A股涨跌幅中位数。
# 方法：分页拉取 /api/a-share/prices/snapshot 全市场，收集每只 price_change_ratio_pct，
# 排序后取中间那只 = 精确中位数（用户定义口径）。零依赖，仅用 curl + 标准库。
# Key 从 ~/.workbuddy/hithink_finance_key 读取（600 权限，不进代码/日志）。
import json, subprocess, sys

KEYFILE = "/Users/sugieliao/.workbuddy/hithink_finance_key"
try:
    KEY = open(KEYFILE).read().strip()
except Exception as e:
    print(json.dumps({"error": f"无法读取API Key: {e}"}))
    sys.exit(1)

BASE = "https://fuyao.aicubes.cn/api/a-share/prices/snapshot"
LIMIT = 2000

def fetch(offset):
    url = f"{BASE}?limit={LIMIT}&offset={offset}"
    out = subprocess.run(["curl", "-s", "--max-time", "30", url,
                          "-H", f"X-api-key: {KEY}"],
                         capture_output=True, text=True).stdout
    return json.loads(out)

all_chg = []
up = down = flat = limit_up = limit_down = 0
offset = pages = 0
try:
    while True:
        d = fetch(offset)
        if d.get("code") != 0:
            print(json.dumps({"error": f"API错误 code={d.get('code')} msg={d.get('message')}"}))
            sys.exit(1)
        items = d["data"]["item"]
        pages += 1
        for it in items:
            pct = it.get("price_change_ratio_pct")
            if pct is None:
                continue
            all_chg.append(pct)
            if pct > 0: up += 1
            elif pct < 0: down += 1
            else: flat += 1
            if pct >= 9.9: limit_up += 1
            if pct <= -9.9: limit_down += 1
        if len(items) < LIMIT:
            break
        offset += LIMIT
except Exception as e:
    print(json.dumps({"error": f"请求异常: {e}"}))
    sys.exit(1)

n = len(all_chg)
all_chg.sort()
mid = n // 2
median = all_chg[mid] if n % 2 == 1 else (all_chg[mid - 1] + all_chg[mid]) / 2
print(json.dumps({
    "median_pct": round(median, 4),
    "valid_stocks": n,
    "up": up, "down": down, "flat": flat,
    "limit_up": limit_up, "limit_down": limit_down,
    "source": "同花顺全市场快照精确计算"
}, ensure_ascii=False))
