#!/usr/bin/env python3
# Cloudflare Pages 发布脚本（从 /tmp/cfpub 用 Assets API 部署到 stock-a 项目）。
# 凭据从环境变量读取：CF_TOKEN（Cloudflare API Token）、CF_ACCOUNT（账户 ID）。
# 由 daily_pipeline.py 调用；BASEDIR 默认 /tmp/cfpub（发布源）。
import os, sys, json, base64, hashlib, mimetypes, urllib.request, urllib.error

TOKEN = os.environ.get("CF_TOKEN")
ACCT = os.environ.get("CF_ACCOUNT")
if not TOKEN or not ACCT:
    print("缺少 CF_TOKEN / CF_ACCOUNT"); sys.exit(1)

BASE = "https://api.cloudflare.com/client/v4"
APIH = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}

def api(method, path, body=None, extra=None, raw_body=None):
    url = BASE + path
    headers = dict(APIH)
    data = None
    if raw_body is not None:
        data = raw_body
        if extra: headers.update(extra)
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        if extra: headers.update(extra)
    else:
        if extra: headers.update(extra)
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

# 1) upload JWT
c, t = api("GET", f"/accounts/{ACCT}/pages/projects/stock-a/upload-token")
print("1) upload-token http=", c)
jwt = json.loads(t).get("result", {}).get("jwt")
if not jwt:
    print("无 jwt，终止"); sys.exit(1)

# 2) gather files
BASEDIR = os.environ.get("CF_PUB_DIR", "/tmp/cfpub")
files = []
for root, _, fs in os.walk(BASEDIR):
    for fn in fs:
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, BASEDIR).replace(os.sep, "/")
        if rel.startswith("."):
            continue
        files.append((rel, full))
print("2) files:", [f[0] for f in files])

def md5hex(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

file_hashes = {rel: md5hex(full) for rel, full in files}

# 3) check-missing
c, t = api("POST", "/pages/assets/check-missing", {"hashes": list(file_hashes.values())},
           extra={"Authorization": "Bearer " + jwt})
print("3) check-missing http=", c)
try:
    missing = json.loads(t) if c == 200 else list(file_hashes.values())
except Exception:
    missing = list(file_hashes.values())
if not isinstance(missing, list):
    missing = list(file_hashes.values())
print("   missing count:", len(missing))

# 4) upload missing
to_up = [(rel, full) for rel, full in files if file_hashes[rel] in missing]
payload = []
for rel, full in to_up:
    data = open(full, "rb").read()
    ctype = "text/html; charset=utf-8" if rel.endswith(".html") else (mimetypes.guess_type(rel)[0] or "application/octet-stream")
    payload.append({"key": file_hashes[rel], "value": base64.b64encode(data).decode(),
                    "metadata": {"contentType": ctype}, "base64": True})
c, t = api("POST", "/pages/assets/upload", payload, extra={"Authorization": "Bearer " + jwt})
print("4) upload http=", c, "|", t[:160])

# 5) upsert-hashes
c, t = api("POST", "/pages/assets/upsert-hashes", {"hashes": list(file_hashes.values())},
           extra={"Authorization": "Bearer " + jwt})
print("5) upsert-hashes http=", c)

# 6) manifest + deployment
manifest = {"/" + rel: file_hashes[rel] for rel, _ in files}
boundary = "----cfbound_" + os.urandom(8).hex()
body = b""
for k, v in (("manifest", json.dumps(manifest)), ("branch", "main")):
    body += ("--" + boundary + "\r\n").encode()
    body += ('Content-Disposition: form-data; name="%s"\r\n' % k).encode()
    body += b"\r\n"
    body += (v.encode() if isinstance(v, str) else v)
    body += b"\r\n"
body += ("--" + boundary + "--\r\n").encode()
ctype = "multipart/form-data; boundary=" + boundary

c, t = api("POST", f"/accounts/{ACCT}/pages/projects/stock-a/deployments",
           raw_body=body, extra={"Content-Type": ctype, "Authorization": "Bearer " + TOKEN})
print("6) deployment http=", c)
try:
    d = json.loads(t)
    res = d.get("result", {})
    print("   deployment id:", res.get("id"))
    print("   url:", res.get("url"))
    print("   environment:", res.get("environment"))
except Exception:
    print("   raw:", t[:300])
print("== 完成 ==")
