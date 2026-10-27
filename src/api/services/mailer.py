# src/api/services/mailer.py
#
# Sends plain-text email over SMTP, using the SMTP_* settings in config.py.
# Any provider that speaks SMTP works. With no SMTP_HOST (dev and tests),
# messages are written to the server log instead, so the flows that send
# email can be tried without a mail account.

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from src.config import settings

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.smtp_host)


def send(to: str, subject: str, text: str) -> None:
    """Send one email. Errors are logged, not raised: this runs after the
    response has gone out, so there is no one to show them to."""
    if not is_configured():
        log.warning(
            "SMTP_HOST is not set; not sending this email:\nTo: %s\nSubject: %s\n\n%s",
            to,
            subject,
            text,
        )
        return

    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)

    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, context=context, timeout=30
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        with server:
            if settings.smtp_port != 465 and settings.smtp_starttls:
                server.starttls(context=context)
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
    except OSError, smtplib.SMTPException:
        log.exception("Couldn't send email to %s", to)
