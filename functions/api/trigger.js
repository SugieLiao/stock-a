// stock-a 触发代理：按钮 POST /api/trigger → 读云端隧道注册表 → 转发到本机触发服务
// 按钮 HTML 已内置（render.py 模板），本函数替代丢失的旧 _worker.js
// 注册表小项目: stock-a-trigger-target.pages.dev/api/target（隧道 URL 变化时自动更新）
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (context.request.method !== "POST") {
    return json({ ok: false, error: "method not allowed" }, 405);
  }
  const cmd = url.searchParams.get("cmd") || "";
  const type = url.searchParams.get("type") || "";
  const date = url.searchParams.get("date") || "";
  const REGISTRY = "https://stock-a-trigger-target.pages.dev/api/target";
  try {
    // 加时间戳绕过边缘缓存，保证拿到最新隧道
    const regResp = await fetch(REGISTRY + "?ts=" + Date.now());
    if (!regResp.ok) throw new Error("注册表不可达 (" + regResp.status + ")");
    const reg = await regResp.json();
    const q = new URLSearchParams({ cmd, key: reg.key || "" });
    if (type) q.set("type", type);
    if (date) q.set("date", date);
    const resp = await fetch((reg.url || "") + "/trigger?" + q.toString(), { method: "POST" });
    let body = { ok: false };
    try { body = await resp.json(); } catch (e) { /* 非 JSON 响应 */ }
    return json(body, resp.status);
  } catch (e) {
    return json({ ok: false, error: "触发链路故障: " + e.message }, 502);
  }
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
