#!/usr/bin/env python3
"""对象存储（S3/MinIO/R2）全链路自检：上传 → 对象元数据 → 307 预签名 → 直出内容 → 清理。

用途：本机或服务器上验证 `STORAGE_BACKEND=s3` 这条路径真的能跑通，
而不是只看代码。默认对着本地 MinIO（见 docs/DEPLOY_2C4G.md §6/§14），
也可以对 R2/OSS 的测试桶跑一次（注意会真的产生对象与写入记录）。

用法：
    # 本地 MinIO（docker run minio/minio，见 docs/DEPLOY_2C4G.md §6.5）
    export S3_ENDPOINT=http://127.0.0.1:19000 S3_BUCKET=sakura-media \
           S3_ACCESS_KEY=... S3_SECRET_KEY=... S3_REGION=us-east-1
    backend/.venv/bin/python scripts/verify_s3.py --base-url http://127.0.0.1:8002

前置：目标后端进程必须已用同一套 S3_* 配置启动（STORAGE_BACKEND=s3）；
需要一个能上传的演示账号口令（默认读 backend/.seed-demo-credentials.json）。

退出码 0 表示全部通过；1 表示有失败项（会打印 FAIL 明细）。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

import boto3
import httpx
from botocore.config import Config
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDS = REPO_ROOT / "backend" / ".seed-demo-credentials.json"

failures: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if not ok else ""))
    if not ok:
        failures.append(name)


def load_password(creds_path: Path) -> str:
    if os.environ.get("SEED_DEMO_PASSWORD"):
        return os.environ["SEED_DEMO_PASSWORD"]
    data = json.loads(creds_path.read_text())
    return data["password"]


def make_image(fmt: str, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def s3_client() -> object:
    missing = [k for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"缺少环境变量: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION") or "us-east-1",
        use_ssl=os.environ.get("S3_USE_SSL", "false").lower() == "true",
        config=Config(signature_version="s3v4"),
    )


def expect_redirect(
    client: httpx.Client, root: str, path: str, label: str, expect_type: str, headers: dict
) -> None:
    # 待审/未公开作品需要 owner token；预签名 URL 本身不带鉴权。
    r = client.get(f"{root}{path}", headers=headers, follow_redirects=False)
    check(f"{label} 307", r.status_code == 307, f"{r.status_code} {r.text[:160]}")
    location = r.headers.get("location", "")
    check(
        f"{label} 预签名跳转",
        bool(location) and "X-Amz-Signature" in location,
        location[:160],
    )
    check(f"{label} 307 不长缓存", "private" in (r.headers.get("cache-control") or ""), r.headers.get("cache-control"))
    r2 = client.get(location, follow_redirects=True)
    check(f"{label} 直出 200", r2.status_code == 200, str(r2.status_code))
    check(
        f"{label} content-type {expect_type}",
        expect_type in (r2.headers.get("content-type") or ""),
        r2.headers.get("content-type"),
    )
    check(f"{label} 非空", len(r2.content) > 100, str(len(r2.content)))


def main() -> int:
    ap = argparse.ArgumentParser(description="验证 STORAGE_BACKEND=s3 全链路")
    ap.add_argument("--base-url", default="http://127.0.0.1:8002", help="已切到 s3 后端的服务地址")
    ap.add_argument("--identifier", default="jackwpp", help="演示账号用户名")
    ap.add_argument("--creds", default=str(DEFAULT_CREDS), help="演示账号口令 JSON")
    ap.add_argument("--keep", action="store_true", help="保留测试数据（默认清理）")
    args = ap.parse_args()

    root = args.base_url.rstrip("/")
    api = f"{root}/api/v1"
    bucket = os.environ["S3_BUCKET"]
    s3 = s3_client()
    password = load_password(Path(args.creds))
    created: list[str] = []

    db_url = os.environ.get("DB_SYNC_URL", "").replace("+asyncpg", "+psycopg2")

    with httpx.Client(timeout=60) as client:
        r = client.post(f"{api}/auth/login", json={"identifier": args.identifier, "password": password})
        check("登录", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        if r.status_code != 200:
            return 1
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # ── 1. 上传普通照片（走 process → persist → S3） ──
        r = client.post(
            f"{api}/photos/upload",
            params={"enable_ai": "false"},
            data={"aigc_declared": "false", "title": "S3 自检 · 普通照片", "author": "verify_s3"},
            files={"file": ("verify-s3.jpg", make_image("JPEG", (1200, 800), (200, 90, 120)), "image/jpeg")},
            headers=headers,
        )
        check("上传普通照片 201", r.status_code == 201, f"{r.status_code} {r.text[:240]}")
        if r.status_code != 201:
            return 1
        pid = r.json()["id"]
        created.append(pid)

        r = client.get(f"{api}/photos/{pid}", headers=headers)
        check("详情可读", r.status_code == 200, str(r.status_code))
        photo = r.json()

        # ── 2. 对象存在 + Content-Type/Cache-Control 元数据 ──
        for name, key in (
            ("original", photo.get("original_path")),
            ("thumbnail", photo.get("thumb_path")),
            ("compressed", photo.get("compressed_path")),
        ):
            if not key:
                check(f"{name} key 存在", False, str(key))
                continue
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
                check(f"{name} 对象存在", True)
                check(f"{name} Content-Type", (head.get("ContentType") or "").startswith("image/"), head.get("ContentType"))
                check(f"{name} Cache-Control", "immutable" in (head.get("CacheControl") or ""), head.get("CacheControl"))
            except Exception as exc:  # noqa: BLE001
                check(f"{name} 对象存在", False, f"{key}: {exc}")

        variants = photo.get("variants") or {}
        check("公开详情带 variants", bool(variants), str(variants)[:200])
        for size_key, entry in variants.items():
            for fmt, suffix in (("webp", "webp"), ("jpeg", "jpg")):
                if not entry.get(fmt):
                    continue
                key = f"variants/{pid}_{size_key}.{suffix}"
                try:
                    head = s3.head_object(Bucket=bucket, Key=key)
                    expected = "image/webp" if fmt == "webp" else "image/jpeg"
                    check(f"variant {size_key}.{suffix} 存在", True)
                    check(f"variant {size_key}.{suffix} Content-Type", head.get("ContentType") == expected, head.get("ContentType"))
                except Exception as exc:  # noqa: BLE001
                    check(f"variant {size_key}.{suffix} 存在", False, f"{key}: {exc}")

        # ── 3. 媒体端点：307 预签名 + 对象存储直出（不占 Python 带宽） ──
        expect_redirect(client, root, f"/api/v1/photos/{pid}/image/thumbnail", "缩略图", "image/jpeg", headers)
        expect_redirect(client, root, f"/api/v1/photos/{pid}/image/variant/640?format=webp", "变体 640 webp", "image/webp", headers)
        r = client.get(f"{root}/api/v1/photos/{pid}/image/variant/2400?format=webp", headers=headers, follow_redirects=False)
        check("缺档位兜底 307", r.status_code == 307, str(r.status_code))

        # ── 4. AIGC 下载：从 S3 local_copy 原图 + 写 XMP 隐式标识 ──
        r = client.post(
            f"{api}/photos/upload",
            params={"enable_ai": "false"},
            data={
                "aigc_declared": "true",
                "aigc_model": "qwen-image-3.0-pro",
                "aigc_provider": "阿里云百炼",
                "aigc_prompt": "verify_s3 aigc",
                "aigc_prompt_public": "true",
                "title": "S3 自检 · AIGC",
                "author": "verify_s3",
            },
            files={"file": ("verify-s3-aigc.png", make_image("PNG", (640, 480), (40, 120, 200)), "image/png")},
            headers=headers,
        )
        check("上传 AIGC 201", r.status_code == 201, f"{r.status_code} {r.text[:240]}")
        if r.status_code == 201:
            apid = r.json()["id"]
            created.append(apid)
            r = client.get(f"{api}/photos/{apid}/download", headers=headers)
            check("AIGC 下载 200", r.status_code == 200, str(r.status_code))
            check("X-AIGC-Label", r.headers.get("x-aigc-label") == "AIGC", r.headers.get("x-aigc-label"))
            check("X-AIGC-Implicit-Label", r.headers.get("x-aigc-implicit-label") == "xmp", r.headers.get("x-aigc-implicit-label"))
            check("下载字节含 XMP", b"sakura:IsAIGC" in r.content, "missing sakura:IsAIGC")
            try:
                Image.open(io.BytesIO(r.content)).verify()
                check("下载图可解码", True)
            except Exception as exc:  # noqa: BLE001
                check("下载图可解码", False, str(exc))

    # ── 5. 清理（对象 + 记录） ──
    if args.keep:
        print("keep=True，保留测试数据:", created)
    else:
        from sqlalchemy import create_engine, text

        if not db_url:
            print("WARN 未设置 DB_SYNC_URL（或 DATABASE_URL），跳过数据库清理；请手动删除 photos:", created)
        else:
            engine = create_engine(db_url)
            with engine.begin() as conn:
                for pid in created:
                    row = conn.execute(
                        text("select original_path, thumb_path, compressed_path, exif_data from photos where id=:id"),
                        {"id": pid},
                    ).first()
                    if row:
                        keys = [row[0], row[1], row[2]]
                        meta = row[3] or {}
                        for size_key in (meta.get("_variants") or {}):
                            keys += [f"variants/{pid}_{size_key}.webp", f"variants/{pid}_{size_key}.jpg"]
                        for key in keys:
                            if key:
                                try:
                                    s3.delete_object(Bucket=bucket, Key=key)
                                except Exception:  # noqa: BLE001
                                    pass
                    conn.execute(text("delete from photos where id=:id"), {"id": pid})
            print("清理完成:", created)

    print("\nRESULT:", "PASS" if not failures else f"{len(failures)} 项失败: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
