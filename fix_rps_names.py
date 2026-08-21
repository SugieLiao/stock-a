#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick fix: 用东财 clist 接口补全 sector_rps.json 中 TDX 路径缺失的板块名称。"""
import json, os, sys, time
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
RPS_FILE = os.path.join(DATA, "sector_rps.json")
CACHE_FILE = os.path.join(DATA, "tdx_concept_names.json")
UA = "Mozilla/5.0"

def http_get_json(url, retries=2, timeout=10):
    import subprocess
    for attempt in range(retries):
        try:
            try:
                import requests
                sess = getattr(http_get_json, "_sess", None)
                if sess is None:
                    sess = requests.Session()
                    sess.headers.update({
                        "User-Agent": UA, "Accept": "*/*",
                        "Referer": "https://quote.eastmoney.com/",
                    })
                    http_get_json._sess = sess
                return sess.get(url, timeout=timeout).json()
            except ImportError:
                pass
            out = subprocess.run(
                ["curl", "-sS", "-m", str(timeout), "-A", UA,
                 "-H", "Connection: close", "-H", "Accept: */*",
                 "-H", "Referer: https://quote.eastmoney.com/", url],
                capture_output=True, text=True, timeout=timeout + 10,
            )
            if out.returncode == 0 and out.stdout.strip():
                return json.loads(out.stdout)
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None

def fetch_board_list(fs, sample=None):
    items = []
    pn = 1; pz = 100
    while True:
        ts = int(time.time() * 1000)
        url = (f"https://push2.eastmoney.com/api/qt/clist/get"
               f"?pn={pn}&pz={pz}&fs={fs}&fields=f12,f14,f6&_={ts}")
        d = http_get_json(url)
        if not d or d.get("rc") != 0 or not d.get("data"):
            break
        diff = d["data"].get("diff") or {}
        for v in diff.values():
            code = v.get("f12")
            name = v.get("f14")
            if code and name:
                items.append((code, name))
        total = d["data"].get("total", 0)
        if sample and len(items) >= sample:
            return items[:sample]
        if not diff or len(items) >= total:
            break
        pn += 1
        time.sleep(0.1)
    return items


def main():
    # 1. 拉取概念板块列表
    print("[fix_names] 拉取东财概念板块列表 ...")
    boards = fetch_board_list("m:90+t:3")
    if not boards:
        print("[fix_names] 东财 clist 接口不可用，无法补名字")
        sys.exit(1)
    mapping = {c: n for c, n in boards}
    print(f"[fix_names] 东财返回 {len(mapping)} 个概念板块")

    # 2. 更新缓存
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            cache = json.load(open(CACHE_FILE, encoding="utf-8"))
        except Exception:
            pass
    added = 0
    for c, n in boards:
        if cache.get(c) != n:
            cache[c] = n
            added += 1
    if added:
        json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[fix_names] 缓存更新 +{added} -> {CACHE_FILE}")
    else:
        print(f"[fix_names] 缓存无变化")

    # 3. 补全 sector_rps.json
    if not os.path.exists(RPS_FILE):
        print("[fix_names] 无 sector_rps.json")
        sys.exit(1)
    rps = json.load(open(RPS_FILE, encoding="utf-8"))
    if not rps.get("ok"):
        print("[fix_names] sector_rps.json ok=false")
        sys.exit(1)
    fixed = 0
    for p in rps.get("passed", []):
        code = p.get("code", "")
        name = p.get("name", "")
        if name.startswith("88") and code in mapping:
            p["name"] = mapping[code]
            fixed += 1
    if fixed:
        json.dump(rps, open(RPS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[fix_names] sector_rps.json 修复 {fixed} 个板块名")
    else:
        print("[fix_names] sector_rps.json 无需修复")

    # 4. 打印修复后的 code-like names
    code_like = [s.get("name") for s in rps.get("passed", []) if s.get("name", "").startswith("88")]
    print(f"[fix_names] 剩余代码名: {code_like} ({len(code_like)} 个)")


if __name__ == "__main__":
    main()
