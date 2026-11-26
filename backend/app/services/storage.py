"""
Storage backends for local filesystem and S3-compatible object storage.
"""
import logging
from functools import lru_cache
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Iterable

from fastapi import UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.core.config import get_settings

settings = get_settings()

try:
    import boto3
    from botocore.client import Config as BotoConfig
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local mode
    boto3 = None
    BotoConfig = None


@dataclass
class PersistedMedia:
    original_path: str
    thumb_path: Optional[str]
    compressed_path: Optional[str]
    file_size: Optional[int]
    # 响应式变体：{ "320": {"webp": "variants/{id}_320.webp",
    #                      "jpeg": "variants/{id}_320.jpg",
    #                      "width": 320, "height": 213}, ... }
    variants: Dict[str, Dict[str, Any]] = field(default_factory=dict)


_MEDIA_TYPE_BY_SUFFIX = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".pdf": "application/pdf",
}


def _media_type_for(path: str) -> Optional[str]:
    """显式给 FileResponse 定 Content-Type。

    某些 Python 环境的 mimetypes 表里没有 webp（会回落 octet-stream），
    浏览器拿到 octet-stream 会下载而不是渲染，这里按扩展名显式兜底。
    """
    return _MEDIA_TYPE_BY_SUFFIX.get(Path(path).suffix.lower())

# 媒体对象在对象存储侧的长缓存语义（与本地 FileResponse 保持一致）。
# 预签名 URL 每次请求都会刷新，但对象本身内容按 uuid 不变，可 immutable。
_MEDIA_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _s3_extra_args(object_key: str) -> Dict[str, Any]:
    """S3 上传的元信息：Content-Type 与 Cache-Control。

    boto3 的 upload_file 不会根据扩展名猜 Content-Type，MinIO/R2 会把对象
    存成 application/octet-stream；经 307 预签名跳转后浏览器拿到 octet-stream
    会变成下载而不是渲染。这里显式带上类型，并把长缓存也写进对象元数据，
    这样对象存储直出时同样命中 CDN/浏览器缓存。
    """
    return {
        "ContentType": _media_type_for(object_key) or "application/octet-stream",
        "CacheControl": _MEDIA_CACHE_CONTROL,
    }


def generate_unique_filename(original_filename: str) -> tuple[str, str]:
    """Generate a stable UUID identifier and preserve extension."""
    file_extension = Path(original_filename).suffix.lower()
    uuid_str = str(uuid.uuid4())
    return uuid_str, file_extension


def ensure_upload_dirs() -> tuple[str, str]:
    """Compatibility helper for local-storage import flows."""
    upload_dir = Path(settings.UPLOAD_DIR)
    originals_dir = upload_dir / "originals"
    thumbnails_dir = upload_dir / "thumbnails"
    compressed_dir = upload_dir / "compressed"
    originals_dir.mkdir(parents=True, exist_ok=True)
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    compressed_dir.mkdir(parents=True, exist_ok=True)
    return str(originals_dir), str(thumbnails_dir)


