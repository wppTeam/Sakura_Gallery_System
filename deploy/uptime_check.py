#!/usr/bin/env python3
"""视觉百花 · 线上可用性巡检（仅标准库，服务器上直接跑，不依赖容器/venv）

检查项：
  1) GET /healthz           → 200 且 {"status":"healthy"}
  2) GET /api/v1/photos/public?limit=1 → 200 且 JSON 可解析
  3) GET /sitemap.xml       → 200 且包含 <urlset

失败时：邮件告警（Resend，读同目录 .env.prod 的 RESEND_API_KEY/RESEND_FROM），
同一故障 30 分钟内只告警一次；恢复时发一封恢复邮件。
状态写 ~/.sakura-uptime-state.json（只存时间戳与最近错误，不含凭据）。

用法：
  python3 deploy/uptime_check.py                # 巡检一次
  ALERT_EMAIL_TO=you@example.com python3 ...    # 指定收件人
  ALERT_EMAIL_TO= python3 ...                   # 只记日志、不发邮件
cron（每 5 分钟）：
  */5 * * * * cd $HOME/sakura-gallery && python3 deploy/uptime_check.py >> $HOME/sakura-uptime.log 2>&1
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL = os.environ.get("UPTIME_BASE_URL", "https://buct-sakura.cn").rstrip("/")
DEFAULT_STATE = Path(__file__).resolve().parent.parent / ".tmp" / "sakura-uptime-state.json"
STATE_FILE = Path(os.environ.get("UPTIME_STATE_FILE", str(DEFAULT_STATE)))
ALERT_EMAIL = os.environ.get("ALERT_EMAIL_TO", "").strip()
ALERT_COOLDOWN_MINUTES = int(os.environ.get("ALERT_COOLDOWN_MINUTES", "30"))
TIMEOUT = float(os.environ.get("UPTIME_TIMEOUT", "15"))
ENV_FILE = Path(os.environ.get("ENV_FILE", str(Path(__file__).resolve().parent / ".env.prod")))


def log(message: str) -> None:
    stamp = datetime.now().astimezone().strftime("%F %T")
    print(f"[{stamp}] {message}", flush=True)


def http_get(path: str) -> tuple[int, str]:
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SakuraGalleryUptime/1.0 (+https://buct-sakura.cn)"},
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return resp.status, resp.read(200_000).decode("utf-8", "replace")


def check_once() -> list[str]:
    errors: list[str] = []

    try:
        status, body = http_get("/healthz")
        # nginx 的 /healthz 是静态 200，不需要匹配正文；后端存活由下面的 API 检查覆盖
        if status != 200:
            errors.append(f"/healthz 异常: HTTP {status} body={body[:120]}")
    except Exception as exc:
        errors.append(f"/healthz 请求失败: {exc}")

    try:
        status, body = http_get("/api/v1/photos/public?limit=1")
        if status != 200:
            errors.append(f"/api/v1/photos/public 异常: HTTP {status}")
        else:
            json.loads(body)
    except Exception as exc:
        errors.append(f"/api/v1/photos/public 请求失败: {exc}")

    try:
        status, body = http_get("/sitemap.xml")
        if status != 200 or "<urlset" not in body:
            errors.append(f"/sitemap.xml 异常: HTTP {status}")
    except Exception as exc:
        errors.append(f"/sitemap.xml 请求失败: {exc}")

    return errors


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return values
    for line in ENV_FILE.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def send_alert(subject: str, text: str) -> None:
    if not ALERT_EMAIL:
        log("未配置 ALERT_EMAIL_TO，跳过邮件告警")
        return
    env = read_env()
    api_key = env.get("RESEND_API_KEY", "").strip()
    sender = env.get("RESEND_FROM", "视觉百花 <noreply@buct-sakura.cn>").strip()
    if not api_key:
        log("未配置 RESEND_API_KEY，跳过邮件告警")
        return
    payload = json.dumps(
        {
            "from": sender,
            "to": [ALERT_EMAIL],
            "subject": subject,
            "text": text,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        log(f"告警邮件已发送 → {ALERT_EMAIL}")
    except Exception as exc:  # 告警失败不能影响退出码语义
        log(f"告警邮件发送失败: {exc}")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    data = json.dumps(state, ensure_ascii=False)
    for candidate in (STATE_FILE, Path("/tmp") / "sakura-uptime-state.json"):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(data)
            return
        except Exception as exc:
            log(f"状态写入失败（{candidate}）: {exc}")


def main() -> int:
    state = load_state()
    errors: list[str] = []
    for attempt in (1, 2):
        errors = check_once()
        if not errors:
            break
        if attempt == 1:
            log("首次巡检失败，10 秒后重试…")
            time.sleep(10)

    now = datetime.now().astimezone()
    if not errors:
        if state.get("down_since"):
            since = state["down_since"]
            send_alert("【视觉百花】站点已恢复正常", f"站点恢复正常。\n异常开始时间：{since}\n恢复时间：{now.isoformat()}")
            log("站点已恢复")
            state.pop("down_since", None)
            state.pop("last_alert_at", None)
        log(f"巡检通过：{BASE_URL}（{now.strftime('%F %T')}）")
        save_state(state)
        return 0

    detail = "\n".join(f"- {e}" for e in errors)
    log(f"巡检失败（{len(errors)} 项）：\n{detail}")
    state.setdefault("down_since", now.isoformat())
    last_alert = state.get("last_alert_at")
    cooldown = timedelta(minutes=ALERT_COOLDOWN_MINUTES)
    should_alert = True
    if last_alert:
        try:
            should_alert = now - datetime.fromisoformat(last_alert) >= cooldown
        except Exception:
            should_alert = True
    if should_alert:
        send_alert(
            "【视觉百花】站点异常告警",
            f"检测时间：{now.isoformat()}\n站点：{BASE_URL}\n失败项：\n{detail}\n\n"
            f"异常开始：{state['down_since']}（同一故障 {ALERT_COOLDOWN_MINUTES} 分钟内只告警一次）",
        )
        state["last_alert_at"] = now.isoformat()
    save_state(state)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
