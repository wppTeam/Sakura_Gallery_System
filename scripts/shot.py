#!/usr/bin/env python3
"""用 Chrome DevTools Protocol 给页面拍**真实等待后**的整页截图。

为什么不用 `chrome --screenshot`：headless 的 `--virtual-time-budget` 与图片
懒加载 / CSS 过渡相互作用不稳定，常拍到 LQIP 占位而非真图。这里用 CDP
导航 + 真实等待（等到图片 load 完或超时）再截整页。

依赖（仅本地评审用，不在 requirements 里）：
    pip install websocket-client

用法：
    python3 scripts/shot.py http://127.0.0.1:5174/ .tmp-shots/home.png \
        [--width 1440] [--height 1200] [--wait 3] [--full]

可选 --token TOKEN：先注入 localStorage.auth_token 再导航（用于审核后台等鉴权页）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket  # type: ignore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_devtools(port: int, timeout: float = 20.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1))
            return data["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.15)
    raise SystemExit("devtools 没起来，检查 chrome 是否可用")


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.seq = 0
        self.target = None
        self.session = None
        self._cmd("Target.createTarget", {"url": "about:blank"}, session=False)
        targets = self._cmd("Target.getTargets", session=False)["targetInfos"]
        page = next(t for t in targets if t["type"] == "page")
        self.target = page["targetId"]
        self.session = self._cmd("Target.attachToTarget", {"targetId": self.target, "flatten": True}, session=False)["sessionId"]

    def _send(self, method: str, params: dict | None = None, session: bool = True) -> int:
        self.seq += 1
        msg = {"id": self.seq, "method": method, "params": params or {}}
        if session and self.session:
            msg["sessionId"] = self.session
        self.ws.send(json.dumps(msg))
        return self.seq

    def _cmd(self, method: str, params: dict | None = None, session: bool = True, timeout: float = 60.0):
        mid = self._send(method, params, session=session)
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)

    def eval(self, expr: str):
        r = self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("value")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--wait", type=float, default=3.0, help="导航后额外等待秒数（图仍会先等 load）")
    ap.add_argument("--full", action="store_true", help="截整页（高度自适应）")
    ap.add_argument("--tall", type=int, default=0, help="导航前就把视口设为该高度（懒加载友好，用于整页评审再裁切）")
    ap.add_argument("--token", default=None, help="注入 localStorage.auth_token")
    args = ap.parse_args()

    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise SystemExit("找不到 google-chrome / chromium")

    port = _free_port()
    profile = tempfile.mkdtemp(prefix="shot-profile-")
    proc = subprocess.Popen(
        [
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
            "--disable-dev-shm-usage", "--force-device-scale-factor=1",
            f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--remote-allow-origins=*",
            f"--window-size={args.width},{args.height}", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        cdp = CDP(_wait_devtools(port))
        cdp._cmd("Page.enable")
        cdp._cmd("Network.enable")
        # 动画/过渡在无头截图里容易停在初始帧（图片 opacity:0），统一按"减少动效"渲染
        cdp._cmd("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
        start_height = args.tall or args.height
        cdp._cmd("Emulation.setDeviceMetricsOverride", {
            "width": args.width, "height": start_height, "deviceScaleFactor": 1, "mobile": args.width < 500,
        })
        if args.token:
            # 先加载同源应用页，等 localStorage 可用后写入 token，再导航目标路由
            # （直接写 favicon 之类非文档页容易在 commit 前 eval 落空）
            host = args.url.split("/")[0] + "//" + args.url.split("/")[2]
            cdp._cmd("Page.navigate", {"url": host + "/"})
            inject_deadline = time.time() + 15
            while time.time() < inject_deadline:
                try:
                    if cdp.eval("!!window.localStorage") == "true":
                        break
                except Exception:
                    pass
                time.sleep(0.25)
            cdp.eval(f"localStorage.setItem('auth_token', {json.dumps(args.token)})")
            cdp.eval("!!window.localStorage.getItem('auth_token')")
        cdp._cmd("Page.navigate", {"url": args.url})
        # 等 load + 图片解码
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                state = cdp.eval("document.readyState")
            except Exception:
                state = None
            if state == "complete":
                break
            time.sleep(0.15)
        # 懒加载图片只有在视口覆盖到它们时才触发加载；整页截图会先把视口拉高，
        # 因此顺序必须是：先拉高视口 -> 把所有 img 改成 eager 并触发重载 -> 轮询等到全部 complete。
        if args.full and not args.tall:
            metrics = cdp._cmd("Page.getLayoutMetrics")
            size = metrics["cssContentSize"]
            cdp._cmd("Emulation.setDeviceMetricsOverride", {
                "width": args.width, "height": int(size["height"]), "deviceScaleFactor": 1, "mobile": args.width < 500,
            })
            time.sleep(0.4)
        cdp.eval(
            "Array.from(document.images).forEach(i => {"
            "  i.loading = 'eager';"
            "  if (!i.complete && i.dataset.reloaded !== '1') {"
            "    i.dataset.reloaded = '1'; const s = i.getAttribute('src'); if (s) { i.src = s; }"
            "  }"
            "}); true"
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                done = cdp.eval(
                    "Array.from(document.images).every(i => i.complete || !i.getAttribute('src'))"
                )
            except Exception:
                done = False
            if done:
                break
            time.sleep(0.3)
        time.sleep(args.wait)
        # 重要：headless=new 的 surface 截图会丢掉图片层（拍到的是背景占位），
        # fromSurface=False 走渲染器渲染，才是页面真实外观。
        shot = cdp._cmd("Page.captureScreenshot", {"format": "png", "fromSurface": False, "captureBeyondViewport": False})
        with open(args.out, "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))
        print(f"saved {args.out}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
