#!/usr/bin/env bash
# 用本机 Google Chrome 无头模式给前端页面截图，供设计评审对照。
#
# 前置：前端 dev server 已启动（默认 http://127.0.0.1:5173），后端 8000 可选。
# 用法：
#   scripts/screenshot_pages.sh                      # 默认截 5 个页面到 .tmp-shots/
#   BASE_URL=http://127.0.0.1:5173 OUT_DIR=/tmp/a scripts/screenshot_pages.sh
#   PAGES="/:home /explore:explore" scripts/screenshot_pages.sh
#
# 输出：<out>/<name>-desktop.png、<out>/<name>-mobile.png
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5173}"
OUT_DIR="${OUT_DIR:-.tmp-shots}"
CHROME_BIN="${CHROME_BIN:-$(command -v google-chrome || command -v chromium || true)}"
WAIT_MS="${WAIT_MS:-9000}"
PAGES="${PAGES:-/:home /explore:explore /search?q=%E6%A8%B1%E8%8A%B1:search}"

if [[ -z "$CHROME_BIN" ]]; then
  echo "未找到 chrome/chromium，可用 CHROME_BIN=/path/to/chrome 指定" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
profile_dir="$(mktemp -d)"
trap 'rm -rf "$profile_dir"' EXIT

shot() {
  local url="$1" file="$2" size="$3"
  "$CHROME_BIN" \
    --headless=new --disable-gpu --no-first-run --no-default-browser-check \
    --hide-scrollbars --force-device-scale-factor=1 \
    --user-data-dir="$profile_dir" \
    --window-size="$size" \
    --virtual-time-budget="$WAIT_MS" \
    --screenshot="$file" \
    "$url" >/dev/null 2>&1 || echo "截图失败（忽略）: $url"
  [[ -f "$file" ]] && echo "✓ $file"
}

for spec in $PAGES; do
  path="${spec%%:*}"
  name="${spec##*:}"
  [[ "$name" == "$spec" ]] && name="$(echo "$path" | sed 's#[/?=&%]#_#g' | cut -c1-40)"
  shot "${BASE_URL}${path}" "${OUT_DIR}/${name}-desktop.png" "1440,2200"
  shot "${BASE_URL}${path}" "${OUT_DIR}/${name}-mobile.png" "390,1600"
done
