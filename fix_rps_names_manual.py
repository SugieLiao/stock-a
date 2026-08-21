#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手动补全 sector_rps.json 中 14 个 TDX 路径缺失的板块名称（通过 MCP tdx_quotes 获取）。"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
RPS_FILE = os.path.join(DATA, "sector_rps.json")
CACHE_FILE = os.path.join(DATA, "tdx_concept_names.json")

NAMES = {
    "881319": "半导体",
    "881300": "制冷空调设备",
    "881325": "半导体封测",
    "881324": "半导体制造",
    "881096": "玻纤制造",
    "881094": "玻璃玻纤",
    "881416": "装修装饰",
    "881295": "仪器仪表",
    "881333": "元器件",
    "881309": "其他专用设备",
    "881301": "磨具磨料",
    "881104": "非金属材料",
    "881046": "塑料薄膜",
    "881331": "光学元件",
}

# 1. 更新缓存
if os.path.exists(CACHE_FILE):
    cache = json.load(open(CACHE_FILE, encoding="utf-8"))
else:
    cache = {}
cache.update(NAMES)
json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[fix_names] 缓存更新 +{len(NAMES)} -> {CACHE_FILE}")

# 2. 补全 sector_rps.json
rps = json.load(open(RPS_FILE, encoding="utf-8"))
fixed = 0
for p in rps.get("passed", []):
    code = p.get("code", "")
    name = p.get("name", "")
    if name.startswith("88") and code in NAMES:
        p["name"] = NAMES[code]
        fixed += 1
json.dump(rps, open(RPS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[fix_names] sector_rps.json 修复 {fixed} 个板块名")

# 3. 验证
remaining = [s.get("name") for s in rps.get("passed", []) if s.get("name", "").startswith("88")]
print(f"[fix_names] 剩余代码名: {remaining} ({len(remaining)} 个)")
