"""把 PG 备份上传到 S3 兼容对象存储（COS/R2/MinIO）并清理过期远端备份。

在 backend 容器内执行（宿主机无需安装 boto3）：
  docker exec sakura-prod-backend python /tmp/backup_upload.py \
    --file /tmp/backup.dump --key backups/pg-2026.dump --keep-days 30

配置直接读容器内 S3_* 环境变量（不 import 应用，避免工作目录依赖），
桶内建议开启版本控制 + 生命周期规则作为第二层保护。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


class EnvSettings:
    def __init__(self) -> None:
        self.S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "").strip()
        self.S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
        self.S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "").strip()
        self.S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "").strip()
        self.S3_REGION = os.environ.get("S3_REGION", "us-east-1").strip() or "us-east-1"
        self.S3_VERIFY = _env_bool("S3_VERIFY", True)
        self.S3_ADDRESSING_STYLE = os.environ.get("S3_ADDRESSING_STYLE", "auto").strip() or "auto"


def build_client(settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        verify=settings.S3_VERIFY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.S3_ADDRESSING_STYLE},
            connect_timeout=10,
            read_timeout=300,
            retries={"max_attempts": 3},
            # COS 不支持 AWS 新版默认的流式 CRC 校验（UnseekableStreamError /
            # MissingContentLength），关掉按需校验才能直传
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="本地备份文件路径；- 表示从 stdin 读取")
    parser.add_argument("--key", required=True, help="对象存储 key（如 backups/pg-xxx.dump）")
    parser.add_argument("--keep-days", type=int, default=30, help="远端保留天数")
    args = parser.parse_args()

    if args.file == "-":
        data = sys.stdin.buffer.read()
        size = len(data)
        if size == 0:
            print("stdin 备份数据为空", file=sys.stderr)
            return 1
    else:
        path = Path(args.file)
        if not path.is_file() or path.stat().st_size == 0:
            print(f"备份文件不存在或为空: {path}", file=sys.stderr)
            return 1
        data = None
        size = path.stat().st_size

    settings = EnvSettings()
    if not settings.S3_BUCKET:
        print("S3_BUCKET 未配置", file=sys.stderr)
        return 1
    client = build_client(settings)

    if data is not None:
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=args.key,
            Body=data,
            ContentLength=size,
            ContentType="application/octet-stream",
            Metadata={"site": "sakura-gallery", "kind": "pg-dump"},
        )
    else:
        with path.open("rb") as fh:
            client.put_object(
                Bucket=settings.S3_BUCKET,
                Key=args.key,
                Body=fh,
                ContentLength=size,
                ContentType="application/octet-stream",
                Metadata={"site": "sakura-gallery", "kind": "pg-dump"},
            )
    print(f"uploaded s3://{settings.S3_BUCKET}/{args.key} ({size} bytes)")

    if args.keep_days > 0:
        prefix = args.key.split("/", 1)[0] + "/"
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.keep_days)
        deleted = 0
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["LastModified"] < cutoff:
                    client.delete_object(Bucket=settings.S3_BUCKET, Key=obj["Key"])
                    deleted += 1
        print(f"remote prune: deleted={deleted} (keep_days={args.keep_days})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
