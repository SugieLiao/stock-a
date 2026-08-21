#!/usr/bin/env python3
# 读取 data/YYYY-MM-DD_hithink.json (+ 可选 westock.json) 与历史归档，渲染 A股每日复盘 HTML。
# 输出 /Users/sugieliao/WorkBuddy/A股每日复盘/A股复盘_YYYY-MM-DD.html，并更新 README 索引。
import json, os, sys, datetime, glob

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
VENDOR = os.path.join(BASE, "vendor", "chart.umd.min.js")
CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"
RED = "#d8392b"; GREEN = "#16a34a"; GREY = "#888"

def load_chartjs():
    # 优先内联本地 vendor 副本，使报告完全离线自包含；缺失则退回 CDN。
    if os.path.exists(VENDOR):
        return open(VENDOR, encoding="utf-8").read()
    return None

def load(date):
    h = json.load(open(os.path.join(DATA, f"{date}_hithink.json"), encoding="utf-8"))
    # 个股新高/新低：优先通达信 tdx_screener（当日），回退 westock（T-1）
    h.setdefault("hl_source", ""); h.setdefault("hl_is_t1", False); h.setdefault("westock_source_date", None)
    tdx = os.path.join(DATA, f"{date}_tdxhl.json")
    used_tdx = False
    if os.path.exists(tdx):
        try:
            t = json.load(open(tdx, encoding="utf-8"))
            hn = t.get("high_new"); ln = t.get("low_new")
            h["high_new"] = hn.get("count") if isinstance(hn, dict) else hn
            h["low_new"] = ln.get("count") if isinstance(ln, dict) else ln
            h["hl_source"] = t.get("source", "通达信 tdx_screener（当日）")
            h["hl_is_t1"] = False
            h["tdx_hl"] = t
            used_tdx = True
        except Exception:
            pass
    if not used_tdx:
        w = os.path.join(DATA, f"{date}_westock.json")
        if os.path.exists(w):
            try:
                we = json.load(open(w, encoding="utf-8"))
                h["high_new"] = we.get("high_new", h.get("high_new"))
                h["low_new"] = we.get("low_new", h.get("low_new"))
                h["hl_source"] = "腾讯自选股 westock"
                h["hl_is_t1"] = True
                h["westock_source_date"] = we.get("source_date")
            except Exception:
                pass
    # 板块三 / 四 统一口径：同花顺 thsdk 90 行业（成交额 + 主力净流入）
    s = os.path.join(DATA, f"{date}_sectors_ths.json")
    if os.path.exists(s):
        try:
            ss = json.load(open(s, encoding="utf-8"))
            h["top_sectors"] = ss.get("top_sectors", h.get("top_sectors"))
            h["net_inflow_sectors"] = ss.get("net_inflow_sectors", h.get("net_inflow_sectors"))
            h["net_source"] = ss.get("source", h.get("net_source"))
            h["net_backup"] = False
            h["net_backup_source"] = None
        except Exception:
            pass
    # 个股分类映射（行业 / 概念板块），用于新高新低、涨跌停清单 enrichment
    cf = os.path.join(DATA, "stock_classify.json")
    if os.path.exists(cf):
        try:
            h["stock_classify"] = json.load(open(cf, encoding="utf-8"))
        except Exception:
            h["stock_classify"] = {}
    else:
        h["stock_classify"] = {}
    return h

def history():
    dates, turnover, up, down, flat, lu, ld, hl_hn, hl_ln = [], [], [], [], [], [], [], [], []
    files = sorted(glob.glob(os.path.join(DATA, "*_hithink.json")))
    recs = {}
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
            recs[d["date"]] = d
        except Exception:
            continue
    for dt in sorted(recs):
        # 跳过周末：A股不开盘，若采集脚本误跑会生成无意义的重复数据点
        wd = datetime.datetime.strptime(dt, "%Y-%m-%d").weekday()
        if wd >= 5:
            continue
        d = recs[dt]
        # 合并同日 新高/新低，使曲线可跨日累积：优先通达信 tdxhl，回退 westock(T-1)
        tf = os.path.join(DATA, f"{dt}_tdxhl.json")
        if os.path.exists(tf):
            try:
                t = json.load(open(tf, encoding="utf-8"))
                hn = t.get("high_new"); ln = t.get("low_new")
                if d.get("high_new") is None:
                    d["high_new"] = hn.get("count") if isinstance(hn, dict) else hn
                if d.get("low_new") is None:
                    d["low_new"] = ln.get("count") if isinstance(ln, dict) else ln
            except Exception:
                pass
        if d.get("high_new") is None:
            wf = os.path.join(DATA, f"{dt}_westock.json")
            if os.path.exists(wf):
                try:
                    we = json.load(open(wf, encoding="utf-8"))
                    if d.get("high_new") is None: d["high_new"] = we.get("high_new")
                    if d.get("low_new") is None: d["low_new"] = we.get("low_new")
                except Exception:
                    pass
        m = d.get("market") or {}
        # market 字段兜底（与上方 high_new/low_new 的 westock 链一致）：hithink 采集失败的历史日，
        # 逐个字段读 {dt}_westock.json 补，避免历史曲线出现 None 断点
        need = [k for k in ("total_turnover_yi", "up", "down", "flat", "limit_up", "limit_down")
                if m.get(k) is None]
        if need:
            wfm = os.path.join(DATA, f"{dt}_westock.json")
            if os.path.exists(wfm):
                try:
                    wem = json.load(open(wfm, encoding="utf-8"))
                    for k in need:
                        if wem.get(k) is not None:
                            m[k] = wem[k]
                except Exception:
                    pass
        dates.append(dt)
        turnover.append(m.get("total_turnover_yi"))
        up.append(m.get("up")); down.append(m.get("down")); flat.append(m.get("flat"))
        lu.append(m.get("limit_up")); ld.append(m.get("limit_down"))
        hl_hn.append(d.get("high_new")); hl_ln.append(d.get("low_new"))
    return {"dates": dates, "turnover": turnover, "up": up, "down": down, "flat": flat,
            "lu": lu, "ld": ld, "hn": hl_hn, "ln": hl_ln}

def pct_color(v):
    if v is None: return ""
    return RED if v > 0 else (GREEN if v < 0 else "")

def fmt_pct(v):
    if v is None: return "—"
    return f"{v:+.2f}%"

def to_thscode(code):
    # 把通达信/tdx_screener 的纯数字代码规范成同花顺 thscode（含交易所后缀）
    if not code:
        return code
    if "." in str(code):
        return code
    c = str(code)
    if c[0] == "6":
        return c + ".SH"
    if c[0] in ("0", "3"):
        return c + ".SZ"
    if c[0] in ("4", "8"):
        return c + ".BJ"
    return c + ".SH"

def lookup_cls(code, classify):
    c = to_thscode(code)
    return classify.get(c) or classify.get(str(code)) or {}

def cls_cells(code, classify):
    # 返回 (行业文本, 概念文本)
    cl = lookup_cls(code, classify)
    ind = "/".join(cl.get("industry", [])[:2]) or "—"
    cons = cl.get("concept", [])
    if len(cons) > 3:
        cons_disp = "、".join(cons[:3]) + f" 等{len(cons)}个"
    else:
        cons_disp = "、".join(cons) or "—"
    return ind, cons_disp

def jzxt_zone(v):
    # 均线占用率区间（参考 极冰10/冰点25/中枢50/过热75/高潮90），返回 (区间名, 颜色)
    if v is None: return ("—", GREY)
    if v < 10: return ("极冰", "#00BFFF")
    if v < 25: return ("冰点", "#4169E1")
    if v < 50: return ("中枢下方", "#ca8a04")
    if v < 75: return ("中枢上方", "#ca8a04")
    if v < 90: return ("过热", "#d8392b")
    return ("高潮", "#d8392b")

def sa_attr(code, sector=False):
    """生成 hover 迷你K线的 data 属性"""
    if not code:
        return ""
    if sector or (isinstance(code, str) and code.startswith("88") and len(code) == 6):
        return ' class="sa-hover" data-code="' + code + '" data-hist-key="sec:' + code + '"'
    # 个股代码格式 300308.SZ / 600519.SH / 838171.BJ
    c = str(code)
    mkt = ""
    if c.endswith(".SZ"): mkt = "sz"; c = c[:-3]
    elif c.endswith(".SH"): mkt = "sh"; c = c[:-3]
    elif c.endswith(".BJ"): mkt = "bj"; c = c[:-3]
    elif c.endswith(".TI"): return ' class="sa-hover" data-hist-key="' + code + '"'  # 通达信指数用内置 hist
    # 纯6位数字代码，自动推断市场
    if not mkt and c.isdigit() and len(c) == 6:
        if c[0] in "6": mkt = "sh"
        elif c[0] in "03": mkt = "sz"
        elif c[:3] == "920": mkt = "bj"
        elif c[0] in "48": mkt = "bj"
        else: mkt = "sz"
    return ' class="sa-hover" data-code="' + c + '" data-mkt="' + mkt + '"'

