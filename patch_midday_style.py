#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性补丁：给午盘版 A股午盘_2026-08-17.html 补回「风格指数」子表 + cStyle 曲线。

背景：今日午盘快照（14:38 采集）早于「风格指数」功能上线（15:54 收盘版首次包含），
故 2026-08-17_midday_bundle.json 无 style_indices；收盘版 render.py 已自带该结构，
明日及以后的午盘版会自动包含，本次仅修复今日线上午盘页。

做法：以当日收盘 hithink 数据（data/2026-08-17_hithink.json 的 style_indices，含 60 日
hist）按 render.py 同一逻辑对齐到午盘 D.idx_dates（同为 2026-05-25 → 2026-08-17），
生成风格表 + 归一化曲线，并在表上方加注「收盘后补录」说明，避免被误读为快照值。

修改点（与收盘版 A股复盘_2026-08-17.html 结构对齐）：
1) 板块二标题 → <h2>二、指数表现</h2> + <h4>宽基指数</h4>；宽基图 h4 加「宽基指数 ·」前缀
2) cIdx canvas 后注入：<hr> + 风格指数子表 + 来源注 + 曲线 h4 + leg_cStyle/cStyle canvas + 剔除注
3) renderIdxTip 后注入：风格曲线 JS（归一化 find 首个非空为基准）+ renderStyleTip
4) buildLegends ids 加入 'cStyle'
5) openZoom 增加 id==='cStyle' 分支
6) D 载荷注入 style_indices / style_dates / style_lines / style_dropped
"""
import re, json, os, shutil, sys

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
MID = os.path.join(BASE, "A股午盘_2026-08-17.html")
CLOSE_HIT = os.path.join(BASE, "data", "2026-08-17_hithink.json")
BAK = MID + ".bak"

# ---------------- 0. 备份 ----------------
shutil.copy2(MID, BAK)
print("[0] 备份 ->", BAK)

# ---------------- 1. 解析 D JSON（括号匹配，鲁棒） ----------------
html = open(MID, encoding="utf-8").read()
m = re.search(r"const D = (\{)", html)
assert m, "const D 未找到"
i = m.start(1)
j = i; depth = 0; in_str = False; esc = False
while j < len(html):
    c = html[j]
    if in_str:
        if esc: esc = False
        elif c == "\\": esc = True
        elif c == '"': in_str = False
    else:
        if c == '"': in_str = True
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
    j += 1
assert depth == 0 and j < len(html), "D JSON 括号未闭合"
D = json.loads(html[i:j])
assert "style_lines" not in D, "D 已有 style_lines？无需补丁"
idx_dates = D.get("idx_dates")
assert idx_dates, "D.idx_dates 缺失"
print(f"[1] D 载荷解析 OK，idx_dates {len(idx_dates)} 天: {idx_dates[0]} → {idx_dates[-1]}")

# ---------------- 2. 构建风格数据（与 render.py 对齐逻辑一致） ----------------
h = json.load(open(CLOSE_HIT, encoding="utf-8"))
style_indices = h.get("style_indices") or []
assert style_indices, "收盘 hithink 无 style_indices"
style_lines, style_dropped = [], []
for s in style_indices:
    hd = s.get("hist_dates") or []
    hc = s.get("hist_close") or []
    if not hd or not hc:
        continue
    mv = dict(zip(hd, hc))
    data = [mv.get(dt) for dt in idx_dates]
    nn = sum(1 for v in data if v is not None)
    if nn / len(idx_dates) >= 0.6:
        style_lines.append({"name": s.get("name", "?"), "data": data})
    else:
        style_dropped.append(s.get("name", "?"))
D["style_indices"] = style_indices
D["style_dates"] = idx_dates
D["style_lines"] = style_lines
D["style_dropped"] = style_dropped
new_json = json.dumps(D, ensure_ascii=False)
html = html[:i] + new_json + html[j:]
print(f"[2] style_lines {len(style_lines)} 条，剔除 {len(style_dropped)} 条: {style_dropped}")

# ---------------- 3. 板块二标题统一（与收盘版一致） ----------------
h2_old = '<div class="card" data-cutoff="11:30"><h2>二、指数表现（重要宽基指数）</h2>'
h2_new = '<div class="card" data-cutoff="11:30"><h2>二、指数表现</h2>\n<h4>宽基指数</h4>'
assert html.count(h2_old) == 1, "h2 锚点异常"
html = html.replace(h2_old, h2_new)

h4_old = '<h4 style="margin-top:14px">近 60 交易日收盘走势（归一化 · 首日=100）</h4>'
h4_new = '<h4 style="margin-top:14px">宽基指数 · 近 60 交易日收盘走势（归一化 · 首日=100）</h4>'
assert html.count(h4_old) == 1, "宽基图 h4 锚点异常"
html = html.replace(h4_old, h4_new)

# ---------------- 4. 注入风格指数 HTML 段（render.py 同款行格式） ----------------
def pct_color(p):
    return "#d8392b" if p > 0 else ("#16a34a" if p < 0 else "#1f2329")
def fmt_pct(p):
    return f"{'+' if p > 0 else ''}{p:.2f}%"

style_rows = ""
for s in style_indices:
    nm = s.get("name", "?")
    close = s.get("close")
    pct = s.get("pct")
    if pct is None:
        style_rows += f"<tr><td>{nm}</td><td class='num'>—</td><td class='num'>—</td></tr>"
    else:
        arr = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
        style_rows += (f"<tr><td>{nm}</td><td class='num'>{close}</td>"
                       f"<td class='num' style='color:{pct_color(pct)};font-weight:600'>{arr}{fmt_pct(pct)}</td></tr>")

drop_note = ""
if style_dropped:
    drop_note = (f"<p class='note' style='color:#888;background:#f6f8fa'>注："
                 f"{'、'.join(style_dropped)}（同花顺仅部分交易日发布、历史不连续）"
                 f"未纳入曲线，其当日表现见上方表格。</p>")

style_html = (
    '<hr style="margin:20px 0 6px;border:none;border-top:1px solid #e5e8ec">\n'
    '<h4 style="margin-top:8px">风格指数（短线风格 / 情绪）</h4>\n'
    "<p class='note' style='color:#b7791f'>⚠ 风格指数采集功能上线于本快照之后，午间版以当日收盘数据补录"
    "（下表与曲线为收盘值；宽基指数仍为快照值）。</p>\n"
    f"<table><tr><th>风格</th><th>收盘</th><th>涨跌幅</th></tr>{style_rows}</table>\n"
    "<p class='note'>风格指数数据来源：同花顺 hithink 特色指数（tszs，与上方宽基指数同源）；"
    "北证50 来自腾讯行情（hithink 指数接口不支持北交所）。「昨日涨停 / 昨日成交前10 / 北交所昨日涨停」"
    "为同花顺编制的风格指数：成分股为上一交易日对应股票（涨停股 / 成交额前十 / 北交所涨停股），指数反映其今日整体表现。</p>\n"
    '<h4 style="margin-top:14px">风格指数 · 近 60 交易日收盘走势（归一化 · 首日=100）</h4>\n'
    "<p class='note'>风格指数点位差异大（全A 约 2000 点、微盘股数万点），统一以 60 个交易日前收盘为基准 100，"
    "直接比较各风格相对强弱；鼠标悬停可查看各指数当日数值（按强弱降序排列）。历史收盘：同花顺特色指数走 "
    "hithink 历史接口（与宽基指数同源），北证50 走新浪日线。</p>\n"
    '<div class="chartLeg" id="leg_cStyle"></div><canvas id="cStyle"></canvas>\n'
    + drop_note
)

anchor_html = '<div class="chartLeg" id="leg_cIdx"></div><canvas id="cIdx"></canvas>\n</div>'
assert html.count(anchor_html) == 1, "cIdx canvas 锚点异常"
html = html.replace(anchor_html,
    '<div class="chartLeg" id="leg_cIdx"></div><canvas id="cIdx"></canvas>\n' + style_html + '</div>')
print("[4] 风格指数 HTML 段已注入（表 %d 行）" % len(style_indices))

# ---------------- 5. 注入风格曲线 JS + renderStyleTip ----------------
style_js = (
    "// 风格指数曲线（归一化 · 首日=100）：数据按宽基指数同一 60 日窗口对齐（D.style_lines）\n"
    "if(D.style_lines && D.style_lines.length){\n"
    "  const sRaw=D.style_lines.map(l=>l.data.slice());\n"
    "  const sNorm=sRaw.map(arr=>{ const b=arr.find(v=>v!==null); return b?arr.map(v=>v==null?null:+(v/b*100).toFixed(2)):[]; });\n"
    "  const styleColors=['#2b6cb0','#d8392b','#16a34a','#9333ea','#0891b2','#ca8a04','#db2777','#475569'];\n"
    "  const sch=makeChart('cStyle', lineCfg(D.style_dates, D.style_lines.map((l,i)=>({\n"
    "    label:l.name, data:sNorm[i], borderColor:styleColors[i%styleColors.length], fill:false, pointRadius:0, tension:.2, borderWidth:1.5\n"
    "  }))), renderStyleTip);\n"
    "  sch._sd=D.style_dates;  // 供自定义 tooltip 取日期\n"
    "  sch.options.scales.y.title={display:true,text:'归一化（首日=100）',font:{size:10}};\n"
    "  sch.options.plugins.tooltip.enabled=false;  // 用自定义 #idxTip 代替原生 tooltip\n"
    "} else {\n"
    "  document.getElementById('cStyle').parentElement.innerHTML='<p class=\"miss\">风格指数曲线：暂无历史数据（本次采集后自动累积）</p>';\n"
    "}\n"
    "function renderStyleTip(idx, e){\n"
    "  const tip=document.getElementById('idxTip');\n"
    "  if(idx==null || idx<0){ tip.style.display='none'; return; }\n"
    "  const ch=INSTANCES['cStyle']; if(!ch) return;\n"
    "  const rows=ch.data.datasets\n"
    "    .map(d=>({name:d.label, val:d.data[idx]}))\n"
    "    .filter(r=>r.val!==null && r.val!==undefined)\n"
    "    .sort((a,b)=>b.val-a.val);\n"
    "  const date=(ch._sd||[])[idx];\n"
    "  tip.innerHTML='<div class=\"t-date\">'+date+'</div>'+rows.map(r=>'<div class=\"t-row\"><span>'+r.name+'</span><b>'+Number(r.val).toFixed(2)+'</b></div>').join('');\n"
    "  tip.style.display='block';\n"
    "  let lx=e.clientX+14, ly=e.clientY+14;\n"
    "  const w=tip.offsetWidth||160;\n"
    "  if(lx+w>window.innerWidth) lx=e.clientX-w-14;\n"
    "  if(ly+tip.offsetHeight>window.innerHeight) ly=e.clientY-tip.offsetHeight-14;\n"
    "  tip.style.left=lx+'px';\n"
    "  tip.style.top=ly+'px';\n"
    "}\n"
)
anchor_js = "  tip.style.top=ly+'px';\n}\nmakeChart('cSec', {"
assert html.count(anchor_js) == 1, "renderIdxTip→cSec 锚点异常"
html = html.replace(anchor_js, "  tip.style.top=ly+'px';\n}\n" + style_js + "makeChart('cSec', {")
print("[5] 风格曲线 JS + renderStyleTip 已注入")

# ---------------- 6. buildLegends ids 加入 cStyle ----------------
ids_old = "var ids=['cTurn','cUp','cLim','cHL','cIdx','cSec','cNet','cJzxt','cRps'];"
ids_new = "var ids=['cTurn','cUp','cLim','cHL','cIdx','cStyle','cSec','cNet','cJzxt','cRps'];"
assert html.count(ids_old) == 1, "ids 锚点异常"
html = html.replace(ids_old, ids_new)
print("[6] buildLegends ids 已加入 cStyle")

# ---------------- 7. openZoom 增加 cStyle 分支 ----------------
zoom_old = (
    "    if(id==='cIdx'){\n"
    "      __zoomInst.options.scales.y.title={display:true,text:'归一化（首日=100）',font:{size:10}};\n"
    "      __zoomInst.options.plugins.tooltip.enabled=false;\n"
    "      __zoomInst.update();\n"
    "    }\n"
)
zoom_new = zoom_old + (
    "    // 风格指数图：同上（归一化曲线，大图不挂自定义 tooltip）\n"
    "    if(id==='cStyle'){\n"
    "      __zoomInst.options.scales.y.title={display:true,text:'归一化（首日=100）',font:{size:10}};\n"
    "      __zoomInst.options.plugins.tooltip.enabled=false;\n"
    "      __zoomInst.update();\n"
    "    }\n"
)
assert html.count(zoom_old) == 1, "zoom cIdx 锚点异常"
html = html.replace(zoom_old, zoom_new)
print("[7] openZoom 已增加 cStyle 分支")

# ---------------- 8. 写回 ----------------
open(MID, "w", encoding="utf-8").write(html)
print("[8] 已写回", MID, "size =", os.path.getsize(MID))
