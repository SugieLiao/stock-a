#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
login_jzxt.py — 均占系统(ghxb.site/jzxt)自动登录，换取 Bearer token 写入 data/.jzxt_token。

复刻前端登录流程（来自 /jzxt/assets/index-*.js 逆向）：
  1) GET  /api/admin/common/auth/challenge → {requestId, secretKey}
  2) 用 secretKey 字符串 UTF-8 编码作为 AES-256-GCM 密钥，随机 12 字节 IV，
     加密密码明文 → {iv: base64, encryptedData: base64}（与前端 WebCrypto 分支一致）
  3) POST /api/admin/c-auth/login
     body: {username, password: encryptedData, clientId, grantType:"password",
            requestId, iv}
  4) 响应 data.accessToken → 写入 data/.jzxt_token，并验证 daily/range 可用。

用法（推荐，交互式，密码不回显、不进 shell history）：
  login_jzxt.py
      运行后提示输入用户名和密码，密码输入时屏幕不显示任何字符。

兼容模式（不推荐在共享机器上使用）：
  login_jzxt.py <用户名> <密码>      # 命令行传参（密码可能留在 shell history）
  JZXT_USER=x JZXT_PASS=y login_jzxt.py   # 或用环境变量

优先级：命令行参数 > 环境变量 > 交互式输入。
"""
import json, os, sys, base64, datetime, getpass, urllib.request, urllib.error
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
TOKEN_FILE = os.path.join(DATA, ".jzxt_token")
HOST = "http://www.ghxb.site"
CLIENT_ID = "dxb_c_end_h5_97aea4dcddd24d68a4054727b145b5d4"


def http_json(url, method="GET", data=None, token=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    try:
        with urllib.request.urlopen(req, body, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return json.loads(raw)
        except Exception:
            return {"code": "HTTP%d" % e.code, "message": raw[:200]}


def aes_gcm_encrypt(key_str, plain):
    """与前端一致：key=TextEncoder(secretKey)，iv=12B 随机，tagLength=128，输出标准 base64。"""
    key = key_str.encode("utf-8")
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plain.encode("utf-8"), None)
    return base64.b64encode(iv).decode(), base64.b64encode(ct).decode()


def main():
    args = sys.argv[1:]
    user = args[0] if len(args) > 0 else os.environ.get("JZXT_USER", "")
    pwd = args[1] if len(args) > 1 else os.environ.get("JZXT_PASS", "")

    # 交互式输入：密码用 getpass 不回显，不经过命令行参数、不落盘
    if not user:
        user = input("均占系统用户名: ").strip()
    if not pwd:
        pwd = getpass.getpass("均占系统密码（输入时不显示）: ")
    if not user or not pwd:
        print("[login] 用户名或密码为空")
        sys.exit(2)

    # 1) challenge
    ch = http_json(HOST + "/api/admin/common/auth/challenge")
    if not (ch.get("success") or ch.get("code") == "0000"):
        print("[login] challenge 失败:", json.dumps(ch, ensure_ascii=False)[:300])
        sys.exit(1)
    d = ch.get("data") or {}
    request_id = d.get("requestId")
    secret_key = d.get("secretKey")
    if not request_id or not secret_key:
        print("[login] challenge 缺少 requestId/secretKey:", json.dumps(d, ensure_ascii=False)[:300])
        sys.exit(1)

    # 2) 加密密码
    iv, enc = aes_gcm_encrypt(secret_key, pwd)

    # 3) 登录
    payload = {"username": user, "password": enc, "clientId": CLIENT_ID,
               "grantType": "password", "requestId": request_id, "iv": iv}
    lg = http_json(HOST + "/api/admin/c-auth/login", "POST", payload)
    if not (lg.get("success") or lg.get("code") == "0000"):
        print("[login] 登录失败:", json.dumps(lg, ensure_ascii=False)[:300])
        sys.exit(1)
    tok = (lg.get("data") or {}).get("accessToken")
    if not tok:
        print("[login] 响应缺少 accessToken:", json.dumps(lg, ensure_ascii=False)[:300])
        sys.exit(1)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok)
    print("[login] 登录成功，token 已写入 %s（%d 字符）" % (TOKEN_FILE, len(tok)))

    # 4) 验证 token：拉 daily/range 确认有效，并打印最新数据日期
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    start = now - datetime.timedelta(days=180)
    S = int(datetime.datetime(start.year, start.month, start.day, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp() * 1000)
    E = int(datetime.datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp() * 1000)
    url = (HOST + "/api/admin/daily/range?from=dxb&marketType=sub&startTime=%d&endTime=%d") % (S, E)
    v = http_json(url, token=tok)
    if v.get("code") == "0000" and v.get("data"):
        dates = (v.get("data") or {}).get("dates") or []
        print("[login] token 验证通过，均线占用率数据范围: %s → %s（%d 个交易日）"
              % (dates[0], dates[-1], len(dates)))
    else:
        print("[login] 警告: token 已写入但验证请求异常:", json.dumps(v, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
