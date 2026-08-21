// stock-a 状态代理：GET /api/status → 读隧道注册表 → 转发 GET {url}/status（红绿灯数据源）
// 与 trigger.js 同模式：注册表项目 stock-a-trigger-target.pages.dev/api/target
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (context.request.method !== "GET") {
    return json({ ok: false, error: "method not allowed" }, 405);
  }
  const REGISTRY = "https://stock-a-trigger-target.pages.dev/api/target";
  try {
    // 加时间戳绕过边缘缓存，保证拿到最新隧道
    const regResp = await fetch(REGISTRY + "?ts=" + Date.now());
    if (!regResp.ok) throw new Error("注册表不可达 (" + regResp.status + ")");
    const reg = await regResp.json();
    const resp = await fetch((reg.url || "") + "/status", { method: "GET" });
    let body = { ok: false };
    try { body = await resp.json(); } catch (e) { /* 非 JSON 响应 */ }
    return json(body, resp.status);
  } catch (e) {
    // 隧道离线/本地服务未启动 → 前端显示「状态离线」灰灯
    return json({ ok: false, state: "offline", error: "状态链路故障: " + e.message }, 502);
  }
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
