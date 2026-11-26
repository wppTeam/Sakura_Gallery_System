#!/usr/bin/env python3
"""刷新 Cloudflare 边缘缓存里的 HTML 壳（发版后必跑，避免旧壳引用已删除的 hashed asset）。

背景：线上给 `buct-sakura.cn` 配了两条 Cache Rule（见 docs/DEPLOY_2C4G.md §15.9）：
- SPA 壳 `/`（以及非 /api、非 /admin 的 GET）边缘缓存 20s；
- 匿名公开 GET API 边缘缓存 30s。
发版后浏览器可能拿到"旧 HTML + 旧 asset 文件名"，而新镜像已不带旧 asset → 白屏。
该脚本调用 Cloudflare Purge API 清掉 HTML 文件缓存，让新壳立刻生效。

凭据只从环境变量读取，不写入仓库：
    CF_API_TOKEN   Cloudflare API Token（Zone → Cache Purge 权限）
    CF_ZONE_ID     buct-sakura.cn 的 Zone ID（可选，缺省用 --zone）

用法：
    CF_API_TOKEN=... CF_ZONE_ID=... python3 scripts/purge_cloudflare_cache.py
    python3 scripts/purge_cloudflare_cache.py --zone <zone_id> --token <token>
    python3 scripts/purge_cloudflare_cache.py --all   # 整个 zone 全清（慎用）

退出码：0 成功；1 配置/网络/API 错误。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"

DEFAULT_FILES = (
    "https://buct-sakura.cn/",
    "https://www.buct-sakura.cn/",
    "https://buct-sakura.cn/index.html",
    "https://www.buct-sakura.cn/index.html",
)


def _prefer_ipv4() -> None:
    """部分开发机/校园网对 api.cloudflare.com 的 IPv6 只黑洞不拒绝，urllib 会卡到超时。
    这里优先 IPv4，仍保留原解析结果作为兜底。"""
    original = socket.getaddrinfo

    def _v4_first(host, port, family=0, type=0, proto=0, flags=0):  # noqa: ANN001
        infos = original(host, port, family, type, proto, flags)
        v4 = [info for info in infos if info[0] == socket.AF_INET]
        return v4 + [info for info in infos if info[0] != socket.AF_INET]

    socket.getaddrinfo = _v4_first


def purge(zone: str, token: str, *, files: tuple[str, ...] = (), everything: bool = False) -> dict:
    if everything:
        payload = {"purge_everything": True}
    else:
        payload = {"files": list(files or DEFAULT_FILES)}
    req = urllib.request.Request(
        f"{API}/zones/{zone}/purge_cache",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Purge Cloudflare HTML shell cache")
    parser.add_argument("--token", default=os.environ.get("CF_API_TOKEN", ""))
    parser.add_argument("--zone", default=os.environ.get("CF_ZONE_ID", ""))
    parser.add_argument("--all", action="store_true", help="purge everything in the zone")
    args = parser.parse_args(argv)

    if not args.token or not args.zone:
        print("缺少凭据：请设置 CF_API_TOKEN / CF_ZONE_ID，或传 --token/--zone", file=sys.stderr)
        return 1
    _prefer_ipv4()
    try:
        data = purge(args.zone, args.token, everything=args.all)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:1000]}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - 运维脚本，统一错误出口
        print(f"purge failed: {exc}", file=sys.stderr)
        return 1
    if not data.get("success"):
        print(f"Cloudflare API error: {json.dumps(data.get('errors'), ensure_ascii=False)}", file=sys.stderr)
        return 1
    scope = "everything" if args.all else f"{len(DEFAULT_FILES)} html files"
    print(f"purged: {scope} (zone {args.zone})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