async def save_upload_file(upload_file: UploadFile, destination: str) -> str:
    """Save uploaded file to a temporary or final destination."""
    try:
        with open(destination, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return destination
    finally:
        upload_file.file.close()


async def stage_photo_upload(upload_file: UploadFile) -> tuple[str, str, str, str]:
    """Persist an uploaded file to a temporary local path for processing."""
    photo_uuid, file_extension = generate_unique_filename(upload_file.filename)
    temp_dir = tempfile.mkdtemp(prefix="buct-media-upload-")
    original_filename = f"{photo_uuid}{file_extension}"
    staged_original_path = os.path.join(temp_dir, original_filename)
    await save_upload_file(upload_file, staged_original_path)
    return photo_uuid, staged_original_path, upload_file.filename, file_extension


class StorageBackend:
    """Base storage backend contract."""

    def persist_photo_files(
        self,
        photo_uuid: str,
        staged_original_path: str,
        staged_thumbnail_path: Optional[str],
        staged_compressed_path: Optional[str] = None,
        staged_variants: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> PersistedMedia:
        raise NotImplementedError

    def persist_redacted(
        self,
        photo_uuid: str,
        staged_redacted_path: Optional[str],
        staged_redacted_thumb_path: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """把脱敏图（强模糊，人像隐私）落盘/上传，返回 {redacted_path, redacted_thumb_path}。"""
        raise NotImplementedError

    def delete_file(self, file_path: Optional[str]) -> bool:
        raise NotImplementedError

    def delete_many(self, file_paths: Iterable[Optional[str]]) -> int:
        """批量删除文件，默认逐个调用 :meth:`delete_file`。

        S3 兼容后端覆盖为 ``DeleteObjects``（单次最多 1000 个 key），
        避免账号注销 / 批量清理时产生成百上千次网络往返。
        """
        return sum(1 for path in file_paths if path and self.delete_file(path))

    def presign_url(
        self,
        file_path: str,
        *,
        content_type: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> Optional[str]:
        """返回可直接给浏览器的绝对媒体 URL（对象存储预签名），本地后端返回 None。

        为什么需要它：前端 <picture>/srcset 里若是同源的 ``/api/.../image/...``，
        每张图都要先经过一次 API 请求（公网经 Cloudflare Tunnel 时单次往返
        可达 1–3 秒）拿到 307 才跳到对象存储。把预签名直链直接写进列表/详情
        响应，浏览器就能直连对象存储，少一次隧道往返（见第 43 轮性能优化）。
        """
        return None

    def build_media_response(
        self,
        file_path: str,
        download_name: Optional[str] = None,
    ) -> Response:
        raise NotImplementedError

    @contextmanager
    def local_copy(self, file_path: str) -> Iterator[str]:
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self) -> None:
        upload_dir = Path(settings.UPLOAD_DIR)
        self.originals_dir = upload_dir / "originals"
        self.thumbnails_dir = upload_dir / "thumbnails"
        self.compressed_dir = upload_dir / "compressed"
        self.variants_dir = upload_dir / "variants"
        self.redacted_dir = upload_dir / "redacted"
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.compressed_dir.mkdir(parents=True, exist_ok=True)
        self.variants_dir.mkdir(parents=True, exist_ok=True)
        self.redacted_dir.mkdir(parents=True, exist_ok=True)

    def _normalize(self, path: str) -> str:
        clean = path.replace("\\", "/")
        if os.path.isabs(clean):
            return clean
        # 兼容旧数据：如果路径已经以 upload_dir 名称开头（如 "uploads/thumbnails/..."），
        # 则不再拼接 UPLOAD_DIR，避免出现 "uploads/uploads/..." 双重前缀
        upload_dir_name = Path(settings.UPLOAD_DIR).name  # e.g. "uploads"
        if clean.startswith(upload_dir_name + "/"):
            # 路径已经包含 upload_dir 前缀，直接相对于 UPLOAD_DIR 的父目录解析
            return str((Path(settings.UPLOAD_DIR).parent / clean).resolve())
        return str((Path(settings.UPLOAD_DIR) / clean).resolve())

    def persist_photo_files(
        self,
        photo_uuid: str,
        staged_original_path: str,
        staged_thumbnail_path: Optional[str],
        staged_compressed_path: Optional[str] = None,
        staged_variants: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> PersistedMedia:
        extension = Path(staged_original_path).suffix.lower()
        original_relative = f"originals/{photo_uuid}{extension}"
        original_target = Path(settings.UPLOAD_DIR) / original_relative
        original_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(staged_original_path, original_target)

        thumb_relative = None
        if staged_thumbnail_path:
            thumb_relative = f"thumbnails/{photo_uuid}_thumb.jpg"
            thumb_target = Path(settings.UPLOAD_DIR) / thumb_relative
            thumb_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staged_thumbnail_path, thumb_target)

        compressed_relative = None
        if staged_compressed_path and os.path.exists(staged_compressed_path):
            compressed_relative = f"compressed/{photo_uuid}_compressed.jpg"
            compressed_target = Path(settings.UPLOAD_DIR) / compressed_relative
            compressed_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staged_compressed_path, compressed_target)

        variants: Dict[str, Dict[str, Any]] = {}
        if staged_variants:
            self.variants_dir.mkdir(parents=True, exist_ok=True)
            for size, info in sorted(staged_variants.items()):
                entry: Dict[str, Any] = {"width": info.get("width"), "height": info.get("height")}
                for fmt in ("webp", "jpeg"):
                    staged_path = info.get(fmt)
                    if not staged_path or not os.path.exists(staged_path):
                        continue
                    suffix = "webp" if fmt == "webp" else "jpg"
                    relative = f"variants/{photo_uuid}_{size}.{suffix}"
                    target = Path(settings.UPLOAD_DIR) / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(staged_path, target)
                    entry[fmt] = relative
                if entry.get("webp") or entry.get("jpeg"):
                    variants[str(size)] = entry

        return PersistedMedia(
            original_path=original_relative,
            thumb_path=thumb_relative,
            compressed_path=compressed_relative,
            file_size=original_target.stat().st_size if original_target.exists() else None,
            variants=variants,
        )

    def persist_redacted(
        self,
        photo_uuid: str,
        staged_redacted_path: Optional[str],
        staged_redacted_thumb_path: Optional[str],
    ) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {"redacted_path": None, "redacted_thumb_path": None}
        for name, staged in (("redacted_path", staged_redacted_path), ("redacted_thumb_path", staged_redacted_thumb_path)):
            if not staged or not os.path.exists(staged):
                continue
            suffix = "_redacted_thumb.jpg" if name.endswith("thumb_path") else "_redacted.jpg"
            relative = f"redacted/{photo_uuid}{suffix}"
            target = Path(settings.UPLOAD_DIR) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staged, target)
            result[name] = relative
        return result

    def delete_file(self, file_path: Optional[str]) -> bool:
        if not file_path:
            return False
        try:
            target = self._normalize(file_path)
            if os.path.exists(target):
                os.remove(target)
                return True
            return False
        except Exception:
            return False

    def build_media_response(
        self,
        file_path: str,
        download_name: Optional[str] = None,
    ) -> Response:
        target = self._normalize(file_path)
        if not os.path.exists(target):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Media file not found: {file_path}")
        media_type = _media_type_for(target)
        if download_name:
            # 下载语义：必须带 Content-Disposition，且别让中间层缓存成在线预览。
            return FileResponse(
                target,
                filename=download_name,
                media_type=media_type,
                headers={"Cache-Control": "private, max-age=0, must-revalidate"},
            )
        # 在线预览（缩略图/压缩图/原图）：图片 URL 与 photo id + 变体档位绑定，
        # 文件名内容不可变，可以放心长缓存——2c4g 小机器最重要的带宽优化之一。
        # Starlette FileResponse 自带 ETag / Last-Modified，nginx 也能直接 304。
        return FileResponse(
            target,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @contextmanager
    def local_copy(self, file_path: str) -> Iterator[str]:
        yield self._normalize(file_path)


class S3StorageBackend(StorageBackend):
    """S3-compatible object storage backend.

    Uses boto3 for read operations (list, get, head) which work through VPN.
    Uses SSH + mc pipe for write operations (put, delete) which are blocked
    by the firewall when accessing MinIO from outside.
    """

    # 本地开发绕过防火墙的可选兜底；凭据不写入仓库，未配置则不可用。
    # 生产应直连 S3，此兜底计划移除（见 docs/ROADMAP.md M0）。
    _ssh_host = os.environ.get("S3_SSH_FALLBACK_HOST", "")
    _ssh_user = os.environ.get("S3_SSH_FALLBACK_USER", "")

    def _require_ssh_fallback(self) -> None:
        if not (self._ssh_host and self._ssh_user):
            raise RuntimeError(
                "S3 写入的 SSH 兜底未配置。请直连 S3，或设置 "
                "S3_SSH_FALLBACK_HOST / S3_SSH_FALLBACK_USER 环境变量。"
            )

    def __init__(self) -> None:
        if boto3 is None or BotoConfig is None:
            raise RuntimeError("boto3 is required for the S3 storage backend.")
        if not all([settings.S3_ENDPOINT, settings.S3_BUCKET, settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY]):
            raise RuntimeError("S3 storage backend requires endpoint, bucket, access key, and secret key.")

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": settings.S3_ADDRESSING_STYLE or "auto"},
            ),
        )

    # ── SSH helpers for write operations ──

    def _mc_pipe(self, local_path: str, key: str) -> None:
        """Upload a local file to MinIO via SSH + mc pipe."""
        self._require_ssh_fallback()
        import subprocess
        cmd = f"mc pipe local/{self.bucket}/{key}"
        with open(local_path, "rb") as fh:
            proc = subprocess.run(
                ["ssh", f"{self._ssh_user}@{self._ssh_host}", cmd],
                stdin=fh,
                capture_output=True,
                timeout=120,
            )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"mc pipe failed for {key}: {stderr}")

    def _mc_rm(self, key: str) -> bool:
        """Delete an object from MinIO via SSH + mc rm."""
        self._require_ssh_fallback()
        import subprocess
        cmd = f"mc rm local/{self.bucket}/{key}"
        proc = subprocess.run(
            ["ssh", f"{self._ssh_user}@{self._ssh_host}", cmd],
            capture_output=True,
            timeout=30,
        )
        return proc.returncode == 0

    # ── StorageBackend interface ──

    def persist_photo_files(
        self,
        photo_uuid: str,
        staged_original_path: str,
        staged_thumbnail_path: Optional[str],
        staged_compressed_path: Optional[str] = None,
        staged_variants: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> PersistedMedia:
        extension = Path(staged_original_path).suffix.lower()
        original_key = f"originals/{photo_uuid}{extension}"

        # Try direct upload first (works when running on the server),
        # fall back to SSH + mc pipe (works through VPN)
        try:
            self.client.upload_file(
                staged_original_path, self.bucket, original_key,
                ExtraArgs=_s3_extra_args(original_key),
            )
        except Exception:
            self._mc_pipe(staged_original_path, original_key)

        thumb_key = None
        if staged_thumbnail_path and os.path.exists(staged_thumbnail_path):
            thumb_key = f"thumbnails/{photo_uuid}_thumb.jpg"
            try:
                self.client.upload_file(
                    staged_thumbnail_path, self.bucket, thumb_key,
                    ExtraArgs=_s3_extra_args(thumb_key),
                )
            except Exception:
                self._mc_pipe(staged_thumbnail_path, thumb_key)

        compressed_key = None
        if staged_compressed_path and os.path.exists(staged_compressed_path):
            compressed_key = f"compressed/{photo_uuid}_compressed.jpg"
            try:
                self.client.upload_file(
                    staged_compressed_path, self.bucket, compressed_key,
                    ExtraArgs=_s3_extra_args(compressed_key),
                )
            except Exception:
                self._mc_pipe(staged_compressed_path, compressed_key)

        variants: Dict[str, Dict[str, Any]] = {}
        if staged_variants:
            for variant_size, info in sorted(staged_variants.items()):
                entry: Dict[str, Any] = {"width": info.get("width"), "height": info.get("height")}
                for fmt in ("webp", "jpeg"):
                    staged_path = info.get(fmt)
                    if not staged_path or not os.path.exists(staged_path):
                        continue
                    suffix = "webp" if fmt == "webp" else "jpg"
                    variant_key = f"variants/{photo_uuid}_{variant_size}.{suffix}"
                    try:
                        self.client.upload_file(
                            staged_path, self.bucket, variant_key,
                            ExtraArgs=_s3_extra_args(variant_key),
                        )
                    except Exception:
                        self._mc_pipe(staged_path, variant_key)
                    entry[fmt] = variant_key
                if entry.get("webp") or entry.get("jpeg"):
                    variants[str(variant_size)] = entry

        size = os.path.getsize(staged_original_path) if os.path.exists(staged_original_path) else None
        return PersistedMedia(
            original_path=original_key,
            thumb_path=thumb_key,
            compressed_path=compressed_key,
            file_size=size,
            variants=variants,
        )

    def persist_redacted(
        self,
        photo_uuid: str,
        staged_redacted_path: Optional[str],
        staged_redacted_thumb_path: Optional[str],
    ) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {"redacted_path": None, "redacted_thumb_path": None}
        for name, staged in (("redacted_path", staged_redacted_path), ("redacted_thumb_path", staged_redacted_thumb_path)):
            if not staged or not os.path.exists(staged):
                continue
            suffix = "_redacted_thumb.jpg" if name.endswith("thumb_path") else "_redacted.jpg"
            key = f"redacted/{photo_uuid}{suffix}"
            try:
                self.client.upload_file(staged, self.bucket, key, ExtraArgs=_s3_extra_args(key))
            except Exception:
                self._mc_pipe(staged, key)
            result[name] = key
        return result

    def delete_file(self, file_path: Optional[str]) -> bool:
        if not file_path:
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=file_path)
            return True
        except Exception:
            return self._mc_rm(file_path)

    def delete_many(self, file_paths: Iterable[Optional[str]]) -> int:
        """用 ``DeleteObjects`` 批量删除（COS / R2 均支持，单批最多 1000）。"""
        paths = [path for path in file_paths if path]
        if not paths:
            return 0
        removed = 0
        for start in range(0, len(paths), 1000):
            batch = paths[start : start + 1000]
            try:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": path} for path in batch], "Quiet": True},
                )
                removed += len(batch)
            except Exception:  # noqa: BLE001 - 批量失败时逐个兜底
                removed += sum(1 for path in batch if self.delete_file(path))
        return removed

    def presign_url(
        self,
        file_path: str,
        *,
        content_type: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> Optional[str]:
        """生成对象存储直链（预签名 GET），留给公开响应内联使用。"""
        if not file_path:
            return None
        params: Dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": file_path.lstrip("/"),
        }
        if content_type:
            params["ResponseContentType"] = content_type
        ttl = int(expires_in if expires_in is not None else settings.S3_PRESIGN_EXPIRE_SECONDS)
        try:
            return self.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=ttl
            )
        except Exception as exc:  # noqa: BLE001 - 预签名失败要能优雅退回 API 路径
            logging.getLogger(__name__).warning(
                "Presign inline failed for key=%s bucket=%s: %s", file_path, self.bucket, exc
            )
            return None

    def build_media_response(
        self,
        file_path: str,
        download_name: Optional[str] = None,
    ) -> Response:
        """返回 307 跳到对象存储的预签名 URL，而不是经 Python 转发字节流。

        2c4g 机器上「Python 边读 S3 边吐给用户」会同时占住一个 uvicorn worker
        和一份内存缓冲；预签名跳转把带宽与并发直接交给对象存储（R2/OSS），
        应用只需要一次不耗内存的重定向。
        """
        from urllib.parse import quote

        params = {"Bucket": self.bucket, "Key": file_path}
        if download_name:
            # RFC 5987: 让浏览器把对象存成可读的中文文件名。
            encoded_name = quote(download_name)
            params["ResponseContentDisposition"] = (
                f"attachment; filename*=UTF-8''{encoded_name}"
            )
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=settings.S3_PRESIGN_EXPIRE_SECONDS,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Presign failed for key=%s bucket=%s: %s", file_path, self.bucket, exc
            )
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Media file not found")

        headers = {
            # 预签名 URL 有 TTL；重定向本身只缓存 5 分钟（< TTL 10 分钟），
            # 既避免每张图都回源，也不会缓存出一个已过期的地址。
            "Cache-Control": "private, max-age=300",
        }
        if download_name:
            headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        return RedirectResponse(url=url, status_code=307, headers=headers)

    @contextmanager
    def local_copy(self, file_path: str) -> Iterator[str]:
        suffix = Path(file_path).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
        self.client.download_file(self.bucket, file_path, temp_path)
        try:
            yield temp_path
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


