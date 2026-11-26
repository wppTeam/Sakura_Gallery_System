#!/usr/bin/env python3
"""发版后自检：purge Cloudflare 边缘缓存 + 校验站点外壳/静态资源/公开 API。

背景：2026-11-26 生产出现「旧 shell 引用已下线 hashed asset → 白屏」，
根因是部署后没有清 Cloudflare 边缘缓存、且浏览器把 HTML 缓存了 4 小时。
这个脚本把「发版后必须做的事」固化成一条命令，出错时退出码非 0，可直接接 CI/部署脚本。

用法：
    python3 scripts/post_deploy_check.py                 # 只自检
    python3 scripts/post_deploy_check.py --purge         # 先清 CF HTML 缓存再自检
    python3 scripts/post_deploy_check.py --base https://buct-sakura.cn --purge

凭据（可选，--purge 需要）：
    CF_API_TOKEN / CF_ZONE_ID 环境变量，或本地 .tmp/deploy/cf.env（0600，不入库）
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import urllib.error
from pathlib import Path
import urllib.request

DEFAULT_BASE = "https://buct-sakura.cn"
HTML_PATHS = ["/", "/index.html", "/explore", "/login"]
API_PATHS = [
    "/api/v1/photos/public?limit=4",
    "/api/v1/collections/public?limit=4",
    "/api/v1/collections/light?per_period=2",
    "/api/v1/collections/spectrum",
    "/api/v1/tags/public/popular?limit=6",
]
ASSET_RE = re.compile(r'(?:src|href)="(/assets/[^"]+)"')


def _prefer_ipv4() -> None:
    """部分网络对 Cloudflare 的 IPv6 只黑洞不拒绝，urllib 会一直卡在连接上。"""
    original = socket.getaddrinfo

    def _v4_first(host, port, family=0, type=0, proto=0, flags=0):  # noqa: ANN001
        infos = original(host, port, family, type, proto, flags)
        v4 = [info for info in infos if info[0] == socket.AF_INET]
        return v4 + [info for info in infos if info[0] != socket.AF_INET]

    socket.getaddrinfo = _v4_first


def fetch(url: str, timeout: int = 20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; sakura-deploy-check/1.0)",
            "Connection": "close",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, dict(resp.headers), resp.read()


def purge_html_cache() -> None:
    import subprocess

    root = Path(__file__).resolve().parent.parent
    env_file = root / ".tmp" / "deploy" / "cf.env"
    cmd = [sys.executable, str(root / "scripts" / "purge_cloudflare_cache.py")]
    proc = subprocess.run(cmd, cwd=root, env=None, capture_output=True, text=True)
    print(proc.stdout.strip() or proc.stderr.strip())
    if proc.returncode != 0:
        print("!! purge 失败，请检查 CF_API_TOKEN/CF_ZONE_ID（也可手动在面板 Purge Everything）")
        sys.exit(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--purge", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    _prefer_ipv4()
    failures = []

    if args.purge:
        purge_html_cache()

    print(f"== 1. 站点外壳 {base} ==")
    html = ""
    for path in HTML_PATHS:
        try:
            status, headers, body = fetch(base + path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path} 请求失败：{exc}")
            print(f"  FAIL {path} {exc}")
            continue
        cache = headers.get("cf-cache-status", "-")
        print(f"  {status} {path}  cf-cache-status={cache}")
        if status != 200:
            failures.append(f"{path} -> HTTP {status}")
        if path in ("/", "/index.html"):
            html = body.decode("utf-8", "replace")

    assets = sorted(set(ASSET_RE.findall(html)))
    print(f"== 2. 外壳引用静态资源（{len(assets)} 个）==")

    # 与服务端本地构建产物比对：边缘/浏览器若还缓存着旧 shell，引用的 hashed 资源
    # 会与本地 dist 不一致（通常是 404 白屏的根因），这里直接报出来。
    local_index = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if local_index.exists():
        try:
            local_assets = sorted(set(ASSET_RE.findall(local_index.read_text(encoding="utf-8"))))
        except Exception:  # noqa: BLE001
            local_assets = []
        if local_assets and set(local_assets) != set(assets):
            failures.append(
                "线上 HTML 引用的资源与本地 dist 不一致——边缘缓存仍是旧 shell，"
                "请执行 --purge（或面板 Purge Everything）后重试"
            )
            print("  WARN 线上 shell 与本地 dist 不一致（边缘缓存陈旧）")
            print(f"   线上: {assets}")
            print(f"   本地: {local_assets}")
        elif local_assets:
            print("  OK 线上 shell 与本地 dist 构建一致")
    for asset in assets:
        try:
            status, headers, body = fetch(base + asset, timeout=60)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{asset} 请求失败：{exc}")
            print(f"  FAIL {asset} {exc}")
            continue
        ctype = headers.get("content-type", "")
        ok = status == 200 and len(body) > 1024
        print(f"  {'OK ' if ok else 'FAIL'} {status} {asset} ({len(body)}B, {ctype.split(';')[0]})")
        if not ok:
            failures.append(f"{asset} -> HTTP {status} / {len(body)}B")

    print(f"== 3. 公开 API ==")
    for path in API_PATHS:
        try:
            status, _headers, body = fetch(base + path)
            payload = json.loads(body)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path} 失败：{exc}")
            print(f"  FAIL {path} {exc}")
            continue
        ok = status == 200 and isinstance(payload, (dict, list))
        print(f"  {'OK ' if ok else 'FAIL'} {status} {path}")
        if not ok:
            failures.append(f"{path} -> HTTP {status}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} 项")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("PASS: 发版自检全部通过（外壳/静态资源/公开 API）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
