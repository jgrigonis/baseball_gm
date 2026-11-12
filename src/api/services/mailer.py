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

# What to do about a certificate error. python.org's macOS Python ships
# without root certificates until "Install Certificates.command" is run, so
# STARTTLS fails to verify any mail server. We use certifi's bundle when it's
# there, which covers that case, but say how to fix it if it still happens.
_CERT_HINT = (
    "Python couldn't check the mail server's certificate. On macOS with "
    'python.org\'s Python, run "Install Certificates.command" in '
    "/Applications/Python 3.x, or check SMTP_HOST is the server's real name."
)


def _ssl_context() -> ssl.SSLContext:
    """A verifying context, using certifi's root certificates when it's
    installed (they don't depend on the system's), the system's otherwise."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


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

    try:
        context = _ssl_context()
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
    except ssl.SSLCertVerificationError as e:
        # One line, not a traceback: the fix is on the machine, not here.
        log.warning(
            "Couldn't send email to %s: %s. %s", to, e.verify_message, _CERT_HINT
        )
    except Exception:
        # Never let an email take down what sent it (a background task or the
        # turn-email thread).
        log.exception("Couldn't send email to %s", to)