def cleanup_staged_files(*paths: Optional[str]) -> None:
    """Remove temporary staged files and their temp directories."""
    for path in paths:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        parent = Path(path).parent
        try:
            if parent.name.startswith("buct-media-upload-") and parent.exists():
                shutil.rmtree(parent, ignore_errors=True)
        except OSError:
            pass


def get_storage_backend() -> StorageBackend:
    """Return the configured storage backend."""
    if settings.STORAGE_BACKEND == "s3":
        return S3StorageBackend()
    return LocalStorageBackend()


def get_storage() -> StorageBackend:
    """Convenience accessor for callers that do not need DI."""
    return get_storage_backend()


def delete_file(file_path: Optional[str]) -> bool:
    """Backward-compatible delete helper."""
    return get_storage().delete_file(file_path)


@lru_cache(maxsize=1)
def _direct_media_backend() -> StorageBackend:
    """进程内缓存的存储后端，专供「公开响应内联预签名直链」使用。

    每个请求都 new 一个 boto3 client 代价很高（解析配置、构造签名器），
    而预签名只是本地 HMAC 计算，复用单例即可；线程安全（boto3 client
    的 generate_presigned_url 无网络 IO）。
    """
    return get_storage_backend()


def direct_media_url(
    file_path: Optional[str],
    *,
    content_type: Optional[str] = None,
    expires_in: Optional[int] = None,
) -> Optional[str]:
    """对象存储模式返回绝对预签名直链；本地模式返回 None（调用方回退 API 路径）。"""
    if not file_path or settings.STORAGE_BACKEND != "s3":
        return None
    try:
        backend = _direct_media_backend()
        return backend.presign_url(file_path, content_type=content_type, expires_in=expires_in)
    except Exception as exc:  # noqa: BLE001 - 直链失败不能影响主流程
        logging.getLogger(__name__).warning(
            "direct_media_url failed for key=%s: %s", file_path, exc
        )
        return None
