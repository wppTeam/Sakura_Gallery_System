#!/usr/bin/env python3
"""把视觉百花接到 Cloudflare Tunnel（远端 tunnel 的 ingress + DNS）。

前置：已用 `cloudflared service install <token>` 或 compose 里的 cloudflared 容器
跑通 tunnel（token 里已含 account_id / tunnel_id）。本脚本只做两件事：

1. 用 Cloudflare API 给既有 tunnel 写 ingress 规则（hostname -> http://nginx:80）
2. 在 Zone 下建对应 CNAME 记录（<tunnel_id>.cfargotunnel.com, proxied）

需要 Cloudflare API Token，权限至少：
  Zone:buct-sakura.cn:DNS:Edit
  Account:Cloudflare Tunnel:Edit

用法：
  CF_API_TOKEN=xxx python3 scripts/setup_cloudflare_tunnel.py \
      --tunnel-token-file .tmp/deploy/tunnel.env \
      --zone buct-sakura.cn \
      --hostname buct-sakura.cn --hostname www.buct-sakura.cn \
      --service http://nginx:80

也支持先 dry-run 查看将会写入什么：加 --dry-run。
凭据只从环境变量 / 文件读取，不打印、不落库。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"


def api(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode() or "{}")
        raise SystemExit(f"[api] {method} {path} -> {exc.code}: {json.dumps(body, ensure_ascii=False)[:800]}")
    if not body.get("success"):
        raise SystemExit(f"[api] {method} {path} failed: {json.dumps(body.get('errors'), ensure_ascii=False)}")
    return body


def decode_tunnel_token(raw: str) -> dict:
    """cloudflared tunnel token 是 base64(JSON{"a":account,"t":tunnel,"s":secret})。"""
    raw = raw.strip()
    if raw.startswith("TUNNEL_TOKEN="):
        raw = raw.split("=", 1)[1].strip()
    padded = raw + "=" * (-len(raw) % 4)
    data = json.loads(base64.b64decode(padded))
    if not data.get("a") or not data.get("t"):
        raise SystemExit("[token] 无法从 tunnel token 解出 account/tunnel id")
    return data


def find_zone_id(token: str, zone: str) -> str:
    body = api("GET", f"/zones?name={zone}", token)
    if not body["result"]:
        raise SystemExit(f"[zone] 账号下找不到 zone {zone}（token 权限不足或域名不在该账号）")
    return body["result"][0]["id"]


def upsert_dns(token: str, zone_id: str, name: str, tunnel_id: str) -> str:
    content = f"{tunnel_id}.cfargotunnel.com"
    body = api("GET", f"/zones/{zone_id}/dns_records?name={name}", token)
    existing = [r for r in body["result"] if r["type"] == "CNAME"]
    if existing:
        rec = existing[0]
        if rec["content"] == content and rec.get("proxied"):
            return f"[dns] {name} 已指向 {content}，跳过"
        api("PATCH", f"/zones/{zone_id}/dns_records/{rec['id']}", token, {"content": content, "proxied": True})
        return f"[dns] {name} 更新为 {content}"
    api(
        "POST",
        f"/zones/{zone_id}/dns_records",
        token,
        {"type": "CNAME", "name": name, "content": content, "proxied": True, "ttl": 1},
    )
    return f"[dns] {name} 新建 CNAME -> {content}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-token", default=os.environ.get("CF_API_TOKEN"), help="Cloudflare API Token")
    ap.add_argument("--tunnel-token", default=os.environ.get("TUNNEL_TOKEN"), help="cloudflared tunnel token")
    ap.add_argument("--tunnel-token-file", help="包含 TUNNEL_TOKEN=... 的文件")
    ap.add_argument("--zone", required=True)
    ap.add_argument("--hostname", action="append", required=True)
    ap.add_argument("--service", default="http://nginx:80")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.api_token:
        raise SystemExit("缺少 --api-token / CF_API_TOKEN（需要 DNS:Edit + Tunnel:Edit 权限）")
    tunnel_token = args.tunnel_token
    if not tunnel_token and args.tunnel_token_file:
        tunnel_token = pathlib.Path(args.tunnel_token_file).read_text()
    if not tunnel_token:
        raise SystemExit("缺少 tunnel token（--tunnel-token / --tunnel-token-file）")

    ids = decode_tunnel_token(tunnel_token)
    account_id, tunnel_id = ids["a"], ids["t"]
    print(f"[tunnel] account={account_id[:6]}… tunnel={tunnel_id[:8]}…")

    ingress = [{"hostname": h, "service": args.service, "originRequest": {"httpHostHeader": h}} for h in args.hostname]
    ingress.append({"service": "http_status:404"})
    config = {"config": {"ingress": ingress}}

    if args.dry_run:
        print("[dry-run] tunnel ingress:", json.dumps(config, ensure_ascii=False))
        zone_id = find_zone_id(args.api_token, args.zone) if args.api_token else "<zone>"
        for h in args.hostname:
            print(f"[dry-run] dns: {h} CNAME {tunnel_id}.cfargotunnel.com proxied=true (zone={zone_id[:8]}…)")
        return 0

    api("PUT", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations", args.api_token, config)
    print(f"[tunnel] ingress 已写入：{', '.join(args.hostname)} -> {args.service}")

    zone_id = find_zone_id(args.api_token, args.zone)
    for host in args.hostname:
        print(upsert_dns(args.api_token, zone_id, host, tunnel_id))

    print("\n[next] DNS 生效后验证：")
    for host in args.hostname:
        print(f"  curl -sI https://{host}/healthz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
