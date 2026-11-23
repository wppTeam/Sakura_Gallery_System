"""AIGC 隐式标识写入（《人工智能生成合成内容标识办法》2025-09-01 施行）。

法定义务四件套中的第 ③ 件：**下载/分发文件必须携带隐式标识**。
本模块在下载时按需把 XMP packet 写进文件字节流，不改动库内原图
（原图只读、保留原始构图），保证「下载到的每个副本都带标识」。

标识内容（XMP，UTF-8）：
- ``xmp:Label`` / ``xmp:CreatorTool``：显式文案「AI 生成」
- ``xmpMM:DocumentID``：作品 id（内容编号）
- ``dc:creator``：上传者公开身份（username / display_name，不含学号）
- 自定义命名空间 ``sakura``：IsAIGC / Model / Provider / Prompt（可选）/ LabeledAt / WorkID

格式支持：JPEG（APP1 XMP 段）、PNG（iTXt ``XML:com.adobe.xmp``）。
WebP/GIF 暂未实现（会返回 None，调用方降级为「原样返回 + 响应头加
``X-AIGC-Label``」并在日志里记一条，见 docs/AI_PLATFORM.md 已知限制）。
"""
from __future__ import annotations

import logging
import struct
import zlib
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.photo import Photo

logger = logging.getLogger(__name__)

XMP_NAMESPACE = "http://ns.adobe.com/xap/1.0/"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XMPMM_NAMESPACE = "http://ns.adobe.com/xap/1.0/mm/"
SAKURA_NAMESPACE = "https://sakura.buct.edu.cn/ns/aigc/1.0/"

PUBLIC_LABEL = "AI 生成"

SUPPORTED_MIME_TYPES = frozenset({"image/jpeg", "image/png"})


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _loaded_uploader(photo: Photo):
    """只在 uploader 已加载时读取，避免 async session 下触发 lazy load（MissingGreenlet）。"""
    try:
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(photo)
        if "uploader" in state.unloaded:
            return None
    except Exception:  # 非 ORM 对象（测试里的简单样例）
        pass
    return getattr(photo, "uploader", None)


def _public_creator(photo: Photo, creator: Optional[str] = None) -> str:
    if creator:
        return creator
    uploader = _loaded_uploader(photo)
    username = getattr(uploader, "username", None) if uploader is not None else None
    display_name = getattr(uploader, "display_name", None) if uploader is not None else None
    return display_name or username or photo.author or "Sakura Gallery"


def build_xmp_packet(
    photo: Photo,
    *,
    labeled_at: Optional[datetime] = None,
    creator: Optional[str] = None,
) -> str:
    """构造 XMP packet（字符串，未做 XML 包装之外的转义）。

    ``creator`` 由调用方显式传入公开身份（download 端点会先查一次 uploader），
    避免在 async 上下文里访问 lazy relationship。
    """
    meta: dict[str, Any] = photo.aigc_meta if isinstance(photo.aigc_meta, dict) else {}
    labeled_at = labeled_at or datetime.now(timezone.utc)
    label_text = photo.aigc_label or PUBLIC_LABEL

    fields = [
        f'<rdf:Description rdf:about=""',
        f'  xmlns:xmp="{XMP_NAMESPACE}"',
        f'  xmlns:dc="{DC_NAMESPACE}"',
        f'  xmlns:xmpMM="{XMPMM_NAMESPACE}"',
        f'  xmlns:sakura="{SAKURA_NAMESPACE}">',
        f"  <xmp:Label>{_xml_escape(label_text)}</xmp:Label>",
        f"  <xmp:CreatorTool>Sakura Gallery / AIGC</xmp:CreatorTool>",
        f"  <xmpMM:DocumentID>sakura:work:{_xml_escape(str(photo.id))}</xmpMM:DocumentID>",
        f"  <dc:creator><rdf:Seq><rdf:li>{_xml_escape(_public_creator(photo, creator))}</rdf:li></rdf:Seq></dc:creator>",
        f"  <sakura:IsAIGC>true</sakura:IsAIGC>",
        f"  <sakura:WorkID>{_xml_escape(str(photo.id))}</sakura:WorkID>",
        f"  <sakura:LabeledAt>{labeled_at.isoformat(timespec='seconds')}</sakura:LabeledAt>",
    ]
    model = meta.get("model")
    provider = meta.get("provider")
    prompt = meta.get("prompt") if meta.get("prompt_public") else None
    if model:
        fields.append(f"  <sakura:Model>{_xml_escape(str(model)[:120])}</sakura:Model>")
    if provider:
        fields.append(f"  <sakura:Provider>{_xml_escape(str(provider)[:120])}</sakura:Provider>")
    if prompt:
        fields.append(f"  <sakura:Prompt>{_xml_escape(str(prompt)[:1500])}</sakura:Prompt>")
    if meta.get("source_work_id"):
        fields.append(
            f"  <sakura:SourceWorkID>{_xml_escape(str(meta['source_work_id'])[:120])}</sakura:SourceWorkID>"
        )
    if meta.get("face_swap"):
        fields.append("  <sakura:FaceSwap>true</sakura:FaceSwap>")
    fields.append("</rdf:Description>")

    body = "\n".join(fields)
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        f"{body}\n"
        "</rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>'
    )


