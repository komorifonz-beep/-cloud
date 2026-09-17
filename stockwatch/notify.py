"""再入荷メールの作成と送信。"""

from __future__ import annotations

import html
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def build_message(email_cfg, product, detection, *, cart_note: str = "",
                  screenshot: str | None = None) -> EmailMessage:
    when = _now_jst()
    price = detection.price or "不明"

    message = EmailMessage()
    message["Subject"] = f"【再入荷】{product.name}"
    message["From"] = email_cfg.sender
    message["To"] = ", ".join(email_cfg.to)

    plain = [
        f"{product.name} が購入できる状態になりました。",
        "",
        f"価格　: {price}",
        f"確認　: {when} (JST)",
        f"判定　: {detection.reason}",
        "",
        f"商品ページ: {product.url}",
    ]
    if cart_note:
        plain += ["", f"カート: {cart_note}"]
    plain += ["", "-- stockwatch"]
    message.set_content("\n".join(plain))

    safe_name = html.escape(product.name)
    safe_url = html.escape(product.url, quote=True)
    cart_block = (
        f'<p style="margin:16px 0 0;color:#444;">カート: {html.escape(cart_note)}</p>'
        if cart_note else ""
    )
    message.add_alternative(
        f"""<html><body style="font-family:-apple-system,'Hiragino Sans',sans-serif;
 background:#f5f5f7;margin:0;padding:24px;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;">
    <p style="margin:0 0 8px;color:#c0392b;font-weight:700;letter-spacing:.04em;">再入荷</p>
    <h1 style="margin:0 0 20px;font-size:20px;line-height:1.4;">{safe_name}</h1>
    <table style="width:100%;border-collapse:collapse;font-size:14px;color:#333;">
      <tr><td style="padding:6px 0;color:#888;width:5em;">価格</td>
          <td style="padding:6px 0;font-weight:600;">{html.escape(price)}</td></tr>
      <tr><td style="padding:6px 0;color:#888;">確認時刻</td>
          <td style="padding:6px 0;">{when} JST</td></tr>
      <tr><td style="padding:6px 0;color:#888;">判定</td>
          <td style="padding:6px 0;color:#666;">{html.escape(detection.reason)}</td></tr>
    </table>
    <p style="margin:24px 0 0;">
      <a href="{safe_url}" style="display:inline-block;background:#111;color:#fff;
         text-decoration:none;padding:13px 28px;border-radius:8px;font-weight:600;">
        商品ページを開く</a>
    </p>
    {cart_block}
    <p style="margin:24px 0 0;font-size:12px;color:#999;">stockwatch</p>
  </div>
</body></html>""",
        subtype="html",
    )

    if screenshot and Path(screenshot).exists():
        data = Path(screenshot).read_bytes()
        message.get_payload()[-1].add_related(
            data, maintype="image", subtype="png", filename="cart.png"
        )
    return message


def send(email_cfg, message: EmailMessage) -> None:
    if not email_cfg.is_configured:
        raise RuntimeError(
            "メール設定が未完了です。config.yml の email.user / email.password / email.to "
            "(または対応する環境変数) を設定してください。"
        )
    if email_cfg.use_tls:
        with smtplib.SMTP(email_cfg.smtp_host, email_cfg.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(email_cfg.user, email_cfg.password)
            server.send_message(message)
    else:
        with smtplib.SMTP_SSL(email_cfg.smtp_host, email_cfg.smtp_port, timeout=30) as server:
            server.login(email_cfg.user, email_cfg.password)
            server.send_message(message)


def send_test(email_cfg) -> None:
    message = EmailMessage()
    message["Subject"] = "【stockwatch】テストメール"
    message["From"] = email_cfg.sender
    message["To"] = ", ".join(email_cfg.to)
    message.set_content(
        f"stockwatch のメール設定は正常です。\n送信時刻: {_now_jst()} (JST)\n"
    )
    send(email_cfg, message)
