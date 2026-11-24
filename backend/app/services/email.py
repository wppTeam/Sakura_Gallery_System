"""邮件发送服务

支持三种发送方式（`EMAIL_PROVIDER`）：
- console：不真实发送，只把内容写日志（本地开发默认；同时接口在 DEBUG 下返回 dev_code）
- smtp：标准 SMTP（QQ 邮箱 / 163 / 企业邮箱 / 自建邮件服务器）
- resend：Resend HTTP API（需要 RESEND_API_KEY，免 SMTP 端口限制）

发送失败抛 EmailDeliveryError，由调用方转成明确的 503 提示，避免静默丢码。
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Optional

import httpx
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

PURPOSE_LABELS = {
    "register": "注册账号",
    "login": "邮箱验证码登录",
    "reset_password": "重置密码",
    "verify_email": "验证邮箱",
}


class EmailDeliveryError(RuntimeError):
    """邮件发送失败（配置缺失 / 网络错误 / 服务端拒收）"""


def _label(purpose: str) -> str:
    return PURPOSE_LABELS.get(purpose, "身份验证")


def _build_message(to: str, subject: str, text: str, html: Optional[str] = None) -> EmailMessage:
    settings = get_settings()
    from_header = settings.SMTP_FROM if settings.EMAIL_PROVIDER != "resend" else settings.RESEND_FROM
    display_name, addr = parseaddr(from_header or "")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((display_name or "视觉百花", addr or "noreply@buct-sakura.cn"))
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _send_smtp_sync(msg: EmailMessage, to: str) -> None:
    settings = get_settings()
    host = settings.SMTP_HOST.strip()
    if not host:
        raise EmailDeliveryError("未配置 SMTP_HOST")
    port = int(settings.SMTP_PORT or 465)
    timeout = 20
    try:
        if settings.SMTP_USE_SSL:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        with server:
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                server.starttls(context=ssl.create_default_context())
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:  # 网络/认证/拒收
        raise EmailDeliveryError(f"SMTP 发送失败：{exc}") from exc


async def _send_resend(to: str, subject: str, text: str, html: Optional[str]) -> None:
    settings = get_settings()
    if not settings.RESEND_API_KEY.strip():
        raise EmailDeliveryError("未配置 RESEND_API_KEY")
    payload = {
        "from": settings.RESEND_FROM,
        "to": [to],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise EmailDeliveryError(f"Resend 请求失败：{exc}") from exc
    if resp.status_code >= 400:
        raise EmailDeliveryError(f"Resend 返回 {resp.status_code}：{resp.text[:200]}")


def is_email_configured() -> bool:
    """是否具备真实发信能力"""
    settings = get_settings()
    if not settings.EMAIL_ENABLED:
        return False
    provider = (settings.EMAIL_PROVIDER or "console").lower()
    if provider == "smtp":
        return bool(settings.SMTP_HOST.strip())
    if provider == "resend":
        return bool(settings.RESEND_API_KEY.strip())
    return False


def console_mode() -> bool:
    settings = get_settings()
    return (not settings.EMAIL_ENABLED) or (settings.EMAIL_PROVIDER or "console").lower() == "console"


def _render_html(code: str, purpose: str, expires_in: int) -> str:
    label = _label(purpose)
    minutes = max(1, expires_in // 60)
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN"><body style="margin:0;padding:24px;background:#fff6f9;font-family:-apple-system,'Noto Sans SC',sans-serif;color:#4a2b35">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:20px;padding:32px;box-shadow:0 6px 24px rgba(201,58,99,.10)">
    <p style="margin:0 0 8px;font-size:13px;letter-spacing:.12em;color:#c93a63">视觉百花 · SAKURA GALLERY</p>
    <h1 style="margin:0 0 16px;font-size:22px;font-weight:600">你的{label}验证码</h1>
    <p style="margin:0 0 20px;font-size:15px;line-height:1.7;color:#63474f">
      请在页面中输入下面的验证码完成{label}。验证码 {minutes} 分钟内有效，仅可使用一次。
    </p>
    <div style="margin:0 0 20px;padding:18px 0;text-align:center;background:#fff6f9;border-radius:16px;letter-spacing:.32em;font-size:32px;font-weight:700;color:#c93a63">{code}</div>
    <p style="margin:0;font-size:13px;line-height:1.7;color:#8a6b74">
      如果这不是你本人的操作，请忽略本邮件；你的账号不会受到影响。<br/>
      请勿把验证码转发给任何人，本站工作人员不会向你索要验证码。
    </p>
  </div>
</body></html>"""


async def send_email(to: str, subject: str, text: str, html: Optional[str] = None) -> bool:
    """发送邮件，返回是否真实投递（console 模式返回 False）。"""
    settings = get_settings()
    provider = (settings.EMAIL_PROVIDER or "console").lower()

    if console_mode():
        logger.info("[EMAIL:console] to=%s subject=%s\n%s", to, subject, text)
        return False

    if provider == "smtp":
        msg = _build_message(to, subject, text, html)
        await run_in_threadpool(_send_smtp_sync, msg, to)
        return True

    if provider == "resend":
        await _send_resend(to, subject, text, html)
        return True

    raise EmailDeliveryError(f"未知 EMAIL_PROVIDER：{settings.EMAIL_PROVIDER}")


async def send_verification_code_email(to: str, code: str, purpose: str, expires_in: int) -> bool:
    """发送验证码邮件，返回是否真实投递。"""
    label = _label(purpose)
    minutes = max(1, expires_in // 60)
    subject = f"【视觉百花】{label}验证码：{code}（{minutes} 分钟内有效）"
    text = (
        f"你好，\n\n"
        f"你正在进行「{label}」操作，验证码是：{code}\n"
        f"验证码 {minutes} 分钟内有效，仅可使用一次。\n\n"
        f"如果这不是你本人的操作，请忽略本邮件。\n"
        f"请勿把验证码转发给任何人，本站工作人员不会向你索要验证码。\n\n"
        f"—— 视觉百花 Sakura Gallery"
    )
    html = _render_html(code, purpose, expires_in)
    return await send_email(to, subject, text, html)
