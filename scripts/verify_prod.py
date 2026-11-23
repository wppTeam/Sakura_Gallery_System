#!/usr/bin/env python3
"""服务器上跑的生产链路自检（仅标准库）：python3 verify_prod.py [BASE]"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"
fails = []


def get(path, expect=200, headers=None, follow=True):
    url = BASE + path
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            code = r.status
            ctype = r.headers.get("content-type", "")
            cache = r.headers.get("cache-control", "")
    except urllib.error.HTTPError as e:
        body, code, ctype, cache = e.read(), e.code, e.headers.get("content-type", ""), e.headers.get("cache-control", "")
    ok = code == expect
    if not ok:
        fails.append(f"{path} -> {code} (expect {expect})")
    print(f"[{'OK ' if ok else 'FAIL'}] {code} {path[:64]:64s} {ctype[:30]:30s} {cache[:40]}")
    return code, body, dict(ctype=ctype, cache=cache)


# 1. 静态站点
get("/", 200)
get("/explore", 200)
get("/healthz", 200)

# 2. 公开列表 + 缩略图 + 变体
code, body, _ = get("/api/v1/photos/public?limit=2", 200)
data = json.loads(body)
items = data.get("items", [])
total = data.get("total")
print(f"      total={total} first={items[0]['title'][:20] if items else None}")
if not items:
    fails.append("photos/public empty")
else:
    it = items[0]
    get(f"/api/v1/photos/{it['id']}/image/thumbnail", 200)
    variants = it.get("variants") or {}
    print(f"      variants={sorted(variants)} lqip={'yes' if it.get('lqip') else 'no'}")
    if variants:
        k = sorted(variants)[0]
        get(variants[k]["webp"], 200)

# 3. 检索（fast）
get("/api/v1/search?q=%E6%A8%B1%E8%8A%B1&mode=fast", 200)
# 4. 专题
code, body, _ = get("/api/v1/collections/public", 200)
c = json.loads(body)
print(f"      collections total={c.get('total')} first={(c.get('items') or [{}])[0].get('slug')}")

# 5. 鉴权边界
get("/api/v1/admin/moderation/queue", 401)
get("/api/v1/photos/favorites/my", 401)

# 6. 登录（演示审核员）——口令不打印
creds_path = "/home/wppjkw/sakura-gallery/backend/.seed-demo-credentials.json"
try:
    with open(creds_path, encoding="utf-8") as f:
        creds = json.load(f)
    password = creds["password"]
    req = urllib.request.Request(
        BASE + "/api/v1/auth/login",
        data=json.dumps({"identifier": "seed-auditor", "password": password}).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.loads(r.read())["access_token"]
        print("[OK ] login seed-auditor -> token ok")
        get("/api/v1/admin/moderation/queue?limit=3", 200, headers={"authorization": f"Bearer {tok}"})
    except urllib.error.HTTPError as e:
        fails.append(f"login -> {e.code}")
        print(f"[FAIL] login -> {e.code}")
except FileNotFoundError:
    print("      (no seed credentials file, skip login)")

print()
if fails:
    print("FAILURES:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