def build_html(d, hist, midday=False):
    cj = load_chartjs()
    chartjs_tag = f"<script>{cj}</script>" if cj else f'<script src="{CDN}"></script>'
    m = d.get("market") or {}
    idx = d.get("indices") or []
    sec = d.get("top_sectors") or []
    stk = (d.get("market") or {}).get("top_stocks") or []
    hn = d.get("high_new"); ln = d.get("low_new")
    ff = d.get("fund_flow") or {"top": [], "bottom": []}
    net = d.get("net_inflow_sectors") or {"top": [], "bottom": []}
    net_backup = bool(d.get("net_backup"))
    net_backup_source = d.get("net_backup_source") or "未知备选源"
    net_src = d.get("net_source") or "同花顺 thsdk（游客模式）行业板块"
    net_top_n = len(net.get("top") or [])
    if net_backup:
        sec4_badge = (f"<p class='note' style='color:#b7791f'>⚠ 备选数据源：{net_backup_source}。"
                      f"东方财富 push2 限流时启用，板块口径为同花顺行业（与东方财富行业板块不同）。</p>")
        sec4_heading = f"四、主力净流入前 {net_top_n} 板块（行业 · {net_backup_source}·备选）"
    else:
        sec4_badge = ("<p class='note'>数据来源：同花顺 thsdk（游客模式）行业板块。"
                      "板块三、四均为同一套同花顺 90 行业口径，可直接对照同一行业的「成交额」与「主力净流入」。</p>")
        sec4_heading = f"四、主力净流入前 {net_top_n} 板块（行业 · 同花顺 thsdk·当日）"
    hl_source = d.get("hl_source") or "未知"
    hl_is_t1 = d.get("hl_is_t1")
    if hl_is_t1:
        hl_note = f"数据来源：{hl_source}。实际数据日期：{d.get('westock_source_date') or '未知'}（该接口常滞后一日，为 T-1 数据）。"
    else:
        hl_note = f"数据来源：{hl_source}。当日数据（条件选股口径，前复权）。"
    # ── 非当日数据标记：计算各数据源实际数据日期，与报告日不同则在对应板块/图表/卡片打红色感叹号 ──
    report_date = d["date"]
    # 板块三/四 同源于 同花顺 thsdk 行业板块
    ths_asof = None
    sp = os.path.join(DATA, f"{report_date}_sectors_ths.json")
    if os.path.exists(sp):
        try:
            ths_asof = json.load(open(sp, encoding="utf-8")).get("date")
        except Exception:
            ths_asof = None
    # 板块五 RPS 共振（东方财富）
    rps_asof = None
    rpp = os.path.join(DATA, "sector_rps.json")
    if os.path.exists(rpp):
        try:
            rps_asof = json.load(open(rpp, encoding="utf-8")).get("date")
        except Exception:
            rps_asof = None
    if hl_is_t1:
        ws = d.get("westock_source_date")
        hl_asof = ws if ws else (datetime.date.fromisoformat(report_date) - datetime.timedelta(days=1)).isoformat()
    else:
        hl_asof = report_date
    _hd = hist.get("dates") or []
    hist_last = _hd[-1] if _hd else None
    _id = idx[0]["hist_dates"] if idx else []
    idx_last = _id[-1] if _id else None
    def stale_attr(v):
        return f' data-stale="{v}"' if v and v != report_date else ""
    sector_stale = stale_attr(ths_asof)  # 三、四 板块（同花顺 thsdk）
    rps_stale = stale_attr(rps_asof)     # 五、RPS 共振（通达信 TDX 概念板块指数）
    hl_stale  = stale_attr(hl_asof)      # 七、个股新高/新低
    hist_stale = stale_attr(hist_last)  # 一、4 张历史曲线（成交额/涨跌/涨跌停/高低）
    idx_stale = stale_attr(idx_last)    # 二、指数走势曲线
    # ── 数据截止时间戳：收盘版=15:00 / 午间版=11:30（页面快照时间）──
    cutoff_hhmm = "11:30" if midday else "15:00"
    cutoff_variant = "午间" if midday else "收盘"
    cutoff_dt = f"{report_date} {cutoff_hhmm}"
    cutoff_attr = f' data-cutoff="{cutoff_hhmm}"'
    cutoff_banner = (f'<div class="cutoff-banner">数据截止时间：{cutoff_dt}'
                     f'（{cutoff_variant}版快照）</div>')
    # 全市场总成交额(亿) 作为「板块成交额占比%」的分母：板块成交额 / 全市场成交额
    total_amt = max(m.get("total_turnover_yi") or 0, 1)
    # 风格指数曲线数据：与宽基指数同一 60 日窗口对齐；历史覆盖 <60% 的指数（如同花顺
    # 仅部分交易日发布的「北交所昨日涨停」）不纳入曲线，避免断线，其当日表现仍在上表展示。
    idx_dates = idx[0]["hist_dates"] if idx else []
    style_lines, style_dropped = [], []
    if idx_dates:
        for s in d.get("style_indices") or []:
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
    style_drop_note = ""
    if style_dropped:
        style_drop_note = (f"<p class='note' style='color:#888;background:#f6f8fa'>注："
                           f"{'、'.join(style_dropped)}（同花顺仅部分交易日发布、历史不连续）"
                           f"未纳入曲线，其当日表现见上方表格。</p>")
    payload = {
        "date": d["date"], "weekday": d.get("weekday", ""),
        "hist": hist,
        "idx_dates": idx[0]["hist_dates"] if idx else [],
        "idx_lines": [{"name": i["name"], "data": i["hist_close"]} for i in idx],
        "sec_bar": [{"name": s["name"], "v": s["turnover_yi"],
                     "pct": s.get("pct"),
                     "ratio": round(s["turnover_yi"] / total_amt * 100, 2)} for s in sec],
        "net_top": [{"name": x["name"], "v": x["zljlr_yi"], "pct": x.get("pct"),
                     "turnover": x.get("turnover_yi"),
                     "ratio": round((x.get("turnover_yi") or 0) / total_amt * 100, 2)} for x in net.get("top", [])],
        "net_bot": [{"name": x["name"], "v": x["zljlr_yi"], "pct": x.get("pct"),
                     "turnover": x.get("turnover_yi"),
                     "ratio": round((x.get("turnover_yi") or 0) / total_amt * 100, 2)} for x in net.get("bottom", [])],
        "style_indices": d.get("style_indices") or [],
        "style_dates": idx_dates,
        "style_lines": style_lines,
        "style_dropped": style_dropped,
        "top_sectors": sec,
        "net_inflow_sectors": net,
    }
    # 万得全A 日K（市值加权全A代理）
    wande = None
    wp = os.path.join(DATA, "wande.json")
    if os.path.exists(wp):
        try:
            wj = json.load(open(wp, encoding="utf-8"))
            if wj.get("ok"):
                wande = wj
        except Exception:
            pass
    payload["wande"] = wande
    # 均占系统 均线占用率（市场宽度）日线
    jzxt = None
    jzxt_html = ""
    jp = os.path.join(DATA, "jzxt_history.json")
    if os.path.exists(jp):
        try:
            jj = json.load(open(jp, encoding="utf-8"))
            if jj.get("ok") and jj.get("dates"):
                jzxt = jj
        except Exception:
            pass
    if jzxt:
        series_def = [("cdx", "5日"), ("dx", "13日"), ("zx", "50日"), ("cx", "120日")]
        last_d = jzxt["dates"][-1]
        rows = ""
        for key, name in series_def:
            arr = jzxt.get(key) or []
            v = arr[-1] if arr else None
            zn, zc = jzxt_zone(v)
            vtxt = f"{v:.2f}" if isinstance(v, (int, float)) else "—"
            rows += (f"<tr><td>{name}</td><td class='num' style='color:{zc};font-weight:600'>{vtxt}</td>"
                     f"<td style='color:{zc}'>{zn}</td></tr>")
        rng = f"{jzxt['dates'][0]} → {last_d}（{len(jzxt['dates'])} 个交易日）"
        jzxt_html = (
            "<h4 style='margin-top:16px'>均线占用率（市场宽度 · 均占系统）</h4>"
            "<table><tr><th>周期</th><th>占用率(%)</th><th>区间</th></tr>" + rows + "</table>\n"
            "<div class=\"chartLeg\" id=\"leg_cJzxt\"></div><canvas id='cJzxt'></canvas>\n"
            "<p class='note'>数据来源：均占系统 ghxb.site/jzxt（/api/admin/daily/range，Bearer 鉴权）。"
            "占用率＝站上对应周期均线的股票占比(%)；参考区间 极冰10 / 冰点25 / 中枢50 / 过热75 / 高潮90。"
            "快线、慢线(kx/mx)当前无数据。范围：" + rng + "。</p>"
        )
    else:
        jzxt_html = ("<p class='miss' style='margin-top:16px'>均线占用率（市场宽度）：数据源暂不可达"
                     "（token 缺失或接口异常），连上后由 collect_jzxt.py 取数并覆盖本占位。</p>")
    payload["jzxt"] = jzxt
    # TR情绪监测（通达信扩展数据 38/39/40：HTR10/HTR20/HTR40，市场宽度/情绪）
    tr = None
    tr_html = ""
    tp = os.path.join(DATA, "tr_emotion.json")
    if os.path.exists(tp):
        try:
            tj = json.load(open(tp, encoding="utf-8"))
            if tj.get("ok") and tj.get("dates"):
                tr = tj
        except Exception:
            pass
    def tr_zone(v):
        # TR情绪区间：沸点87(超买) / 相变50(多空分界) / 冰点13(超卖)
        if v is None: return ("—", GREY)
        if v >= 87: return ("超买(沸点)", "#d8392b")
        if v >= 50: return ("偏强", "#ca8a04")
        if v >= 13: return ("偏弱", "#2b6cb0")
        return ("超卖(冰点)", "#4169E1")
    if tr:
        tr_series = [("htr10", "HTR10(短期)", "#ff6b6b"),
                      ("htr20", "HTR20(中期)", "#2b6cb0"),
                      ("htr40", "HTR40(长期)", "#9333ea")]
        last_d = tr["dates"][-1]
        rows = ""
        for key, name, color in tr_series:
            arr = tr.get(key) or []
            v = arr[-1] if arr else None
            zn, zc = tr_zone(v)
            vtxt = f"{v:.2f}" if isinstance(v, (int, float)) else "—"
            rows += (f"<tr><td><span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
                     f"background:{color};margin-right:6px'></span>{name}</td>"
                     f"<td class='num' style='color:{zc};font-weight:600'>{vtxt}</td>"
                     f"<td style='color:{zc}'>{zn}</td></tr>")
        rng = f"{tr['dates'][0]} → {last_d}（{len(tr['dates'])} 个交易日）"
        tr_html = (
            "<h4 style='margin-top:16px'>TR情绪监测（市场宽度 · 通达信扩展数据）</h4>"
            "<table><tr><th>指标</th><th>最新值(%)</th><th>区间</th></tr>" + rows + "</table>\n"
            "<div class='tr-range-btns' id='trRangeBtns'>"
            "<button class='tr-range-btn' data-range='120'>近120天</button>"
            "<button class='tr-range-btn active' data-range='half'>近半年</button>"
            "<button class='tr-range-btn' data-range='year'>近一年</button>"
            "<button class='tr-range-btn' data-range='2year'>近两年</button>"
            "</div>\n"
            "<div class=\"chartLeg\" id=\"leg_cTr\"></div><canvas id='cTr'></canvas>\n"
            "<p class='note'>数据来源：通达信扩展数据 38/39/40 号（TR占比 日线，基于平均股价指数880003）。"
            "TR＝个股收盘价突破N日TR波动上限的占比(%)，衡量市场广度情绪；"
            "参考线 沸点87(超买) / 相变50(多空分界) / 冰点13(超卖)。"
            "范围：" + rng + "。</p>"
        )
    else:
        tr_html = ("<p class='miss' style='margin-top:16px'>TR情绪监测：数据源暂不可达"
                   "（collect_tr_emotion.py 未运行或 VM 不可达），连上后覆盖本占位。</p>")
    payload["tr_emotion"] = tr
    # 板块 RPS 共振（通达信 TDX 概念板块指数，主源；同花顺 THS 兜底；5/10/20/50 日，至少3个>87）
    rps = None
    rps_html = ""
    rps_chart_cfg = None
    rp = os.path.join(DATA, "sector_rps.json")
    if os.path.exists(rp):
        try:
            rr = json.load(open(rp, encoding="utf-8"))
            if rr.get("ok") and rr.get("passed"):
                rps = rr
        except Exception:
            pass
    if rps:
        thr = rps["threshold"]; mp = rps["min_pass"]
        src = rps.get("source") or "通达信 TDX（概念板块指数，主源）"
        # 午间版不更新 RPS，沿用上一交易日收盘结果（sector_rps.json 为上一交易日）
        rps_midday_note = ("<p class='note' style='color:#b7791f'>⚠ 午间版不更新 RPS 数据，"
                           f"本区沿用上一交易日（{rps.get('date')}）收盘 RPS 共振结果。</p>"
                           ) if midday else ""
        def rps_cell(v):
            if v is None:
                return "<td class='num'>—</td>"
            col = "#d8392b" if v > thr else ("#999" if v < 50 else "#222")
            bold = "font-weight:600" if v > thr else ""
            return f"<td class='num' style='color:{col};{bold}'>{v:.2f}</td>"
        shown = rps["passed"][:40]
        rows = ""
        for p in shown:
            rows += (f"<tr><td{sa_attr(p.get('code') or '', sector=True)}>{p['name']}</td><td class='num'>{p['cat']}</td>"
                     + rps_cell(p["rps5"]) + rps_cell(p["rps10"]) + rps_cell(p["rps20"]) + rps_cell(p["rps50"])
                     + f"<td class='num' style='font-weight:600'>{p['n_pass']}</td></tr>")
        more = len(rps["passed"]) - len(shown)
        moretxt = (f"<tr><td colspan=7 style='color:#888;text-align:center'>… 其余 {more} 个（共 {len(rps['passed'])} 个通过筛选）</td></tr>"
                   if more > 0 else "")
        ulabel = rps.get("universe_label", "全市场板块")
        rng = f"{ulabel}有效板块 {rps['valid_boards']} 个，日期 {rps['date']}"
        rps_html = (
            f"<h4 style='margin-top:16px'>强势板块 · RPS 共振（{ulabel}）</h4>"
            + rps_midday_note +
            "<table><tr><th>板块</th><th>类别</th><th>RPS5</th><th>RPS10</th><th>RPS20</th><th>RPS50</th><th>达标周期</th></tr>"
            + rows + moretxt + "</table>\n"
            "<div class=\"chartLeg\" id=\"leg_cRps\"></div><canvas id='cRps'></canvas>\n"
            f"<p class='note'>筛选条件：5/10/20/50 日 RPS 中至少 {mp} 个 &gt; {thr}。"
            f"RPS＝板块N日涨幅在{ulabel}中的排名百分位（欧奈尔定义，前复权）。红字＝该周期 &gt; "
            f"{thr}（强势）。数据来源：{src}。{rng}。"
            f"｜ 操作：双击图表可放大；点击上方图例可高亮对应系列；悬停某一行可列出该板块全部 RPS 值。</p>"
        )
        # 横向分组条形图（前25个通过板块，最弱在下）
        top_rev = list(reversed(rps["passed"][:25]))
        names = [p["name"] for p in top_rev]
        def ds(k, color):
            return {"label": k, "data": [p[k] for p in top_rev], "backgroundColor": color}
        rps_chart_cfg = {
            "type": "bar",
            "data": {"labels": names, "datasets": [
                ds("rps5", "#2b6cb0"), ds("rps10", "#16a34a"),
                ds("rps20", "#ca8a04"), ds("rps50", "#d8392b")]},
            "options": {
                "indexAxis": "y", "responsive": True,
                "plugins": {"legend": {"labels": {"font": {"size": 11}}}},
                "scales": {
                    "x": {"min": 0, "max": 100, "grid": {"color": "#eee"},
                          "title": {"display": True, "text": "RPS", "font": {"size": 10}}},
                    "y": {"ticks": {"font": {"size": 10}, "autoSkip": False}}}
            }
        }
    else:
        rps_html = ("<p class='miss' style='margin-top:16px'>强势板块 RPS：数据源暂不可达"
                    "（collect_sector_rps.py 未运行或接口异常），连上后覆盖本占位。</p>")
    payload["rps"] = rps
    payload["rps_chart_cfg"] = rps_chart_cfg
    payload["rps_thr"] = rps["threshold"]
    only1 = len(hist["dates"]) <= 1

    # ---- 指数表 ----
    idx_rows = "".join(
        f"<tr><td{sa_attr(i.get('code') or '')}>{i['name']}</td><td class='num'>{i['close']}</td>"
        f"<td class='num' style='color:{pct_color(i['pct'])}'>{fmt_pct(i['pct'])}</td>"
        f"<td class='num'>{i['turnover_yi']}亿</td></tr>" for i in idx)
    # ---- 风格指数表（板块二子表：短线风格/情绪）----
    style = d.get("style_indices") or []
    style_rows = ""
    if style:
        for s in style:
            nm = s.get("name", "?")
            close = s.get("close")
            pct = s.get("pct")
            sa = sa_attr(s.get("code") or "")
            if pct is None:
                style_rows += f"<tr><td{sa}>{nm}</td><td class='num'>—</td><td class='num'>—</td></tr>"
            else:
                arr = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
                style_rows += (f"<tr><td{sa}>{nm}</td><td class='num'>{close}</td>"
                               f"<td class='num' style='color:{pct_color(pct)};font-weight:600'>{arr}{fmt_pct(pct)}</td></tr>")
    else:
        style_rows = "<tr><td colspan=3 class='num'>风格指数数据暂缺</td></tr>"
    # ---- 板块表 ----
    # 板块三/四自带 hist 数据时，直接用自身 code（去 URFI 前缀）生成 hover 属性
    def _sec_hover(s):
        c = (s.get("code") or "").replace("URFI", "")
        return sa_attr(c, sector=True) if c else ""
    sec_rows = "".join(
        f"<tr><td>{k+1}</td><td{_sec_hover(s)}>{s['name']}</td><td class='num'>{s['turnover_yi']}亿</td>"
        f"<td class='num'>{s['turnover_yi']/total_amt*100:.2f}%</td>"
        f"<td class='num' style='color:{pct_color(s['pct'])}'>{fmt_pct(s['pct'])}</td></tr>"
        for k, s in enumerate(sec))
    # ---- 成交量前100个股（51~100 折叠）----
    classify = d.get("stock_classify") or {}
    stk_top = stk[:50]
    stk_rest = stk[50:100]
    def _stk_row(rank, s, fold=False):
        ind, cons = cls_cells(s.get("code"), classify)
        cls = " class='fold-row'" if fold else ""
        dsp = " style='display:none'" if fold else ""
        return (f"<tr{cls}{dsp}><td>{rank}</td><td{sa_attr(s.get('code') or '')}>{s['name']}</td><td class='num'>{s['code']}</td>"
                f"<td class='num'>{s['turnover_yi']}亿</td>"
                f"<td class='num' style='color:{pct_color(s['pct'])}'>{fmt_pct(s['pct'])}</td>"
                f"<td>{ind}</td><td style='font-size:12px'>{cons}</td></tr>")
    stk_rows = "".join(_stk_row(k + 1, s) for k, s in enumerate(stk_top))
    stk_rows_rest = "".join(_stk_row(k + 51, s, fold=True) for k, s in enumerate(stk_rest))

    # ---- 新高 / 新低 个股清单（含行业 / 概念板块）----
    tdx_hl = d.get("tdx_hl") or {}
    def _hl_stocks(key):
        v = tdx_hl.get(key)
        if isinstance(v, dict):
            return v.get("stocks", []) or []
        return []
    hn_stocks = _hl_stocks("high_new")
    ln_stocks = _hl_stocks("low_new")
    def hl_rows(stocks):
        rows = ""
        for k, s in enumerate(stocks):
            ind, cons = cls_cells(s.get("code"), classify)
            rows += (f"<tr><td>{k+1}</td><td{sa_attr(s.get('code') or '')}>{s.get('name','')}</td><td class='num'>{s.get('code','')}</td>"
                     f"<td class='num' style='color:{pct_color(s.get('chg'))}'>{fmt_pct(s.get('chg'))}</td>"
                     f"<td>{ind}</td><td style='font-size:12px'>{cons}</td></tr>")
        return rows or "<tr><td colspan=6 style='color:#888'>无数据</td></tr>"
    hn_rows = hl_rows(hn_stocks)
    ln_rows = hl_rows(ln_stocks)

    # ---- 涨停 / 跌停 个股清单（含行业 / 概念板块）----
    lu_list = m.get("limit_up_list") or []
    ld_list = m.get("limit_down_list") or []
    def lim_rows(stocks):
        rows = ""
        for k, s in enumerate(stocks):
            ind, cons = cls_cells(s.get("code"), classify)
            rows += (f"<tr><td>{k+1}</td><td{sa_attr(s.get('code') or '')}>{s.get('name','')}</td><td class='num'>{s.get('code','')}</td>"
                     f"<td class='num' style='color:{pct_color(s.get('pct'))}'>{fmt_pct(s.get('pct'))}</td>"
                     f"<td class='num'>{s.get('turnover_yi',0)}亿</td>"
                     f"<td>{ind}</td><td style='font-size:12px'>{cons}</td></tr>")
        return rows or "<tr><td colspan=7 style='color:#888'>无数据</td></tr>"
    lu_rows = lim_rows(lu_list)
    ld_rows = lim_rows(ld_list)
    # ---- 主力净流入板块（东方财富·当日）----
    def _net_amt_cell(x):
        tv = x.get("turnover_yi")
        if tv is None:
            return "<td class='num'>—</td>", "<td class='num'>—</td>"
        return (f"<td class='num'>{tv}亿</td>",
                f"<td class='num'>{tv/total_amt*100:.2f}%</td>")
    net_top_rows = "".join(
        (lambda c: f"<tr><td>{k+1}</td><td{_sec_hover(x)}>{x['name']}</td>"
         f"<td class='num' style='color:{RED}'>+{x['zljlr_yi']:.2f}亿</td>"
         f"<td class='num' style='color:{pct_color(x.get('pct'))}'>{fmt_pct(x.get('pct'))}</td>"
         f"{c[0]}{c[1]}</tr>")(_net_amt_cell(x))
        for k, x in enumerate(net.get("top", [])))
    net_bot_rows = "".join(
        (lambda c: f"<tr><td>{k+1}</td><td{_sec_hover(x)}>{x['name']}</td>"
         f"<td class='num' style='color:{GREEN}'>{x['zljlr_yi']:.2f}亿</td>"
         f"<td class='num' style='color:{pct_color(x.get('pct'))}'>{fmt_pct(x.get('pct'))}</td>"
         f"{c[0]}{c[1]}</tr>")(_net_amt_cell(x))
        for k, x in enumerate(net.get("bottom", [])))

    if only1:
        note = "<p class='note'>⚠️ 曲线为自建归档逐日累积，当前仅首日数据；随每日自动化运行，曲线将自动变长。</p>"
    else:
        note = ("<p class='note'>曲线为自建归档逐日累积（近 60 交易日）。"
                "历史点：涨跌家数/涨停跌停/创250日新高新低来自腾讯自选股 westock，"
                "全市场成交额来自东方财富妙想，指数收盘来自 westock K线；"
                "历史点新高/新低为创250日口径，末点（当日）为创一年口径（近似一致）；"
                "末点（当日）与报告其余部分同源（同花顺/通达信）。</p>")

    if wande:
        wande_html = ("<h4>平均股价(880003) 日K · 等权全A代理（通达信）</h4>"
                      "<canvas id='cWande'></canvas>")
    else:
        wande_html = ("<p class='miss'>平均股价(880003) 日K：数据源暂不可达"
                      "（通达信行情服务器当前不可达，连上后由 collect_wande.py 经 pytdx 取数并覆盖本占位）。"
                      "说明：平均股价=全市场个股价格的等权平均，是「全A等权」的贴近代理。</p>")

    hn_disp = f"{hn} 只" if isinstance(hn, int) else "数据缺失"
    ln_disp = f"{ln} 只" if isinstance(ln, int) else "数据缺失"

    LEGEND_JS = r"""
// ---- 自定义图例 + 点击高亮对应曲线 ----
function chartColor(ds){
  var c = ds.borderColor;
  if(c===undefined || (typeof c==='string' && c.indexOf('rgba(0,0,0,0)')>=0)) c = ds.backgroundColor;
  return c;
}
function hexToRgba(c,a){
  if(typeof c!=='string') return c;
  var h=c.replace('#','');
  if(h.length===3) h=h.split('').map(function(x){return x+x;}).join('');
  if(h.length===6){var r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);return 'rgba('+r+','+g+','+b+','+a+')';}
  return c;
}
function darken(c,f){
  if(typeof c!=='string'||c.charAt(0)!=='#') return c;
  var h=c.replace('#',''); if(h.length===3) h=h.split('').map(function(x){return x+x;}).join('');
  if(h.length!==6) return c;
  var r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);
  r=Math.max(0,Math.round(r*f));g=Math.max(0,Math.round(g*f));b=Math.max(0,Math.round(b*f));
  return 'rgb('+r+','+g+','+b+')';
}
// RPS 自定义外部 tooltip：紧凑显示全部 4 个 RPS，值>87 红色
function rpsExternalTooltip(context){
  var t=context.tooltip;
  var el=document.getElementById('rpsTip');
  if(!el){
    el=document.createElement('div');
    el.id='rpsTip';
    el.style.cssText='position:absolute;pointer-events:none;background:rgba(255,255,255,.97);border:1px solid #e1e4e8;border-radius:8px;box-shadow:0 4px 14px rgba(0,0,0,.12);padding:8px 10px;font-size:13px;color:#1f2329;z-index:9999;max-width:260px;line-height:1.55;font-family:-apple-system,BlinkMacSystemFont,sans-serif';
    document.body.appendChild(el);
  }
  if(!t||t.opacity===0){ el.style.opacity=0; return; }
  var items=t.dataPoints;
  if(!items||!items.length){ el.style.opacity=0; return; }
  var board=items[0].label;
  var thr=87;
  var order=['rps50','rps20','rps10','rps5'];
  var map={};
  items.forEach(function(it){ map[it.dataset.label]=it.parsed.x; });
  var html='<div style="font-weight:600;margin-bottom:4px">'+board+'</div>';
  order.forEach(function(k){
    if(map[k]===undefined) return;
    var v=Number(map[k]);
    var col=v>thr?'#d8392b':'#1f2329';
    html+='<div style="color:'+col+'">■ '+k+': '+v.toFixed(2)+'</div>';
  });
  el.innerHTML=html;
  var cv=context.chart.canvas;
  var rect=cv.getBoundingClientRect();
  el.style.opacity=1;
  el.style.left=(rect.left+window.pageXOffset+t.caretX)+'px';
  el.style.top=(rect.top+window.pageYOffset+t.caretY+14)+'px';
}
function setHighlight(id, idx){
  var ch=INSTANCES[id]; if(!ch) return;
  var same = ch._hlIdx===idx;
  ch._hlIdx = same?null:idx;
  ch.data.datasets.forEach(function(ds,i){
    if(ds.__ob===undefined) ds.__ob={bc:ds.borderColor,bg:ds.backgroundColor,bw:ds.borderWidth,pr:ds.pointRadius};
    var ob=ds.__ob;
    if(ch._hlIdx===null){
      ds.borderColor=ob.bc; ds.backgroundColor=ob.bg; ds.borderWidth=ob.bw; ds.pointRadius=ob.pr;
    } else if(i===ch._hlIdx){
      // 选中系列：保留原色，并加一条更深的描边 + 加粗，使其明显“跳”出来
      ds.borderColor = (ob.bc!==undefined && ob.bc!==null) ? ob.bc : darken(ob.bg, 0.5);
      ds.backgroundColor = ob.bg;
      ds.borderWidth = (typeof ob.bw==='number'?ob.bw:1) + 2.5;
      ds.pointRadius = (typeof ob.pr==='number'?ob.pr:2) + 2;
    } else {
      ds.borderColor=hexToRgba(ob.bc,0.10);
      ds.backgroundColor=hexToRgba(ob.bg,0.10);
      ds.borderWidth=1; ds.pointRadius=0;
    }
  });
  ch.update();
  var box=document.getElementById('leg_'+id);
  if(box) box.querySelectorAll('.chip').forEach(function(c){
    c.classList.toggle('active', !same && (+c.dataset.idx)===idx);
  });
}
function buildLegends(){
  var ids=['cTurn','cUp','cLim','cHL','cIdx','cStyle','cSec','cNet','cJzxt','cTr','cRps'];
  ids.forEach(function(id){
    var ch=INSTANCES[id]; var box=document.getElementById('leg_'+id);
    if(!ch||!box) return;
    ch.data.datasets.forEach(function(ds,i){
      var col=chartColor(ds);
      if(col===undefined) return;
      if(typeof col==='string' && col.indexOf('rgba(0,0,0,0)')>=0) return;
      var chip=document.createElement('span');
      chip.className='chip'; chip.dataset.idx=i;
      var dot=document.createElement('span'); dot.className='dot'; dot.style.background=col;
      var txt=document.createElement('span'); txt.textContent=ds.label||('系列'+(i+1));
      chip.appendChild(dot); chip.appendChild(txt);
      chip.addEventListener('click',(function(i){return function(){setHighlight(id,i);};})(i));
      box.appendChild(chip);
    });
  });
}
// ---- RPS 图表：悬停某一行列出该板块全部 RPS 值 ----
if(D.rps_chart_cfg){
  var rch=INSTANCES['cRps'];
  if(rch){
    // 横向条形图(indexAxis:y)必须用 nearest+intersect，按鼠标最近柱子触发；
    // 值取 parsed.x（X轴=RPS数值），parsed.y 是行号索引。
    rch.options.interaction={mode:'index', intersect:false};
    rch.options.plugins.tooltip.enabled=false;
    rch.options.plugins.tooltip.mode='index';
    rch.options.plugins.tooltip.intersect=false;
    rch.options.plugins.tooltip.external=rpsExternalTooltip;
    rch.update();
  }
}
buildLegends();
"""

    # 顶部分页导航（内嵌到 ctrl-bar 同一行左侧）
    if midday:
        nav_href, nav_label = "../", "查看收盘版"
    else:
        nav_href, nav_label = "午盘/", "查看午间版"
    nav_html = ""  # 不再独立渲染，已合入 ctrl_bar

    # stock-a 控制按钮：通达信量化（保留不动）+ 重新抽数（同行右侧，无色描边）
    # 导航链接 + 控制按钮合为一行：左=导航链接，右=操作按钮
    ctrl_bar = ("""<div class="ctrl-bar">
<a class="navlink" href="{nav_href}">{nav_label}</a>
<span style="flex:1"></span>
<button id="tdxBtn" class="re-btn" onclick="saTrigger('tdx',this)">📊 通达信量化</button>
<button id="reBtn" class="re-btn" onclick="reextractCheck(this)">🔄 重新抽数</button>
<span class="ctrl-status" id="saStatus"></span>
</div>
<style>
.ctrl-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0 12px}
/* 导航文字链接 */
.navlink{display:inline-flex;align-items:center;gap:6px;text-decoration:none;color:#2b6cb0;font-size:14px;font-weight:600;padding:6px 2px;transition:.15s}
.navlink:hover{color:#234e7a;text-decoration:underline}
/* 无色描边按钮 */
.re-btn{border:1.5px solid #a0aec0;border-radius:10px;padding:9px 18px;font-size:14px;font-weight:600;color:#4a5568;cursor:pointer;background:transparent;transition:all .15s;white-space:nowrap}
.re-btn:hover{border-color:#3182ce;color:#2b6cb0;background:#ebf4ff}
.re-btn:active{transform:scale(.97)}
.re-btn:disabled{opacity:.5;cursor:wait}
.ctrl-status{font-size:13px;color:#888;min-height:18px}
.ctrl-status.ok{color:#48c779;font-weight:600}
.ctrl-status.err{color:#f56565;font-weight:600}
.ctrl-status.busy{color:#ff8a3d}
{SA_CSS}
</style>
<script>
function saSet(t,m){document.querySelectorAll('.ctrl-status').forEach(function(e){e.textContent=m||'';e.className='ctrl-status '+(t||'')})}
function lastTradingDate(){
  var d=new Date();var dow=d.getDay();
  if(dow===0) d.setDate(d.getDate()-2);      /* Sun → Fri */
  else if(dow===6) d.setDate(d.getDate()-1);  /* Sat → Fri */
  var off=d.getTimezoneOffset()*60000;
  return new Date(d.getTime()-off).toISOString().slice(0,10);
}
function saTrigger(cmd, el, opts){
  opts=opts||{};
  var btns = el ? [el] : document.querySelectorAll('.re-btn');
  btns.forEach(function(b){b.disabled=true});
  saSet('busy','正在提交…');
  var tries=0;
  function done(ok,msg){saSet(ok?'ok':'err',msg);btns.forEach(function(b){b.disabled=false})}
  function attempt(){
    tries++;
    var url=location.origin+'/api/trigger?cmd='+encodeURIComponent(cmd);
    if(cmd==='reextract') url+='&type='+encodeURIComponent(PAGE_MODE);
    if(opts.date) url+='&date='+encodeURIComponent(opts.date);
    fetch(url,{method:'POST'})
      .then(function(r){return r.json()})
      .then(function(d){
        var label=(cmd==='tdx'?'通达信量化 Task1-5':'重新抽数'+(opts.date?'（'+opts.date+'）':''));
        if(d&&d.ok) done(true,'✅ 已提交：'+label+'。完成后邮件通知 hao.liao01@qq.com');
        else if(tries<3) setTimeout(attempt,800);
        else done(false,'❌ 提交失败：'+(d&&d.error||'未知错误，请稍后重试'));
      })
      .catch(function(e){ if(tries<3) setTimeout(attempt,800); else done(false,'❌ 网络错误：'+e.message) });
  }
  attempt();
}
function localToday(){var d=new Date();var off=d.getTimezoneOffset()*60000;return new Date(d.getTime()-off).toISOString().slice(0,10)}
function doReextract(el, date){ saTrigger('reextract', el, {date:date}); }
function reextractCheck(el){
  var dow=new Date().getDay();
  var isWeekend=(dow===0||dow===6);
  if(isWeekend){
    var target=REPORT_DATE||lastTradingDate();
    if(confirm('今天不是交易日（周末），系统将抽取上一个交易日（'+target+'）的数据。\\n确定继续吗？')){
      doReextract(el, target);
    }
  } else if(REPORT_DATE===localToday()){
    if(confirm('今天的数据自动化任务已经成功刷新完毕，确定要再跑一次吗？')) doReextract(el);
  } else {
    doReextract(el);
  }
}
{SA_JS}
</script>""")
    # ---- 红绿灯（抽数状态指示）：黄=进行中 绿=成功 红=有错 灰=离线/待机 ----
    sa_css = """
.sa-light{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;padding:4px 12px;border:1px solid #e2e5ea;border-radius:20px;background:#fafbfc;cursor:default;white-space:nowrap;user-select:none;vertical-align:middle;margin-left:10px}
.sa-dot{width:11px;height:11px;border-radius:50%;background:#cbd5e0;display:inline-block;flex:none;transition:background .3s,box-shadow .3s}
.sa-light.running .sa-dot{background:#f6c343;box-shadow:0 0 8px rgba(246,195,67,.85);animation:saBlink 1.2s infinite}
.sa-light.ok .sa-dot{background:#48c779;box-shadow:0 0 8px rgba(72,199,121,.7)}
.sa-light.err .sa-dot{background:#f56565;box-shadow:0 0 8px rgba(245,101,101,.7)}
.sa-light.off .sa-dot{background:#a0aec0}
@keyframes saBlink{0%,100%{opacity:1}50%{opacity:.4}}
/* hover 迷你K线弹窗 */
.sa-hover{cursor:help;text-decoration:underline dotted #aaa;text-underline-offset:3px}
.sa-hover:hover{background:#eef4fb;border-radius:4px}
#saKlineTip{position:fixed;pointer-events:none;z-index:99999;display:none;width:420px;height:340px;background:#fff;border:1px solid #d0d7de;border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.18);padding:10px 10px 6px;overflow:hidden}
#saKlineLbl{text-align:center;font-size:12px;font-weight:600;color:#1f2329;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#saKlineCv{width:100%;height:230px;display:block}
#saKlineFoot{text-align:center;font-size:10px;color:#999;margin-top:2px}"""
    sa_js = """
function renderLight(d){
  var box=document.getElementById('saLight'),dot=document.getElementById('saDot'),txt=document.getElementById('saTxt');
  if(!box||!dot||!txt) return;
  function set(cls,text,title){box.className='sa-light '+(cls||'off');txt.textContent=text;if(title)box.title=title;else box.removeAttribute('title')}
  // 静态部署页：隧道未运行时显示快照就绪，避免被误解为数据离线
  var pageDate=(typeof REPORT_DATE!=='undefined'?REPORT_DATE:'')||'';
  var pageMode=(typeof PAGE_MODE!=='undefined'?PAGE_MODE:'')||'';
  var cutoffText=pageDate+(pageMode==='midday'?' 11:30':(pageMode==='close'?' 15:00':''));
  if(!d||!d.ok){set('ok','快照已就绪','数据截止：'+cutoffText+'；实时抽数服务未连接');return}
  var st=d.state,last=d.last;
  if(st==='running'){
    var rn=d.running||{},src=rn.note||'';
    var label=(rn.cmd==='tdx')?'通达信刷新':(rn.cmd==='external'?'定时自动化':'抽数');
    set('running',label+'进行中'+(src?'（'+src+'）':''),'开始于 '+(rn.started||'?'));
  }else if(st==='done_ok'){
    var warns=(last&&last.warns||[]);
    var title='最近完成：'+(last&&last.finished||'?')+'（耗时 '+(last&&last.elapsed_s!=null?last.elapsed_s+'s':'?')+'）'+(warns.length?'\\n提示：'+warns.join('；'):'');
    set('ok','抽数成功',title);
  }else if(st==='done_error'){
    var issues=(last&&last.issues||[]),err=last&&last.error||'';
    var isQ=issues.length>0&&!(last&&last.rc);
    var msg=isQ?'完成但有缺口':'抽数失败';
    var title='最近完成：'+(last&&last.finished||'?');
    if((last&&last.rc)!=null)title+='（rc='+last.rc+'，耗时 '+(last&&last.elapsed_s!=null?last.elapsed_s+'s':'?')+'）';
    if(issues.length)title+='\\n缺口：'+issues.join('；');
    if(err)title+='\\n错误：'+err;
    set('err',msg,title);
  }else{
    set('off','待机','暂无抽数记录');
  }
}
function pollStatus(){
  fetch(location.origin+'/api/status?ts='+Date.now())
    .then(function(r){return r.json()})
    .then(function(d){renderLight(d)})
    .catch(function(){renderLight(null)})
    .then(function(){setTimeout(pollStatus,30000)});
}
pollStatus();

/* ---- hover 迷你K线弹窗 ---- */
var saTip=null,saTimer=null,saCurReq=0;
function initSaHover(){
  if(saTip)return;
  saTip=document.createElement('div');saTip.id='saKlineTip';
  var lbl=document.createElement('div');lbl.id='saKlineLbl';
  var cv=document.createElement('canvas');cv.id='saKlineCv';
  var ft=document.createElement('div');ft.id='saKlineFoot';
  saTip.appendChild(lbl);saTip.appendChild(cv);saTip.appendChild(ft);
  document.body.appendChild(saTip);
  document.querySelectorAll('.sa-hover').forEach(function(td){
    td.addEventListener('mouseenter',function(e){clearTimeout(saTimer);saTimer=setTimeout(function(){showKlineTip(td,e)},300)});
    td.addEventListener('mouseleave',function(){clearTimeout(saTimer);hideKlineTip()});
    td.addEventListener('mousemove',function(e){posTip(e)});
  });
}
function showKlineTip(td,e){
  var code=td.getAttribute('data-code')||'';
  var mkt=td.getAttribute('data-mkt')||'';
  var isSector=td.getAttribute('data-sector')==='1';
  var histKey=td.getAttribute('data-hist-key')||'';
  var name=td.textContent.trim();
  var lbl=document.getElementById('saKlineLbl');
  lbl.textContent=name+' 加载中…';
  posTip(e);saTip.style.display='block';
  /* 优先用页面已嵌入的历史数据（指数、板块） */
  if(histKey){
    var found=null;
    if(histKey.indexOf('sec:')===0){
      var sc=histKey.slice(4);
      (D.rps&&D.rps.passed||[]).forEach(function(x){if(x.code===sc)found=x});
      if(!found&&(D.top_sectors||[]))D.top_sectors.forEach(function(x){if((x.code||'').replace('URFI','')===sc)found=x});
      if(!found&&D.net_inflow_sectors){
        var ni=D.net_inflow_sectors;
        (ni.top||[]).forEach(function(x){if((x.code||'').replace('URFI','')===sc)found=x});
        if(!found)(ni.bottom||[]).forEach(function(x){if((x.code||'').replace('URFI','')===sc)found=x});
      }
    }else{
      (D.indices||[]).forEach(function(x){if(x.code===histKey)found=x});
      if(!found&&(D.style_indices||[]))D.style_indices.forEach(function(x){if(x.code===histKey)found=x});
    }
    if(found&&found.hist_dates&&found.hist_close){
      drawMiniKline(found.hist_dates,found.hist_close,null,null,null,name,'页面嵌入数据');
      return;
    }
  }
  /* 否则 fetch API */
  var myReq=++saCurReq;
  var url=location.origin+'/api/kline?lmt=60';
  if(isSector){url+='&secid='+encodeURIComponent(code)}
  else{url+='&code='+encodeURIComponent(code);if(mkt)url+='&mkt='+mkt}
  fetch(url).then(function(r){return r.json()}).then(function(d){
    if(myReq!==saCurReq)return;
    if(!d.ok){lbl.textContent=name+'：'+(d.error||'获取失败');return}
    drawMiniKline(d.dates,d.close,d.open,d.high,d.low,name,d.name||'');
  }).catch(function(){if(myReq===saCurReq)lbl.textContent=name+'：网络错误'});
}
function drawMiniKline(dates,close,open,high,low,name,foot){
  var cv=document.getElementById('saKlineCv');
  var lbl=document.getElementById('saKlineLbl');
  var ft=document.getElementById('saKlineFoot');
  lbl.textContent=name;
  var n=dates.length;if(!n){lbl.textContent=name+'：无K线数据';return}
  var dpr=window.devicePixelRatio||1;
  var w=cv.clientWidth||360,h=cv.clientHeight||230;
  cv.width=w*dpr;cv.height=h*dpr;
  var ctx=cv.getContext('2d');ctx.scale(dpr,dpr);
  ctx.clearRect(0,0,w,h);
  /* 计算价格范围 */
  var hasOHLC=open&&open.length===n;
  var mn=Infinity,mx=-Infinity;
  for(var i=0;i<n;i++){
    var lo=hasOHLC?Math.min(open[i],close[i],high[i],low[i]):close[i];
    var hi=hasOHLC?Math.max(open[i],close[i],high[i],low[i]):close[i];
    if(lo<mn)mn=lo;if(hi>mx)mx=hi;
  }
  if(mn===mx){mn-=1;mx+=1}
  var rng=mx-mn;mn-=rng*0.08;mx+=rng*0.08;
  var pad=12,pw=w-pad*2,ph=h-pad*2;
  var cw=hasOHLC?Math.max(2,(n>1?pw/(n-1):0)*0.55):0;
  var x0=pad+cw/2,xEnd=w-pad-cw/2;
  var xStep=n>1?(xEnd-x0)/(n-1):0;
  var yOf=function(v){return pad+ph-(v-mn)/(mx-mn)*ph};
  /* 网格线 */
  ctx.strokeStyle='#f0f0f0';ctx.lineWidth=1;
  for(var g=0;g<=4;g++){var y=pad+g*ph/4;ctx.beginPath();ctx.moveTo(x0,y);ctx.lineTo(x0+pw,y);ctx.stroke()}
  /* K线或折线 */
  var RED='#d8392b',GREEN='#16a34a';
  if(hasOHLC){
    for(var i=0;i<n;i++){
      var x=x0+i*xStep;
      var yO=yOf(open[i]),yC=yOf(close[i]),yH=yOf(high[i]),yL=yOf(low[i]);
      var up=close[i]>=open[i];
      ctx.strokeStyle=up?RED:GREEN;ctx.fillStyle=up?RED:GREEN;
      ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,yH);ctx.lineTo(x,yL);ctx.stroke();
      var top=Math.min(yO,yC),bh=Math.max(1,Math.abs(yC-yO));
      ctx.fillRect(x-cw/2,top,cw,bh);
    }
  }else{
    ctx.strokeStyle='#2b6cb0';ctx.lineWidth=1.5;ctx.beginPath();
    for(var i=0;i<n;i++){var x=x0+i*xStep,y=yOf(close[i]);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)}
    ctx.stroke();
  }
  /* 末点标签 */
  var lastV=close[n-1];
  ctx.fillStyle='#1f2329';ctx.font='9px sans-serif';ctx.textAlign='right';
  ctx.fillText(lastV.toFixed(2),w-pad,pad+14);
  ctx.textAlign='left';
  ctx.fillText(dates[0],pad,h-pad-4);
  ctx.textAlign='right';ctx.fillText(dates[n-1],w-pad,h-pad-4);
  ft.textContent=foot||('近'+n+'个交易日');
}
function posTip(e){
  if(!saTip)return;
  var tw=420,th=340,off=14;
  var x=e.clientX+off,y=e.clientY-th-18;
  if(x+tw>window.innerWidth)x=e.clientX-tw-off;
  if(x<4)x=4;if(y<4)y=4;if(y+th>window.innerHeight)y=window.innerHeight-th-4;
  saTip.style.left=x+'px';saTip.style.top=y+'px';
}
function hideKlineTip(){if(saTip)saTip.style.display='none'}
if(document.readyState!=='loading')initSaHover();
else document.addEventListener('DOMContentLoaded',initSaHover);"""
    ctrl_bar = ctrl_bar.replace("{nav_href}", nav_href).replace("{nav_label}", nav_label)
    ctrl_bar = ctrl_bar.replace("{SA_CSS}", sa_css).replace("{SA_JS}", sa_js)
    pm = "midday" if midday else "close"
    page_cfg = f"<script>var REPORT_DATE='{report_date}';var PAGE_MODE='{pm}';</script>"

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A股收盘复盘 {d['date']}</title>
{chartjs_tag}
<style>
*{{box-sizing:border-box}} body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
background:#f5f6f8;color:#1f2329;margin:0;padding:24px}}
.wrap{{max-width:1080px;margin:0 auto}}
h1{{font-size:24px;margin:0 0 4px}} .sub{{color:#888;font-size:13px;margin-bottom:20px}}
.card{{background:#fff;border-radius:12px;padding:18px 20px;margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.card h2{{font-size:18px;margin:0 0 14px;border-left:4px solid #2b6cb0;padding-left:10px}}
.kpis{{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:14px}}
.kpi{{flex:1;min-width:150px;background:#fafbfc;border:1px solid #eef0f3;border-radius:10px;padding:12px 14px}}
.kpi .lab{{font-size:12px;color:#888}} .kpi .val{{font-size:22px;font-weight:700;margin-top:4px}}
canvas{{height:300px!important;max-height:300px;width:100%!important}}
body{{overflow-x:hidden}}
.grid2{{display:grid;grid-template-columns:1fr;gap:16px}}
@media(min-width:900px){{ .grid2{{grid-template-columns:1fr 1fr}} }}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 10px;border-bottom:1px solid #eee;text-align:left}}
th{{background:#fafbfc;color:#666;font-weight:600}} td.num{{text-align:right;font-variant-numeric:tabular-nums}}
table.sortable th{{cursor:pointer;user-select:none;position:relative;white-space:nowrap}}
table.sortable th:hover{{background:#eef2f7}}
table.sortable th .arr{{color:#2b6cb0;font-size:10px;margin-left:4px}}
h4{{margin:6px 0}}
.note{{color:#b7791f;font-size:12px;background:#fffaf0;padding:8px 10px;border-radius:6px}}
.miss{{color:#888;font-style:italic}}
#zoomModal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:999;align-items:center;justify-content:center;flex-direction:column}}
#zoomBody{{width:90vw;height:82vh;background:#fff;border-radius:12px;padding:18px;box-sizing:border-box}}
#zoomBody canvas{{max-height:none!important;width:100%!important;height:100%!important}}
#zoomHint{{color:#fff;font-size:12px;margin-top:10px}}
#idxTip{{position:fixed;z-index:1000;display:none;pointer-events:none;background:rgba(255,255,255,.97);border:1px solid #e2e5ea;border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.15);min-width:150px;max-width:240px}}
#idxTip .t-date{{font-weight:700;color:#666;margin-bottom:6px;border-bottom:1px solid #eee;padding-bottom:4px}}
#idxTip .t-row{{display:flex;justify-content:space-between;gap:14px;line-height:1.7}}
#idxTip .t-row b{{font-variant-numeric:tabular-nums}}
.chartLeg{{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 8px}}
.chartLeg .chip{{display:inline-flex;align-items:center;gap:5px;font-size:11px;line-height:1;padding:4px 9px;border:1px solid #e2e5ea;border-radius:14px;cursor:pointer;user-select:none;background:#fafbfc;transition:.15s;color:#444}}
.chartLeg .chip:hover{{border-color:#2b6cb0;color:#2b6cb0}}
.chartLeg .chip.active{{background:#2b6cb0;color:#fff;border-color:#2b6cb0;box-shadow:0 1px 4px rgba(43,108,176,.4)}}
.chartLeg .chip .dot{{width:9px;height:9px;border-radius:50%;display:inline-block}}
/* TR情绪监测 时间范围切换按钮 */
.tr-range-btns{{display:flex;gap:6px;margin:4px 0 8px}}
.tr-range-btn{{font-size:12px;padding:4px 12px;border:1px solid #e2e5ea;border-radius:14px;background:#fafbfc;color:#444;cursor:pointer;user-select:none;transition:.15s}}
.tr-range-btn:hover{{border-color:#2b6cb0;color:#2b6cb0}}
.tr-range-btn.active{{background:#2b6cb0;color:#fff;border-color:#2b6cb0;box-shadow:0 1px 4px rgba(43,108,176,.4)}}
/* 非当日数据红色感叹号标记 */
.stale-badge{{position:absolute;top:5px;right:6px;width:18px;height:18px;line-height:18px;text-align:center;border-radius:50%;background:#d8392b;color:#fff;font-weight:700;font-size:12px;cursor:help;z-index:5;box-shadow:0 1px 3px rgba(216,57,43,.4)}}
.stale-badge::after{{content:attr(data-tip);position:absolute;left:50%;top:140%;transform:translateX(-50%);white-space:nowrap;background:#d8392b;color:#fff;font-size:12px;font-weight:400;padding:4px 9px;border-radius:5px;opacity:0;pointer-events:none;transition:opacity .15s;z-index:50;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.stale-badge:hover::after{{opacity:1}}
/* 数据截止时间戳 */
.cutoff-banner{{display:inline-block;background:#eef4fb;color:#2b6cb0;border:1px solid #cdd8e6;border-radius:8px;padding:6px 12px;font-size:13px;font-weight:600;margin:0 0 14px}}
.cutoff-badge{{position:absolute;bottom:6px;right:8px;font-size:11px;color:#5b7083;background:#eef2f7;border:1px solid #dde4ec;border-radius:10px;padding:2px 8px;z-index:4}}
</style></head><body><div class="wrap">
<h1>A股收盘复盘 {d['date']}（{d.get('weekday','')}）<span class="sa-light off" id="saLight" title=""><span class="sa-dot" id="saDot"></span><span class="sa-txt" id="saTxt">状态加载中…</span></span></h1>
<div class="sub">数据来源：同花顺 hithink-finance（市场宽度/等权/指数/板块成交额/个股）＋ 通达信 TDX（板块 RPS 共振·概念板块指数 881xxx，同花顺兜底）＋ 东方财富（主力净流入前10板块·当日）＋ 通达信 tdx_screener（个股新高/新低·当日，westock 兜底）· 仅客观复盘，不构成投资建议</div>
{cutoff_banner}
{nav_html}
{page_cfg}
{ctrl_bar}
<div class="card"{cutoff_attr}><h2>一、市场表现</h2>
<div class="kpis">
<div class="kpi"><div class="lab">全A等权涨跌幅</div><div class="val" style="color:{pct_color(m.get('equal_weight_pct'))}">{fmt_pct(m.get('equal_weight_pct'))}</div></div>
<div class="kpi"><div class="lab">涨跌幅中位数</div><div class="val" style="color:{pct_color(m.get('median_pct'))}">{fmt_pct(m.get('median_pct'))}</div></div>
<div class="kpi"><div class="lab">全市场总成交额</div><div class="val">{m.get('total_turnover_yi')}亿</div></div>
<div class="kpi"><div class="lab">上涨 / 下跌 / 平</div><div class="val" style="font-size:18px"><span style="color:{RED}">{m.get('up')}</span> / <span style="color:{GREEN}">{m.get('down')}</span> / <span style="color:#1f2329">{m.get('flat')}</span></div></div>
<div class="kpi"><div class="lab">涨停 / 跌停</div><div class="val" style="font-size:18px;color:{RED}">{m.get('limit_up')} <span style="color:#888">/</span> <span style="color:{GREEN}">{m.get('limit_down')}</span></div></div>
</div>
<div class="grid2">
<div><h4>全市场总成交额（亿元）</h4><div class="chartLeg" id="leg_cTurn"></div><canvas id="cTurn"{hist_stale}></canvas></div>
<div><h4>涨跌家数</h4><div class="chartLeg" id="leg_cUp"></div><canvas id="cUp"{hist_stale}></canvas></div>
</div>
<div class="grid2" style="margin-top:12px">
<div><h4>涨停 / 跌停家数</h4><div class="chartLeg" id="leg_cLim"></div><canvas id="cLim"{hist_stale}></canvas></div>
<div><h4>个股创新高 / 新低家数</h4><div class="chartLeg" id="leg_cHL"></div><canvas id="cHL"{hist_stale}></canvas></div>
</div>
<div style="margin-top:14px">{wande_html}</div>
{jzxt_html}
{tr_html}
{note}
</div>

<div class="card"{cutoff_attr}><h2>二、指数表现</h2>
<h4>宽基指数</h4>
<table><tr><th>指数</th><th>收盘</th><th>涨跌幅</th><th>成交额</th></tr>{idx_rows}</table>
<h4 style="margin-top:14px">宽基指数 · 近 60 交易日收盘走势（归一化 · 首日=100）</h4>
<p class='note'>曲线以 60 个交易日前收盘为基准 100，高低即代表相对强弱：最终位置越高＝区间越强；与某指数差值＝跑赢/跑输幅度。鼠标悬停可查看各指数当日数值（按强弱降序排列）。</p>
<div class="chartLeg" id="leg_cIdx"></div><canvas id="cIdx"{idx_stale}></canvas>
<hr style="margin:20px 0 6px;border:none;border-top:1px solid #e5e8ec">
<h4 style="margin-top:8px">风格指数（短线风格 / 情绪）</h4>
<table><tr><th>风格</th><th>收盘</th><th>涨跌幅</th></tr>{style_rows}</table>
<p class='note'>风格指数数据来源：同花顺 hithink 特色指数（tszs，与上方宽基指数同源）；北证50 来自腾讯行情（hithink 指数接口不支持北交所）。「昨日涨停 / 昨日成交前10 / 北交所昨日涨停」为同花顺编制的风格指数：成分股为上一交易日对应股票（涨停股 / 成交额前十 / 北交所涨停股），指数反映其今日整体表现。</p>
<h4 style="margin-top:14px">风格指数 · 近 60 交易日收盘走势（归一化 · 首日=100）</h4>
<p class='note'>风格指数点位差异大（全A 约 2000 点、微盘股数万点），统一以 60 个交易日前收盘为基准 100，直接比较各风格相对强弱；鼠标悬停可查看各指数当日数值（按强弱降序排列）。历史收盘：同花顺特色指数走 hithink 历史接口（与宽基指数同源），北证50 走新浪日线。</p>
<div class="chartLeg" id="leg_cStyle"></div><canvas id="cStyle"{idx_stale}></canvas>
{style_drop_note}
</div>

<div class="card"{sector_stale}{cutoff_attr}><h2>三、成交量排名前 10 板块（行业 · 同花顺 thsdk·按真实成交额）</h2>
<table><tr><th>#</th><th>板块</th><th>成交额</th><th>成交额占比%</th><th>涨跌幅</th></tr>{sec_rows}</table>
<h4 style="margin-top:14px">前 10 板块：成交额（亿元 · 柱）与 成交额占比%（% · 线）</h4><div class="chartLeg" id="leg_cSec"></div><canvas id="cSec"></canvas>
<p class='note'>按真实成交额排序，数据来源：同花顺 thsdk（游客模式）行业板块，与第四节「主力净流入」为同一套 90 行业口径，可直接对照同一行业的成交额与资金流向。</p>
</div>

<div class="card"{sector_stale}{cutoff_attr}><h2>{sec4_heading}</h2>
{sec4_badge}
<div class='grid2'>
<div><h4>主力净流入 TOP{net_top_n}</h4><table><tr><th>#</th><th>行业</th><th>净额</th><th>涨跌幅</th><th>成交额</th><th>成交额占比%</th></tr>{net_top_rows or "<tr><td colspan=4>数据缺失</td></tr>"}</table></div>
<div><h4>主力净流出 TOP{net_top_n}</h4><table><tr><th>#</th><th>行业</th><th>净额</th><th>涨跌幅</th><th>成交额</th><th>成交额占比%</th></tr>{net_bot_rows or "<tr><td colspan=4>数据缺失</td></tr>"}</table></div>
</div>
<h4 style="margin-top:14px">主力净流入前 {net_top_n} 板块（亿元）</h4><div class="chartLeg" id="leg_cNet"></div><canvas id="cNet"></canvas>
<p class='note'>按主力净流入排序，数据来源：{net_src}（与第三节成交额同为同花顺 90 行业口径，可直接对照）。本节即「资金流向」模块。</p>
</div>

<div class="card"{rps_stale}{cutoff_attr}><h2>五、强势板块 · RPS 共振（RPS≥87）</h2>
{rps_html}
</div>

<div class="card"{cutoff_attr}><h2>六、成交量排名前 100 个股</h2>
<table id="stkVolTable"><tr><th>#</th><th>名称</th><th>代码</th><th>成交额</th><th>涨跌幅</th><th>行业</th><th>概念板块</th></tr>{stk_rows}{stk_rows_rest}</table>
<p style="margin-top:10px"><span id="foldToggle" style="cursor:pointer;color:#2b6cb0;font-size:13px">展开 第 51–100 名（点击折叠 / 展开）</span></p>
<p class='note'>按当日真实成交额降序，取前 100；51–100 默认折叠，点击展开。点击表头可排序（含折叠行一并参与排序）。数据来源：同花顺 hithink-finance。</p>
</div>

<div class="card"{hl_stale}{cutoff_attr}><h2>七、个股新高 / 新低</h2>
<div class="kpis">
<div class="kpi"><div class="lab">创一年新高</div><div class="val" style="color:{RED}">{hn_disp}</div></div>
<div class="kpi"><div class="lab">创一年新低</div><div class="val" style="color:{GREEN}">{ln_disp}</div></div>
</div>
<p class='note'>{hl_note}</p>
<h4 style="margin-top:14px">创一年新高（{len(hn_stocks)} 只 · 含行业 / 概念板块）</h4>
<table><tr><th>#</th><th>名称</th><th>代码</th><th>涨跌幅</th><th>行业</th><th>概念板块</th></tr>{hn_rows}</table>
<h4 style="margin-top:14px">创一年新低（{len(ln_stocks)} 只 · 含行业 / 概念板块）</h4>
<table><tr><th>#</th><th>名称</th><th>代码</th><th>涨跌幅</th><th>行业</th><th>概念板块</th></tr>{ln_rows}</table>
</div>

<div class="card"{cutoff_attr}><h2>八、涨停 / 跌停个股</h2>
<div class="kpis">
<div class="kpi"><div class="lab">涨停</div><div class="val" style="color:{RED}">{m.get('limit_up')}</div></div>
<div class="kpi"><div class="lab">跌停</div><div class="val" style="color:{GREEN}">{m.get('limit_down')}</div></div>
</div>
<h4 style="margin-top:14px">涨停（{len(lu_list)} 只 · 含行业 / 概念板块，按成交额降序）</h4>
<table><tr><th>#</th><th>名称</th><th>代码</th><th>涨跌幅</th><th>成交额</th><th>行业</th><th>概念板块</th></tr>{lu_rows}</table>
<h4 style="margin-top:14px">跌停（{len(ld_list)} 只 · 含行业 / 概念板块，按成交额降序）</h4>
<table><tr><th>#</th><th>名称</th><th>代码</th><th>涨跌幅</th><th>成交额</th><th>行业</th><th>概念板块</th></tr>{ld_rows}</table>
<p class='note'>涨停 / 跌停口径：当日涨跌幅 ≥9.9% / ≤−9.9%（同花顺快照，已含科创 / 创业 / 北交所不同涨跌幅限制的股票）。行业 / 概念板块来自同花顺分类映射，未匹配到的显示「—」。</p>
</div>

</div>

<div id="zoomModal"><div id="zoomBody"></div><div id="zoomHint">点击空白处或按 Esc 关闭</div></div>
<div id="idxTip"></div>

<script>
const D = {json.dumps(payload, ensure_ascii=False)};
const RED='{RED}', GREEN='{GREEN}', GREY='{GREY}';
const verticalLinePlugin = {{
  id:'verticalLine',
  afterDraw(chart){{
    let x = null;
    if(chart._hx != null) x = chart._hx;
    else {{ const tt = chart.tooltip; if(tt && tt.getActiveElements && tt.getActiveElements().length) x = tt.getActiveElements()[0].element.x; }}
    if(x == null) return;
    const top = chart.chartArea.top, bot = chart.chartArea.bottom;
    const ctx = chart.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, top); ctx.lineTo(x, bot);
    ctx.lineWidth = 1.5; ctx.strokeStyle = 'rgba(0,0,0,.4)';
    ctx.setLineDash([4,3]);
    ctx.stroke();
    ctx.restore();
  }}
}};
const ZONES=[{{name:'极冰',value:10,color:'#00BFFF'}},{{name:'冰点',value:25,color:'#4169E1'}},{{name:'中枢',value:50,color:'#FFB7C5'}},{{name:'过热',value:75,color:'#FFD700'}},{{name:'高潮',value:90,color:'#ff0000'}}];
const zonePlugin={{id:'zones',afterDraw(chart){{const ys=chart.scales.y;if(!ys)return;const ctx=chart.ctx;ctx.save();ctx.font='11px sans-serif';ZONES.forEach(z=>{{const y=ys.getPixelForValue(z.value);ctx.beginPath();ctx.moveTo(chart.chartArea.left,y);ctx.lineTo(chart.chartArea.right,y);ctx.lineWidth=1;ctx.setLineDash([5,4]);ctx.strokeStyle=z.color;ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=z.color;ctx.fillText(z.name,chart.chartArea.left+4,y-3);}});ctx.restore();}}}};
const TR_ZONES=[{{name:'沸点87',value:87,color:'#d8392b'}},{{name:'相变50',value:50,color:'#ca8a04'}},{{name:'冰点13',value:13,color:'#4169E1'}}];
const trZonePlugin={{id:'trZones',afterDraw(chart){{const ys=chart.scales.y;if(!ys)return;const ctx=chart.ctx;ctx.save();ctx.font='11px sans-serif';TR_ZONES.forEach(z=>{{const y=ys.getPixelForValue(z.value);ctx.beginPath();ctx.moveTo(chart.chartArea.left,y);ctx.lineTo(chart.chartArea.right,y);ctx.lineWidth=1;ctx.setLineDash([5,4]);ctx.strokeStyle=z.color;ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=z.color;ctx.fillText(z.name,chart.chartArea.left+4,y-3);}});ctx.restore();}}}};
const WANDE = (D.wande && D.wande.ok) ? D.wande : null;
const candlePlugin = {{
  id:'candle',
  afterDraw(chart){{
    if(!WANDE) return;
    const xs=chart.scales.x, ys=chart.scales.y;
    const n=WANDE.close.length;
    if(!n) return;
    const step = n>1 ? Math.abs(xs.getPixelForValue(1)-xs.getPixelForValue(0)) : 10;
    const w = Math.max(1.5, step*0.6);
    const ctx=chart.ctx;
    for(let i=0;i<n;i++){{
      const x=xs.getPixelForValue(i);
      const yO=ys.getPixelForValue(WANDE.open[i]);
      const yC=ys.getPixelForValue(WANDE.close[i]);
      const yH=ys.getPixelForValue(WANDE.high[i]);
      const yL=ys.getPixelForValue(WANDE.low[i]);
      const up = WANDE.close[i] >= WANDE.open[i];
      ctx.strokeStyle = up ? RED : GREEN;
      ctx.fillStyle = up ? RED : GREEN;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x,yH); ctx.lineTo(x,yL); ctx.stroke();
      const top=Math.min(yO,yC), hgt=Math.max(1,Math.abs(yC-yO));
      ctx.fillRect(x-w/2, top, w, hgt);
    }}
  }}
}};
const INSTANCES = {{}};
function cloneCfg(config){{
  // 克隆「干净、可序列化」的配置，专供大图放大使用。
  // chart.config 是 Chart.js 的 Config 包装对象（内含 chart 自引用），JSON 序列化会抛循环引用错误，
  // 因此必须在创建图表时单独存一份纯数据副本。
  try {{ return {{type:config.type, data:JSON.parse(JSON.stringify(config.data)), options:JSON.parse(JSON.stringify(config.options||{{}}))}}; }} catch(e){{ return null; }}
}}
function attachHover(ch, cv, onMove){{
  let rafId = null;
  cv.addEventListener('mousemove', (e)=>{{
    const rect = cv.getBoundingClientRect();
    const xs = ch.scales.x; if(!xs) return;
    const dpr = window.devicePixelRatio || 1;
    const x = (e.clientX - rect.left) * dpr;
    const idx = Math.round(xs.getValueForPixel(x));
    const labels = (ch.data && ch.data.labels) || [];
    const v = (idx>=0 && idx<labels.length) ? xs.getPixelForValue(idx) : null;
    if(v !== ch._hx){{
      ch._hx = v;
      if(rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(()=>{{ ch.update('none'); rafId=null; }});
    }}
    if(onMove) onMove((idx>=0 && idx<labels.length)?idx:null, e);
  }});
  cv.addEventListener('mouseleave', ()=>{{
    if(ch._hx!==null){{ ch._hx=null; if(rafId) cancelAnimationFrame(rafId); ch.update('none'); }}
    if(onMove) onMove(null, null);
  }});
}}
function makeChart(id, config, onMove){{
  config.options = config.options || {{}};
  config.options.interaction = {{mode:'index', intersect:false}};
  config.options.plugins = config.options.plugins || {{}};
  config.options.plugins.verticalLine = true;
  // 关闭原生图例（改用上方可点击高亮的自定义图例 chip）
  config.options.plugins.legend = Object.assign({{}}, config.options.plugins.legend||{{}}, {{display:false}});
  config.options.plugins.tooltip = Object.assign({{
    enabled:true, titleFont:{{size:13,weight:'bold'}}, bodyFont:{{size:12}},
    padding:10, filter:(item)=> item.parsed !== null && item.parsed !== undefined
  }}, config.options.plugins.tooltip||{{}});
  config.plugins = (config.plugins||[]).concat([verticalLinePlugin]);
  const ch = new Chart(document.getElementById(id), config);
  INSTANCES[id] = ch;
  // 保存干净可序列化配置用于大图放大（见 cloneCfg 说明）
  ch.__zoomCfg = cloneCfg(config);
  ch.__needsCandle = (id==='cWande');
  ch.__needsZone = (id==='cJzxt');
  ch.__needsTrZone = (id==='cTr');
  const cv = document.getElementById(id);
  cv.style.cursor='zoom-in';
  cv.addEventListener('dblclick', ()=>openZoom(id));
  attachHover(ch, cv, onMove);
  return ch;
}}
function lineCfg(labels, datasets, opts){{ return {{type:'line', data:{{labels,datasets}}, options:Object.assign({{responsive:true,elements:{{point:{{hitRadius:8}}}},plugins:{{legend:{{labels:{{font:{{size:11}}}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:12,font:{{size:10}}}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:10}}}},grid:{{color:'#eee'}}}}}}}}, opts||{{}})}}; }}
function barCfg(labels, label, data, color, rot){{ return {{type:'bar', data:{{labels,datasets:[{{label,data,backgroundColor:color, barPercentage:0.4, categoryPercentage:0.6}}]}}, options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{font:{{size:10}},maxRotation:rot||0}}}},y:{{grid:{{color:'#eee'}}}}}}}}}}; }}

const H=D.hist;
makeChart('cTurn', lineCfg(H.dates, [{{label:'总成交额(亿)',data:H.turnover,borderColor:GREY,fill:false,pointRadius:1,tension:.25,borderWidth:1}}]));
makeChart('cUp', lineCfg(H.dates, [
  {{label:'上涨',data:H.up,borderColor:RED,backgroundColor:RED,fill:false,pointRadius:1,tension:.25,borderWidth:1}},
  {{label:'下跌',data:H.down,borderColor:GREEN,backgroundColor:GREEN,fill:false,pointRadius:1,tension:.25,borderWidth:1}}]));
makeChart('cLim', lineCfg(H.dates, [
  {{label:'涨停',data:H.lu,borderColor:RED,fill:false,pointRadius:1,tension:.25,borderWidth:1}},
  {{label:'跌停',data:H.ld,borderColor:GREEN,fill:false,pointRadius:1,tension:.25,borderWidth:1}}]));
const hlDs=[];
if(H.hn.some(x=>x!==null)) hlDs.push({{label:'新高',data:H.hn,borderColor:RED,fill:false,pointRadius:1,tension:.25,borderWidth:1}});
if(H.ln.some(x=>x!==null)) hlDs.push({{label:'新低',data:H.ln,borderColor:GREEN,fill:false,pointRadius:1,tension:.25,borderWidth:1}});
if(hlDs.length) makeChart('cHL', lineCfg(H.dates, hlDs));
else document.getElementById('cHL').parentElement.innerHTML='<p class="miss">新高/新低：暂无历史数据</p>';
const idxColors=['#2b6cb0','#d8392b','#16a34a','#9333ea','#0891b2','#ca8a04','#db2777','#475569'];
// 重要指数：一律归一化（首日=100），消除点位绝对值差异，便于比强弱
const idxRaw = D.idx_lines.map(l=>l.data.slice());
const idxNorm = idxRaw.map(arr=>{{ const b=arr[0]; return arr.map(v=> v==null?null:+(v/b*100).toFixed(2)); }});
makeChart('cIdx', lineCfg(D.idx_dates, D.idx_lines.map((l,i)=>({{
  label:l.name, data:idxNorm[i], borderColor:idxColors[i%8], fill:false, pointRadius:0, tension:.2, borderWidth:1.5
}}))), renderIdxTip);
INSTANCES['cIdx'].options.scales.y.title={{display:true,text:'归一化（首日=100）',font:{{size:10}}}};
INSTANCES['cIdx'].options.plugins.tooltip.enabled=false;  // 用自定义 #idxTip 代替原生 tooltip
// 鼠标悬停时渲染各指数当日数值，按强弱（值）降序排列
function renderIdxTip(idx, e){{
  const tip=document.getElementById('idxTip');
  if(idx==null || idx<0){{ tip.style.display='none'; return; }}
  const ch=INSTANCES['cIdx']; if(!ch) return;
  const rows=ch.data.datasets
    .map(d=>({{name:d.label, val:d.data[idx]}}))
    .filter(r=>r.val!==null && r.val!==undefined)
    .sort((a,b)=>b.val-a.val);
  const date=D.idx_dates[idx];
  tip.innerHTML='<div class="t-date">'+date+'</div>'+rows.map(r=>'<div class="t-row"><span>'+r.name+'</span><b>'+Number(r.val).toFixed(2)+'</b></div>').join('');
  tip.style.display='block';
  let lx=e.clientX+14, ly=e.clientY+14;
  const w=tip.offsetWidth||160;
  if(lx+w>window.innerWidth) lx=e.clientX-w-14;
  if(ly+tip.offsetHeight>window.innerHeight) ly=e.clientY-tip.offsetHeight-14;
  tip.style.left=lx+'px';
  tip.style.top=ly+'px';
}}
// 风格指数曲线（归一化 · 首日=100）：数据由后端按宽基指数同一 60 日窗口对齐（D.style_lines）
if(D.style_lines && D.style_lines.length){{
  const sRaw=D.style_lines.map(l=>l.data.slice());
  const sNorm=sRaw.map(arr=>{{ const b=arr.find(v=>v!==null); return b?arr.map(v=>v==null?null:+(v/b*100).toFixed(2)):[]; }});
  const styleColors=['#2b6cb0','#d8392b','#16a34a','#9333ea','#0891b2','#ca8a04','#db2777','#475569'];
  const sch=makeChart('cStyle', lineCfg(D.style_dates, D.style_lines.map((l,i)=>({{
    label:l.name, data:sNorm[i], borderColor:styleColors[i%styleColors.length], fill:false, pointRadius:0, tension:.2, borderWidth:1.5
  }}))), renderStyleTip);
  sch._sd=D.style_dates;  // 供自定义 tooltip 取日期
  sch.options.scales.y.title={{display:true,text:'归一化（首日=100）',font:{{size:10}}}};
  sch.options.plugins.tooltip.enabled=false;  // 用自定义 #idxTip 代替原生 tooltip
}} else {{
  document.getElementById('cStyle').parentElement.innerHTML='<p class="miss">风格指数曲线：暂无历史数据（本次采集后自动累积）</p>';
}}
function renderStyleTip(idx, e){{
  const tip=document.getElementById('idxTip');
  if(idx==null || idx<0){{ tip.style.display='none'; return; }}
  const ch=INSTANCES['cStyle']; if(!ch) return;
  const rows=ch.data.datasets
    .map(d=>({{name:d.label, val:d.data[idx]}}))
    .filter(r=>r.val!==null && r.val!==undefined)
    .sort((a,b)=>b.val-a.val);
  const date=(ch._sd||[])[idx];
  tip.innerHTML='<div class="t-date">'+date+'</div>'+rows.map(r=>'<div class="t-row"><span>'+r.name+'</span><b>'+Number(r.val).toFixed(2)+'</b></div>').join('');
  tip.style.display='block';
  let lx=e.clientX+14, ly=e.clientY+14;
  const w=tip.offsetWidth||160;
  if(lx+w>window.innerWidth) lx=e.clientX-w-14;
  if(ly+tip.offsetHeight>window.innerHeight) ly=e.clientY-tip.offsetHeight-14;
  tip.style.left=lx+'px';
  tip.style.top=ly+'px';
}}
makeChart('cSec', {{
  type:'bar',
  data:{{labels:D.sec_bar.map(s=>s.name), datasets:[
    {{type:'bar', label:'成交额(亿)', data:D.sec_bar.map(s=>s.v), backgroundColor:'#2b6cb0', yAxisID:'y', barPercentage:0.4, categoryPercentage:0.6}},
    {{type:'line', label:'成交额占比%', data:D.sec_bar.map(s=>s.ratio), borderColor:'#d8392b', backgroundColor:'#d8392b', yAxisID:'y1', pointRadius:3, borderWidth:2, tension:.25}}
  ]}},
  options:{{responsive:true, plugins:{{legend:{{display:false}}}}, scales:{{
    x:{{ticks:{{font:{{size:10}},maxRotation:60}}}},
    y:{{position:'left', grid:{{color:'#eee'}}, title:{{display:true,text:'成交额(亿)',font:{{size:10}}}}}},
    y1:{{position:'right', grid:{{drawOnChartArea:false}}, title:{{display:true,text:'成交额占比%',font:{{size:10}}}}, ticks:{{font:{{size:10}}}}}}
  }}}}
}});
makeChart('cNet', barCfg(D.net_top.map(s=>s.name),'主力净流入(亿)',D.net_top.map(s=>s.v),'#d8392b',60));

// 万得全A(881001) 日K（市值加权全A代理，非等权）
if(WANDE){{
  const wcfg={{type:'line',
    data:{{labels:WANDE.dates, datasets:[{{data:WANDE.close, pointRadius:0, borderColor:'rgba(0,0,0,0)', showLine:false}}]}},
    options:{{responsive:true, maintainAspectRatio:false,
      interaction:{{mode:'index', intersect:false}},
      plugins:{{legend:{{display:false}}, verticalLine:true,
        tooltip:{{enabled:true, titleFont:{{size:13,weight:'bold'}}, bodyFont:{{size:12}}, padding:10,
          callbacks:{{label:(c)=>['开 '+WANDE.open[c.dataIndex].toFixed(2),'收 '+WANDE.close[c.dataIndex].toFixed(2),'高 '+WANDE.high[c.dataIndex].toFixed(2),'低 '+WANDE.low[c.dataIndex].toFixed(2)]}}}}}},
      scales:{{x:{{offset:true,ticks:{{maxTicksLimit:12,font:{{size:10}}}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:10}}}},grid:{{color:'#eee'}}}}}}
    }},
    plugins:[verticalLinePlugin, candlePlugin]
  }};
  const wch=new Chart(document.getElementById('cWande'), wcfg);
  INSTANCES['cWande']=wch;
  wch.__zoomCfg = cloneCfg(wcfg);
  wch.__needsCandle = true;
  const wcv=document.getElementById('cWande');
  wcv.style.cursor='zoom-in';
  wcv.addEventListener('dblclick', ()=>openZoom('cWande'));
  attachHover(wch, wcv);
}}
// 均占系统 均线占用率（市场宽度）日线
const jz=D.jzxt;
if(jz && jz.dates && jz.dates.length){{
  const jzSeries=[['cdx','5日','#ff0000'],['dx','13日','#4169E1'],['zx','50日','#ff8c00'],['cx','120日','#8B008B']];
  const jzDs=jzSeries.filter(s=>(jz[s[0]]||[]).length).map(s=>({{label:s[1],data:jz[s[0]],borderColor:s[2],backgroundColor:s[2],fill:false,pointRadius:0,tension:.2,borderWidth:1.5}}));
  const jzCfg={{type:'line',data:{{labels:jz.dates,datasets:jzDs}},options:{{responsive:true,plugins:{{legend:{{labels:{{font:{{size:11}}}}}},tooltip:{{enabled:true,callbacks:{{label:(c)=>c.dataset.label+': '+Number(c.parsed.y).toFixed(2)+'%'}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:12,font:{{size:10}}}},grid:{{display:false}}}},y:{{min:0,max:100,ticks:{{font:{{size:10}}}},grid:{{color:'#eee'}},title:{{display:true,text:'占用率 %',font:{{size:10}}}}}}}}}},plugins:[zonePlugin]}};
  makeChart('cJzxt', jzCfg);
}}
// TR情绪监测（通达信扩展数据 38/39/40：HTR10/HTR20/HTR40）
const trFull = D.tr_emotion;
if(trFull && trFull.dates && trFull.dates.length){{
  const TR_RANGES = {{'120':120,'half':180,'year':365,'2year':730}};
  function trSlice(range){{
    const days = TR_RANGES[range] || 180;
    const lastDate = new Date(trFull.dates[trFull.dates.length-1]);
    const cutoff = new Date(lastDate);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffStr = cutoff.toISOString().slice(0,10);
    let si = trFull.dates.findIndex(d => d >= cutoffStr);
    return si < 0 ? 0 : si;
  }}
  let trStart = trSlice('half');
  const trSeries=[['htr10','HTR10(短期)','#ff6b6b'],['htr20','HTR20(中期)','#2b6cb0'],['htr40','HTR40(长期)','#9333ea']];
  function trDs(start){{
    return trSeries.map(s=>({{label:s[1],data:(trFull[s[0]]||[]).slice(start),borderColor:s[2],backgroundColor:s[2],fill:false,pointRadius:0,tension:.2,borderWidth:1.5}}));
  }}
  const trCfg={{type:'line',data:{{labels:trFull.dates.slice(trStart),datasets:trDs(trStart)}},options:{{responsive:true,plugins:{{legend:{{labels:{{font:{{size:11}}}}}},tooltip:{{enabled:true,callbacks:{{label:(c)=>c.dataset.label+': '+Number(c.parsed.y).toFixed(2)+'%'}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:12,font:{{size:10}}}},grid:{{display:false}}}},y:{{min:0,max:100,ticks:{{font:{{size:10}}}},grid:{{color:'#eee'}},title:{{display:true,text:'TR占比 %',font:{{size:10}}}}}}}}}},plugins:[trZonePlugin]}};
  makeChart('cTr', trCfg);
  document.querySelectorAll('.tr-range-btn').forEach(function(btn){{
    btn.addEventListener('click', function(){{
      document.querySelectorAll('.tr-range-btn').forEach(function(b){{b.classList.remove('active');}});
      this.classList.add('active');
      trStart = trSlice(this.dataset.range);
      const ch = INSTANCES['cTr'];
      ch.data.labels = trFull.dates.slice(trStart);
      ch.data.datasets.forEach(function(ds,i){{ds.data=(trFull[trSeries[i][0]]||[]).slice(trStart);}});
      ch.update();
    }});
  }});
}}
// 板块 RPS 共振（东方财富·全市场板块）：横向分组条形图
if(D.rps_chart_cfg) makeChart('cRps', D.rps_chart_cfg);

{LEGEND_JS}

// ---- 真正用数据重新渲染的大图（新建 Canvas + Chart 实例）----
var __zoomInst = null;   // 当前放大态的 Chart 实例
var __zoomId   = null;   // 当前放大态的原始图表 id

function openZoom(id){{
  var m=document.getElementById('zoomModal');
  if(m.style.display==='flex') return;
  var ch=INSTANCES[id]; if(!ch) return;

  // 用创建时保存的「干净可序列化」配置（ch.__zoomCfg）作为大图数据源。
  // 切勿使用 ch.config：它是 Chart.js 的 Config 包装对象，内含 chart 自引用，
  // JSON.stringify 会抛“循环引用”错误，导致大图打不开。
  var box=document.getElementById('zoomBody');
  var cfg=null;
  if(ch.__zoomCfg){{ try{{ cfg=JSON.parse(JSON.stringify(ch.__zoomCfg)); }}catch(e){{cfg=null;}} }}
  if(!cfg){{ try{{ cfg=JSON.parse(JSON.stringify((ch.config&&ch.config._config)||ch.config)); }}catch(e){{cfg=null;}} }}
  if(!cfg){{ m.style.display='flex'; box.innerHTML='<p style="color:#f00;padding:20px">该图表暂不支持放大</p>'; return; }}

  // 重建插件（JSON 序列化会丢失插件函数对象，这里按原图需要重新挂回）
  cfg.plugins = [verticalLinePlugin];
  if(ch.__needsCandle) cfg.plugins.push(candlePlugin);
  if(ch.__needsZone) cfg.plugins.push(zonePlugin);
  if(ch.__needsTrZone) cfg.plugins.push(trZonePlugin);
  cfg.options = cfg.options || {{}};
  cfg.options.maintainAspectRatio = false;  // 大图填满弹窗，避免 letterbox

  // 在弹窗中创建全新高分辨率 canvas
  var box=document.getElementById('zoomBody');
  box.innerHTML = '';
  var ncv = document.createElement('canvas');
  ncv.id='zoomCanvas';
  ncv.style.width='92vw';
  ncv.style.height='82vh';
  box.appendChild(ncv);

  m.style.display='flex';
  var tip=document.getElementById('idxTip'); if(tip) tip.style.display='none';

  // 用同一份配置新建 Chart 实例（高分辨率渲染）
  try {{
    __zoomInst = new Chart(ncv, cfg);
    INSTANCES['__zoom__'] = __zoomInst;   // 注册到全局映射，使 setHighlight 可用
    __zoomId = id;

    // ---- 补回 JSON 丢失的函数回调 ----
    // RPS 横向条形图：改用 index 模式 + 自定义外部 tooltip
    if(id==='cRps'){{
      __zoomInst.options.interaction={{mode:'index', intersect:false}};
      __zoomInst.options.plugins.tooltip.enabled=false;
      __zoomInst.options.plugins.tooltip.mode='index';
      __zoomInst.options.plugins.tooltip.intersect=false;
      __zoomInst.options.plugins.tooltip.external=rpsExternalTooltip;
      __zoomInst.update();
    }}
    // 指数图：关闭原生 tooltip（用自定义 idxTip，但大图中暂不跟随鼠标）
    if(id==='cIdx'){{
      __zoomInst.options.scales.y.title={{display:true,text:'归一化（首日=100）',font:{{size:10}}}};
      __zoomInst.options.plugins.tooltip.enabled=false;
      __zoomInst.update();
    }}
    // 风格指数图：同上（归一化曲线，大图不挂自定义 tooltip）
    if(id==='cStyle'){{
      __zoomInst.options.scales.y.title={{display:true,text:'归一化（首日=100）',font:{{size:10}}}};
      __zoomInst.options.plugins.tooltip.enabled=false;
      __zoomInst.update();
    }}

    // 继承原图的高亮状态
    if(ch._hlIdx!==null && ch._hlIdx!==undefined){{
      setHighlight('__zoom__', ch._hlIdx);
    }}
  }} catch(e){{ console.error('[zoom] 新建图表失败', e); box.innerHTML='<p style="color:#f00">图表放大失败：'+e.message+'</p>'; }}
}}
function closeZoom(){{
  // 销毁放大态 Chart 实例（释放 canvas / 事件 / 内存）
  if(__zoomInst){{
    try {{ __zoomInst.destroy(); }} catch(e){{}}
    delete INSTANCES['__zoom__'];
    __zoomInst = null;
    __zoomId = null;
  }}
  var box=document.getElementById('zoomBody');
  box.innerHTML='';
  var m=document.getElementById('zoomModal');
  m.style.display='none';
  var tip=document.getElementById('idxTip'); if(tip) tip.style.display='none';
}}
document.getElementById('zoomModal').addEventListener('click',(e)=>{{ if(e.target.id==='zoomModal') closeZoom(); }});
document.addEventListener('keydown',(e)=>{{ if(e.key==='Escape') closeZoom(); }});

// ---- 表头点击排序（所有数据表通用）----
function parseCell(txt){{
  txt=(txt||'').trim();
  if(txt===''||txt==='—'||txt==='-') return {{num:false, raw:txt}};
  var s=txt.replace(/[^0-9.-]/g,'');
  var n=parseFloat(s);
  if(s!=='' && !isNaN(n) && isFinite(n)) return {{num:true, val:n, raw:txt}};
  return {{num:false, raw:txt}};
}}
function sortTable(t, ci, dir){{
  var rows=[], skips=[];
  t.querySelectorAll('tr').forEach(function(tr){{
    if(tr.querySelector(':scope > th')) return;            // 跳过表头行
    var cells=tr.children;
    if(!cells.length || cells.length<=ci) return;
    if(cells[ci].getAttribute('colspan')){{ skips.push(tr); return; }}  // 跳过合计/占位行
    rows.push(tr);
  }});
  rows.sort(function(a,b){{
    var av=parseCell(a.children[ci].textContent), bv=parseCell(b.children[ci].textContent);
    if(av.num&&bv.num) return (av.val-bv.val)*dir;
    return av.raw.localeCompare(bv.raw,'zh')*dir;
  }});
  // 仅当首列表头为 #（序号列）时，按新顺序重排序号
  var firstTh=t.querySelector('th');
  var renum = firstTh && firstTh.textContent.trim()==='#';
  rows.forEach(function(r, idx){{ t.appendChild(r); if(renum){{ r.children[0].textContent = (idx+1); }} }});
  skips.forEach(function(r){{ t.appendChild(r); }});
  // 排序后，把折叠行（如成交量 51–100）全部显示出来
  var fr=t.querySelectorAll('tr.fold-row');
  if(fr.length && typeof foldState!=='undefined'){{ foldState.open=true; if(foldState.apply) foldState.apply(); }}
}}
function makeTablesSortable(){{
  document.querySelectorAll('table').forEach(function(t){{
    var ths=t.querySelectorAll('th');
    if(!ths.length) return;
    t.classList.add('sortable');
    var state={{col:null, dir:1}};
    ths.forEach(function(th, ci){{
      var arr=document.createElement('span'); arr.className='arr'; th.appendChild(arr);
      th.addEventListener('click', function(){{
        if(state.col===ci){{ state.dir=-state.dir; }} else {{ state.col=ci; state.dir=1; }}
        sortTable(t, ci, state.dir);
        ths.forEach(function(o){{ var a=o.querySelector('.arr'); if(a) a.textContent=''; }});
        arr.textContent = state.dir>0 ? '▲' : '▼';
      }});
    }});
  }});
}}
makeTablesSortable();
// 成交量表的折叠/展开（51–100 名），折叠行仍参与排序；排序后自动展开
var foldState={{open:false}};
function setupFold(){{
  var t=document.getElementById('stkVolTable'); if(!t) return;
  var btn=document.getElementById('foldToggle'); if(!btn) return;
  var rows=t.querySelectorAll('tr.fold-row');
  foldState.apply=function(){{
    rows.forEach(function(r){{ r.style.display = foldState.open ? '' : 'none'; }});
    btn.textContent = foldState.open ? '折叠 第 51–100 名（点击折叠 / 展开）' : '展开 第 51–100 名（点击折叠 / 展开）';
  }};
  btn.addEventListener('click', function(){{ foldState.open=!foldState.open; foldState.apply(); }});
}}
setupFold();
// 非当日数据：在标记的元素（表格/图表/卡片）上显示红色感叹号，hover 显示数据截至日期
// 非交易日（周末）：A股不开盘，数据本就该截止到最近交易日，不标红
function markStale(elm, date){{
  if(!elm) return;
  // 周末为非交易日，没有更新的数据可得，一律不标红（交易日由数据自然决定是否过期）
  var dow = new Date().getDay();
  if(dow === 0 || dow === 6) return;
  var host = (elm.tagName==='CANVAS') ? elm.parentElement : elm;
  if(!host) return;
  if(getComputedStyle(host).position==='static') host.style.position='relative';
  var b=document.createElement('span');
  b.className='stale-badge';
  b.setAttribute('data-tip','当前数据截至 '+date);
  b.textContent='!';
  host.appendChild(b);
}}
document.querySelectorAll('[data-stale]').forEach(function(box){{
  var date=box.getAttribute('data-stale');
  if(box.classList.contains('card') || box.classList.contains('section')){{
    box.querySelectorAll('table,canvas,.kpi').forEach(function(c){{ markStale(c, date); }});
  }} else {{
    markStale(box, date);
  }}
}});
// 数据截止时间戳：在带 data-cutoff 的元素（各板块卡片）右下角标注「数据截至 HH:MM」
document.querySelectorAll('[data-cutoff]').forEach(function(box){{
  var host = (box.tagName==='CANVAS') ? box.parentElement : box;
  if(!host) return;
  if(getComputedStyle(host).position==='static') host.style.position='relative';
  var b=document.createElement('span');
  b.className='cutoff-badge';
  b.textContent='数据截至 '+box.getAttribute('data-cutoff');
  host.appendChild(b);
}});
</script>
</body></html>"""
    # ── 动态化（Path A）：把"数据"拆成 bundle JSON，页面运行时 fetch 后渲染 ──
    # body_html = .wrap 内部全部内容（标题/截止戳/控制条/八张卡片）；图表脚本在静态外壳里。
    body_html = html.split('<div class="wrap">', 1)[1].split('<div id="zoomModal">', 1)[0]
    meta = {
        "date": report_date,
        "weekday": d.get("weekday", ""),
        "midday": midday,
        "pagemode": "midday" if midday else "close",
        "report_date": report_date,
        "cutoff_hhmm": cutoff_hhmm,
        "cutoff_variant": cutoff_variant,
        "cutoff_dt": cutoff_dt,
    }
    bundle = {"meta": meta, "payload": payload, "body_html": body_html}
    return html, bundle

def main():
    args = sys.argv[1:]
    midday = "--midday" in args
    if midday:
        args.remove("--midday")
    date = args[0] if args else datetime.date.today().strftime("%Y-%m-%d")
    d = load(date)
    hist = history()
    page_label = "A股午间复盘" if midday else "A股收盘复盘"
    base_name = "A股午盘" if midday else "A股复盘"
    html, bundle = build_html(d, hist, midday=midday)
    html = html.replace("A股收盘复盘", page_label)
    if midday:
        bundle["body_html"] = bundle["body_html"].replace("A股收盘复盘", page_label)
    out = os.path.join(BASE, f"{base_name}_{date}.html")
    open(out, "w", encoding="utf-8").write(html)
    # ── 动态化：写出 bundle（数据）+ manifest（指向最新 bundle）──
    # 文件名带 variant，避免收盘/午间同日期时 bundle 互相覆盖（曾导致午间页误加载收盘数据）
    variant = "midday" if midday else "close"
    bundle_name = f"{date}_{variant}_bundle.json"
    bundle_path = os.path.join(DATA, bundle_name)
    json.dump(bundle, open(bundle_path, "w", encoding="utf-8"), ensure_ascii=False)
    manifest = {"variant": variant, "date": date, "bundle": f"data/{bundle_name}",
                "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    json.dump(manifest, open(os.path.join(DATA, f"manifest_{variant}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    if not midday:
        # 主线索引仅收盘版维护；午间版走独立目录，不污染主线
        rd = os.path.join(BASE, "README.md")
        line = f"- [{date}]({base_name}_{date}.html)"
        txt = open(rd, encoding="utf-8").read()
        if line not in txt:
            if "## 已生成复盘" in txt:
                txt = txt.rstrip() + "\n" + line + "\n"
            else:
                txt += f"\n## 已生成复盘\n{line}\n"
            open(rd, "w", encoding="utf-8").write(txt)
    print(f"已生成[{'午间' if midday else '收盘'}]", out, "| 历史归档点数:", len(hist["dates"]))

if __name__ == "__main__":
    main()
