"""Send an EPUB file to a Kindle email address via SMTP."""

from __future__ import annotations

import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def send_to_kindle(
    epub_path: str | Path,
    *,
    kindle_email: str,
    sender_email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
) -> None:
    """Send *epub_path* as an email attachment to the Kindle email address.

    Amazon's Send-to-Kindle service accepts .epub files directly.
    Make sure the sender address is in your Kindle's Approved Personal
    Document E-mail List (Amazon account > Devices > Preferences).
    """
    epub_path = Path(epub_path)
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = kindle_email
    msg["Subject"] = f"convert"  # 'convert' tells Amazon to convert if needed

    msg.attach(MIMEText("Sent by webnovel-to-kindle.", "plain", "utf-8"))

    with open(epub_path, "rb") as f:
        part = MIMEBase("application", "epub+zip")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f'attachment; filename="{epub_path.name}"',
    )
    msg.attach(part)

    print(f"Connecting to {smtp_host}:{smtp_port} …")
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(sender_email, kindle_email, msg.as_string())

    print(f"Sent {epub_path.name} → {kindle_email}")
