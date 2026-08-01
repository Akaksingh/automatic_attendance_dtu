"""Development SMTP and production AWS SES email delivery."""
from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

from .config import settings


def welcome_html(full_name: str, email: str, password: str) -> str:
    return f"""<!doctype html><html><body style='margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#172033'>
    <div style='max-width:600px;margin:32px auto;background:#fff;border-radius:16px;padding:36px;box-shadow:0 8px 30px #17203318'>
      <div style='color:#315efb;font-size:13px;font-weight:bold;letter-spacing:2px'>CLASSLENS</div>
      <h1 style='margin:18px 0 8px'>Welcome, {html.escape(full_name)}</h1>
      <p>Your student account is ready. Use the credentials below to sign in.</p>
      <div style='background:#eef3ff;border-radius:12px;padding:18px;margin:24px 0'>
        <p style='margin:4px 0'><b>Login ID:</b> {html.escape(email)}</p>
        <p style='margin:4px 0'><b>Temporary password:</b> <code>{html.escape(password)}</code></p>
      </div>
      <p>Please change this password after your first login. If you did not expect this account, contact your administrator.</p>
    </div></body></html>"""


def send_welcome_email(*, email: str, full_name: str, password: str) -> None:
    if not settings.email_enabled:
        return
    message = EmailMessage()
    message["Subject"] = "Your ClassLens student account"
    message["From"] = settings.email_from
    message["To"] = email
    message.set_content(f"Your ClassLens login is {email}. Temporary password: {password}")
    message.add_alternative(welcome_html(full_name, email, password), subtype="html")

    if settings.email_backend.lower() == "ses":
        import boto3
        client = boto3.client("ses", region_name=settings.ses_region or settings.storage_region)
        kwargs = {"Source": settings.email_from, "Destination": {"ToAddresses": [email]}, "Message": {"Subject": {"Data": message["Subject"]}, "Body": {"Text": {"Data": f"Your ClassLens login is {email}. Temporary password: {password}"}, "Html": {"Data": welcome_html(full_name, email, password)}}}}
        if settings.ses_configuration_set:
            kwargs["ConfigurationSetName"] = settings.ses_configuration_set
        client.send_email(**kwargs)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)
