#!/usr/bin/env python3
"""AI 渠道连通性自检（不烧钱：两次极短调用）。

用法：
    cd backend && .venv/bin/python ../scripts/check_ai.py
    cd backend && .venv/bin/python ../scripts/check_ai.py --json

检查项：
1. 配置解析：AI_PROVIDER / OPENAI_COMPATIBLE_BASE_URL / AI_VISION_MODEL / AI_TEXT_MODEL
2. 文本模型（AI_TEXT_MODEL，默认 deepseek-v4.1-flash-1017）JSON 输出与延迟
3. 视觉模型（AI_VISION_MODEL，默认 qwen3-vl-plus）读图 JSON 输出与延迟
4. 成本估算是否命中 AI_MODEL_PRICES

失败时退出码 1，便于部署脚本 / CI 调用。
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


async def _vision_payload() -> str:
    from PIL import Image

    image = Image.new("RGB", (64, 64), (230, 200, 210))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


async def run(json_output: bool) -> int:
    from app.core.config import get_settings
    from app.services.ai_client import AIError, chat_json

    settings = get_settings()
    report: dict = {
        "provider": settings.AI_PROVIDER,
        "base_url": settings.OPENAI_COMPATIBLE_BASE_URL or settings.DASHSCOPE_BASE_URL,
        "text_model": settings.AI_TEXT_MODEL,
        "vision_model": settings.AI_VISION_MODEL,
        "checks": {},
    }
    ok = True

    try:
        result = await chat_json(
            db=None,
            operation="check.text",
            system="只输出 JSON，不要解释。",
            user='输出 {"ok": true, "n": 42}',
            max_tokens=200,
            temperature=0.0,
        )
        report["checks"]["text"] = {
            "ok": True,
            "model_id": result.model_id,
            "latency_ms": result.latency_ms,
            "tokens": result.total_tokens,
            "cost_usd": result.cost_usd,
            "parsed": result.data,
        }
    except AIError as exc:  # 渠道配置/网络/解析失败
        ok = False
        report["checks"]["text"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        result = await chat_json(
            db=None,
            operation="check.vision",
            system="只输出 JSON，不要解释。",
            user='这张图主要是什么颜色？输出 {"colors": ["..."]}',
            image_base64=await _vision_payload(),
            image_mime="image/jpeg",
            max_tokens=200,
            temperature=0.0,
        )
        report["checks"]["vision"] = {
            "ok": True,
            "model_id": result.model_id,
            "latency_ms": result.latency_ms,
            "tokens": result.total_tokens,
            "cost_usd": result.cost_usd,
            "parsed": result.data,
        }
    except AIError as exc:
        ok = False
        report["checks"]["vision"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    report["ok"] = ok
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"provider={report['provider']} base_url={report['base_url']}")
        for name, item in report["checks"].items():
            model = item.get("model_id", report[f"{name}_model"])
            if item["ok"]:
                print(
                    f"[OK]   {name:<6} model={model} latency={item['latency_ms']}ms "
                    f"tokens={item['tokens']} cost=${item['cost_usd']:.6f} data={item['parsed']}"
                )
            else:
                print(f"[FAIL] {name:<6} model={model} {item['error']}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 渠道连通性自检")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()
    return asyncio.run(run(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
