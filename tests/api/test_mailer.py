# tests/api/test_mailer.py
"""The SMTP mailer: logs instead of sending with no SMTP_HOST, and talks to
the configured server otherwise."""

import logging
import smtplib

from src.api.services import mailer
from src.config import settings


class FakeSMTP:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["To"], msg["Subject"], msg.get_content()))


def test_logs_without_smtp_host(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(smtplib, "SMTP", None)
    with caplog.at_level(logging.WARNING):
        mailer.send("a@example.com", "Hi", "the body")
    assert "the body" in caplog.text


def test_sends_with_starttls_and_login(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "user")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    mailer.send("a@example.com", "Hi", "the body")

    (server,) = FakeSMTP.instances
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.calls[0] == "starttls"
    assert server.calls[1] == ("login", "user", "secret")
    assert server.calls[2] == ("send", "a@example.com", "Hi", "the body\n")


def test_send_errors_are_logged_not_raised(monkeypatch, caplog):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    with caplog.at_level(logging.ERROR):
        mailer.send("a@example.com", "Hi", "the body")
    assert "Couldn't send email" in caplog.text