# ---------------------------------------------------------------------------
# 格式写入
# ---------------------------------------------------------------------------

_XMP_APP1_PREFIX = b"http://ns.adobe.com/xap/1.0/\x00"


def _embed_jpeg(data: bytes, packet: bytes) -> Optional[bytes]:
    """把 XMP 作为 APP1 段插到 SOI 之后；已有 XMP APP1 则替换。"""
    if not data.startswith(b"\xff\xd8"):
        return None
    payload = _XMP_APP1_PREFIX + packet
    if len(payload) + 2 > 0xFFFF:
        logger.warning("AIGC XMP too large for JPEG APP1 (%s bytes)", len(payload))
        return None
    app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload

    body = data[2:]
    # 跳过已有 XMP APP1（标准位置在 EXIF 之后，但容忍任意位置）
    out = bytearray(b"\xff\xd8") + app1
    index = 0
    while index < len(body):
        if body[index] != 0xFF or index + 1 >= len(body):
            break
        marker = body[index + 1]
        if marker in (0xE1,) and body.startswith(_XMP_APP1_PREFIX, index + 4):
            chunk_len = struct.unpack(">H", body[index + 2:index + 4])[0]
            index += 2 + chunk_len
            continue
        break
    out.extend(body[index:])
    return bytes(out)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _embed_png(data: bytes, packet: bytes) -> Optional[bytes]:
    """在 PNG 的 IDAT 之前插入 XMP iTXt chunk。"""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    insert_at: Optional[int] = None
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        if chunk_type == b"iTXt":
            keyword = data[pos + 8:pos + 8 + 22]
            if keyword.startswith(b"XML:com.adobe.xmp"):
                # 已有 XMP：整段替换
                end = pos + 12 + length
                chunk = _png_chunk(
                    b"iTXt",
                    b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + packet,
                )
                return data[:pos] + chunk + data[end:]
        if chunk_type in (b"IDAT", b"IEND"):
            insert_at = pos
            break
        pos += 12 + length
    if insert_at is None:
        return None
    chunk = _png_chunk(
        b"iTXt",
        b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + packet,
    )
    return data[:insert_at] + chunk + data[insert_at:]


def detect_image_mime(data: bytes) -> Optional[str]:
    """按文件头嗅探真实格式（客户端声明的 MIME 可能不准，如 .jpg 实际是 PNG）。"""
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"GIF8"):
        return "image/gif"
    return None


def embed_aigc_label(data: bytes, mime_type: Optional[str], packet: bytes) -> Optional[bytes]:
    """写入隐式标识；不支持的格式返回 None（调用方降级）。

    以文件头嗅探为准（``mime_type`` 仅作兜底），避免上传时声明的 MIME
    与真实字节不一致导致「本可写却没写」。
    """
    actual = detect_image_mime(data) or (mime_type or "").lower()
    if actual == "image/jpeg":
        return _embed_jpeg(data, packet)
    if actual == "image/png":
        return _embed_png(data, packet)
    return None


def has_aigc_xmp(data: bytes) -> bool:
    """测试/校验用：文件字节里是否已含本系统写入的 XMP 标识。"""
    return b"sakura:IsAIGC" in data or _XMP_APP1_PREFIX in data
