// stock-a 迷你K线代理：GET /api/kline?code=600519[&mkt=sh][&lmt=60]
// 个股 → 腾讯 ifzq.gtimg.cn fqkline（前复权日K，无鉴权）
// 板块 → 东方财富 push2his（secid=90.BKxxxx，无鉴权）
// 返回 { ok, dates, open, close, high, low, vol, name }
export async function onRequest(context) {
  const url = new URL(context.request.url);
  const code = (url.searchParams.get("code") || "").trim();
  const mkt  = (url.searchParams.get("mkt")  || "").trim();   // sh/sz/bj（个股）
  const secid = (url.searchParams.get("secid") || "").trim();  // 东方财富 secid（板块）
  const lmt  = parseInt(url.searchParams.get("lmt") || "60", 10);
  const isSector = !!secid || /^88\d{4}$/.test(code);          // 申万 88xxxx → 板块

  if (!code && !secid) return json({ ok: false, error: "缺少 code 或 secid" }, 400);

  try {
    if (isSector) {
      return await fetchSectorKline(secid || code, lmt);
    }
    return await fetchStockKline(code, mkt, lmt);
  } catch (e) {
    return json({ ok: false, error: String(e.message || e) }, 502);
  }
}

// ---------- 个股：腾讯 fqkline ----------
async function fetchStockKline(code, mkt, lmt) {
  // 自动推断市场前缀
  if (!mkt) {
    if (code.startsWith("6") || code.startsWith("5") || code.startsWith("11") || code.startsWith("13")) mkt = "sh";
    else if (code.startsWith("0") || code.startsWith("3") || code.startsWith("12") || code.startsWith("15") || code.startsWith("16") || code.startsWith("18")) mkt = "sz";
    else if (code.startsWith("4") || code.startsWith("8") || code.startsWith("920")) mkt = "bj";
    else mkt = "sz";
  }
  const sym = mkt + code;
  const apiUrl = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + sym + ",day,,," + lmt + ",qfq";
  const resp = await fetch(apiUrl, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!resp.ok) throw new Error("腾讯K线HTTP " + resp.status);
  const d = await resp.json();
  const blk = (d.data && d.data[sym]) || {};
  const rows = blk["qfqday"] || blk["day"] || [];
  if (!rows.length) throw new Error("腾讯K线无数据");
  const dates = [], open = [], close = [], high = [], low = [], vol = [];
  for (const r of rows) {
    // [date, open, close, high, low, vol, ...]
    dates.push(r[0]); open.push(+r[1]); close.push(+r[2]);
    high.push(+r[3]); low.push(+r[4]); vol.push(+r[5] || 0);
  }
  return json({ ok: true, name: blk.name || code, market: mkt, dates, open, close, high, low, vol });
}

// ---------- 板块：东方财富 push2his ----------
// 申万 88xxxx → secid 格式 90.881xxx（与 collect_sector_rps.py 同源）
async function fetchSectorKline(code, lmt) {
  const secid = "90." + code;
  const apiUrl = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=" + secid +
    "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&lmt=" + lmt;
  const resp = await fetch(apiUrl, { headers: { "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/" } });
  if (!resp.ok) throw new Error("东方财富K线HTTP " + resp.status);
  const d = await resp.json();
  const data = d.data || {};
  const klines = data.klines || [];
  if (!klines.length) throw new Error("东方财富板块K线无数据(" + secid + ")");
  const dates = [], open = [], close = [], high = [], low = [], vol = [];
  for (const k of klines) {
    const p = k.split(",");
    dates.push(p[0]); open.push(+p[1]); close.push(+p[2]);
    high.push(+p[3]); low.push(+p[4]); vol.push(+p[5] || 0);
  }
  return json({ ok: true, name: data.name || code, secid: secid, dates, open, close, high, low, vol });
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
    },
  });
}
