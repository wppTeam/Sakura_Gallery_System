#!/usr/bin/env python3
"""轻量压测脚本（只依赖 httpx，无 wrk/hey/ab 时可用）。

用于在本地 cgroup 受限的 compose 栈上模拟 2C4G 机器，测出读路径 / 检索路径的
吞吐与延迟分位数，以及后端进程的内存峰值。

用法：
    backend/.venv/bin/python scripts/loadtest.py \
        --base-url http://127.0.0.1:18080 \
        --scenario read --concurrency 16 --duration 30

场景（--scenario）：
    read     列表 + 缩略图 + 检索（fast）混合，最接近真实首页/探索页流量
    list     只看 /api/v1/photos/public
    image    只取缩略图（走本地文件/预签名，测静态资源路径）
    search   只走 /api/v1/search?mode=fast（测 SQL 排序 + 序列化）
    agent    走 /api/v1/search?mode=agent（会调外部模型，勿长时间打）

注意：这是开发用压测工具，不要在公网暴露的实例上随意跑。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx

TERMINAL = {"ok": "\033[32m", "warn": "\033[33m", "err": "\033[31m", "reset": "\033[0m"}


@dataclass
class Endpoint:
    name: str
    url: str
    weight: float = 1.0


@dataclass
class Stats:
    latencies: list[float] = field(default_factory=list)
    errors: int = 0
    total: int = 0
    by_endpoint: dict[str, list[float]] = field(default_factory=dict)
    statuses: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, latency: float, status: str, ok: bool) -> None:
        self.total += 1
        self.latencies.append(latency)
        self.by_endpoint.setdefault(name, []).append(latency)
        self.statuses[status] = self.statuses.get(status, 0) + 1
        if not ok:
            self.errors += 1


def percentile(values: Iterable[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * pct / 100.0
    low, high = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def build_endpoints(base_url: str, scenario: str, photo_id: str | None) -> list[Endpoint]:
    base = base_url.rstrip("/")
    photo = photo_id or "6e12ee4b-d80e-5aa0-94bd-5bcd233321ec"
    endpoints = {
        "list": [Endpoint("list", f"{base}/api/v1/photos/public?limit=20&offset=0", 3.0)],
        "image": [Endpoint("thumb", f"{base}/api/v1/photos/{photo}/image/thumbnail", 1.0)],
        "search": [Endpoint("search", f"{base}/api/v1/search?q=%E8%8A%B1&mode=fast&limit=20", 1.0)],
        "agent": [Endpoint("agent", f"{base}/api/v1/search?q=%E8%8A%B1&mode=agent&limit=20", 1.0)],
    }
    if scenario == "read":
        return endpoints["list"] + endpoints["search"] * 2 + endpoints["image"] * 2
    return endpoints[scenario]


async def worker(
    client: httpx.AsyncClient,
    endpoints: list[Endpoint],
    stop_at: float,
    stats: Stats,
    lock: asyncio.Lock,
) -> None:
    weights = [ep.weight for ep in endpoints]
    while time.perf_counter() < stop_at:
        ep = random.choices(endpoints, weights=weights, k=1)[0]
        started = time.perf_counter()
        status = "exception"
        try:
            resp = await client.get(ep.url)
            status = str(resp.status_code)
        except Exception as exc:  # noqa: BLE001 - 压测里任何异常都算失败
            status = type(exc).__name__
        latency = (time.perf_counter() - started) * 1000.0
        ok = status.isdigit() and 200 <= int(status) < 400
        async with lock:
            stats.add(ep.name, latency, status, ok)


async def run(args: argparse.Namespace) -> int:
    endpoints = build_endpoints(args.base_url, args.scenario, args.photo_id)
    limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=args.concurrency)
    timeout = httpx.Timeout(args.timeout)
    stats = Stats()
    lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        # 预热，避免把首请求建连/缓存冷启动算进结果
        for _ in range(args.warmup):
            try:
                await client.get(random.choice(endpoints).url)
            except Exception:  # noqa: BLE001
                pass

        started = time.perf_counter()
        stop_at = started + args.duration
        await asyncio.gather(
            *(worker(client, endpoints, stop_at, stats, lock) for _ in range(args.concurrency))
        )
        elapsed = time.perf_counter() - started

    errors = stats.errors
    rate = (stats.total - errors) / elapsed if elapsed else 0.0
    p50 = percentile(stats.latencies, 50)
    p95 = percentile(stats.latencies, 95)
    p99 = percentile(stats.latencies, 99)
    color = TERMINAL["ok"] if errors == 0 else TERMINAL["warn"]
    print(
        f"{color}[{args.scenario}] {rate:.1f} req/s · "
        f"p50 {p50:.0f}ms · p95 {p95:.0f}ms · p99 {p99:.0f}ms · "
        f"err {errors}/{stats.total}{TERMINAL['reset']}"
    )
    if errors:
        print("  status:", json.dumps(stats.statuses, ensure_ascii=False))
    for name, values in sorted(stats.by_endpoint.items()):
        if not values:
            continue
        print(
            f"  - {name:<8} n={len(values):<6} "
            f"p50={percentile(values, 50):.0f}ms p95={percentile(values, 95):.0f}ms "
            f"avg={statistics.fmean(values):.0f}ms"
        )

    if args.json_out:
        payload = {
            "scenario": args.scenario,
            "concurrency": args.concurrency,
            "duration": round(elapsed, 2),
            "rps": round(rate, 2),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(p99, 1),
            "errors": errors,
            "statuses": stats.statuses,
            "total": stats.total,
            "by_endpoint": {
                name: {
                    "n": len(values),
                    "p50_ms": round(percentile(values, 50), 1),
                    "p95_ms": round(percentile(values, 95), 1),
                    "avg_ms": round(statistics.fmean(values), 1),
                }
                for name, values in stats.by_endpoint.items()
            },
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"  report -> {args.json_out}")
    return 0 if errors == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080", help="被压测的 nginx/uvicorn 根地址")
    parser.add_argument(
        "--scenario", default="read", choices=["read", "list", "image", "search", "agent"], help="流量场景"
    )
    parser.add_argument("-c", "--concurrency", type=int, default=16, help="并发 worker 数")
    parser.add_argument("-d", "--duration", type=float, default=20.0, help="压测秒数")
    parser.add_argument("--timeout", type=float, default=10.0, help="单请求超时秒数")
    parser.add_argument("--warmup", type=int, default=5, help="预热请求数")
    parser.add_argument("--photo-id", default=None, help="缩略图场景用的作品 id")
    parser.add_argument("--json-out", default=None, help="把结果写到 JSON 文件")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
