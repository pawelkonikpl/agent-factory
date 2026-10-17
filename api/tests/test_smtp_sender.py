import asyncio
import email
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import Message
from typing import Any

import aiosmtplib
import pytest

from app.services import smtp_sender
from app.services.smtp_config_service import SmtpConfig
from app.services.smtp_sender import (
    LOGIN_WITHOUT_TLS_ERROR,
    EmailItem,
    SendResult,
    SmtpEmailSender,
    send_many,
)

RECIPIENT = "jan@example.com"


def make_config(**overrides: Any) -> SmtpConfig:
    values: dict[str, Any] = {
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "noreply@example.com",
        "smtp_password": "secret-password",
        "smtp_use_tls": True,
    } | overrides
    return SmtpConfig(**values)


@dataclass
class FakeSmtp:
    """Stands in for aiosmtplib.SMTP and records what the sender does with it."""

    login_error: Exception | None = None
    send_error: Exception | None = None
    send_delay: float = 0
    kwargs: dict[str, Any] = field(default_factory=dict)
    logins: list[tuple[str, str]] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> "FakeSmtp":
        self.kwargs = kwargs
        return self

    async def __aenter__(self) -> "FakeSmtp":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def login(self, username: str, password: str) -> None:
        if self.login_error is not None:
            raise self.login_error
        self.logins.append((username, password))

    async def send_message(self, message: Message) -> None:
        await asyncio.sleep(self.send_delay)
        if self.send_error is not None:
            raise self.send_error
        self.messages.append(message)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> FakeSmtp:
    fake = FakeSmtp()
    monkeypatch.setattr(aiosmtplib, "SMTP", fake)
    return fake


def decoded_subject(message: Message) -> str:
    return str(make_header(decode_header(message["Subject"])))


async def test_message_has_the_headers_and_one_html_part(smtp: FakeSmtp) -> None:
    result = await SmtpEmailSender(make_config()).send(RECIPIENT, "Oferta", "<p>Dzień dobry</p>")

    assert result.success
    assert result.error is None
    [message] = smtp.messages
    assert message.get_content_type() == "multipart/alternative"
    assert message["From"] == "noreply@example.com"
    assert message["To"] == RECIPIENT
    assert decoded_subject(message) == "Oferta"
    assert email.utils.parsedate_to_datetime(message["Date"]) is not None
    assert message["Message-ID"].startswith("<")
    assert result.smtp_message_id == message["Message-ID"]
    payload = message.get_payload()
    assert isinstance(payload, list)
    [part] = payload
    assert isinstance(part, Message)
    assert part.get_content_type() == "text/html"
    assert part.get_content_charset() == "utf-8"
    body = part.get_payload(decode=True)
    assert isinstance(body, bytes)
    assert body.decode("utf-8") == "<p>Dzień dobry</p>"


async def test_emoji_subject_survives_a_round_trip(smtp: FakeSmtp) -> None:
    subject = "Promocja 🎉 zażółć gęślą jaźń"

    await SmtpEmailSender(make_config()).send(RECIPIENT, subject, "<p>x</p>")

    parsed = email.message_from_bytes(smtp.messages[0].as_bytes())
    assert decoded_subject(parsed) == subject


async def test_logs_in_with_user_and_password(smtp: FakeSmtp) -> None:
    await SmtpEmailSender(make_config()).send(RECIPIENT, "s", "b")

    assert smtp.logins == [("noreply@example.com", "secret-password")]


async def test_no_login_without_a_password(smtp: FakeSmtp) -> None:
    result = await SmtpEmailSender(make_config(smtp_password=None)).send(RECIPIENT, "s", "b")

    assert result.success
    assert smtp.logins == []


@pytest.mark.parametrize(
    ("port", "use_tls", "expected"),
    [
        pytest.param(465, True, {"use_tls": True, "start_tls": False}, id="465-implicit-tls"),
        pytest.param(587, True, {"use_tls": False, "start_tls": True}, id="587-starttls"),
        pytest.param(2525, False, {"use_tls": False, "start_tls": False}, id="tls-off"),
        pytest.param(465, False, {"use_tls": False, "start_tls": False}, id="465-tls-off"),
    ],
)
async def test_tls_arguments(
    smtp: FakeSmtp, port: int, use_tls: bool, expected: dict[str, bool]
) -> None:
    # No password, so TLS off still connects (a login without TLS is refused, see below).
    config = make_config(smtp_port=port, smtp_use_tls=use_tls, smtp_password=None)

    await SmtpEmailSender(config).send(RECIPIENT, "s", "b")

    base = {"hostname": "smtp.example.com", "port": port, "timeout": 8}
    assert smtp.kwargs == base | expected


async def test_login_without_tls_is_refused_before_connecting(
    smtp: FakeSmtp, caplog: pytest.LogCaptureFixture
) -> None:
    config = make_config(smtp_port=2525, smtp_use_tls=False)

    result = await SmtpEmailSender(config).send(RECIPIENT, "s", "<p>secret body</p>")

    assert result == SendResult(success=False, smtp_message_id=None, error=LOGIN_WITHOUT_TLS_ERROR)
    assert smtp.kwargs == {}
    assert smtp.logins == []
    assert smtp.messages == []
    assert RECIPIENT in caplog.text
    assert "secret-password" not in caplog.text


async def test_sends_without_tls_when_there_is_no_password(smtp: FakeSmtp) -> None:
    config = make_config(smtp_port=2525, smtp_use_tls=False, smtp_password=None)

    result = await SmtpEmailSender(config).send(RECIPIENT, "s", "b")

    assert result.success
    assert smtp.logins == []
    assert len(smtp.messages) == 1


@pytest.mark.parametrize(
    ("where", "error", "expected"),
    [
        pytest.param(
            "login",
            aiosmtplib.SMTPAuthenticationError(535, "bad credentials"),
            "SMTP Authentication failed: (535, 'bad credentials')",
            id="authentication",
        ),
        pytest.param(
            "send",
            aiosmtplib.SMTPRecipientsRefused(
                [aiosmtplib.SMTPRecipientRefused(550, "no such user", RECIPIENT)]
            ),
            f"Recipient refused: [SMTPRecipientRefused(550, 'no such user', '{RECIPIENT}')]",
            id="recipients-refused",
        ),
        pytest.param(
            "send",
            aiosmtplib.SMTPException("server said no"),
            "SMTP error: server said no",
            id="smtp-exception",
        ),
        pytest.param("send", RuntimeError("boom"), "Unexpected error: boom", id="unexpected"),
    ],
)
async def test_errors_become_failed_results(
    smtp: FakeSmtp, caplog: pytest.LogCaptureFixture, where: str, error: Exception, expected: str
) -> None:
    if where == "login":
        smtp.login_error = error
    else:
        smtp.send_error = error

    result = await SmtpEmailSender(make_config()).send(RECIPIENT, "s", "<p>secret body</p>")

    assert not result.success
    assert result.smtp_message_id is None
    assert result.error == expected
    assert RECIPIENT in caplog.text
    assert "secret-password" not in caplog.text
    assert "secret body" not in caplog.text


def test_timeout_is_8_seconds() -> None:
    assert smtp_sender.SMTP_TIMEOUT_SECONDS == 8


async def test_timeout_becomes_a_failed_result(
    smtp: FakeSmtp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smtp_sender, "SMTP_TIMEOUT_SECONDS", 0.05)
    smtp.send_delay = 1

    result = await SmtpEmailSender(make_config()).send(RECIPIENT, "s", "b")

    assert result == SendResult(
        success=False, smtp_message_id=None, error="SMTP error: timed out after 0.05 s"
    )


async def test_aiosmtplib_timeout_gets_the_same_message(smtp: FakeSmtp) -> None:
    smtp.send_error = aiosmtplib.SMTPReadTimeoutError("Timed out waiting for server response")

    result = await SmtpEmailSender(make_config()).send(RECIPIENT, "s", "b")

    assert result.error == "SMTP error: timed out after 8 s"


@dataclass
class FakeSender:
    """Answers by recipient and records how many sends ran at once."""

    running: int = 0
    max_running: int = 0

    async def send(self, to: str, subject: str, html_body: str) -> SendResult:
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(0.01)
            if to.startswith("raise"):
                raise RuntimeError("connection lost")
            if to.startswith("fail"):
                return SendResult(success=False, smtp_message_id=None, error="SMTP error: no")
            return SendResult(success=True, smtp_message_id=f"<{to}>", error=None)
        finally:
            self.running -= 1


async def test_send_many_reports_every_result_within_the_concurrency_cap() -> None:
    sender = FakeSender()
    items = [
        EmailItem(to=to, subject="s", html_body="b")
        for to in ["ok1@x.pl", "fail@x.pl", "raise@x.pl", "ok2@x.pl", "ok3@x.pl"]
    ]
    results: dict[str, SendResult] = {}

    async def on_result(item: EmailItem, result: SendResult) -> None:
        results[item.to] = result

    await send_many(sender, items, max_concurrent=2, on_result=on_result)

    assert results == {
        "ok1@x.pl": SendResult(success=True, smtp_message_id="<ok1@x.pl>", error=None),
        "fail@x.pl": SendResult(success=False, smtp_message_id=None, error="SMTP error: no"),
        "raise@x.pl": SendResult(
            success=False, smtp_message_id=None, error="Unexpected error: connection lost"
        ),
        "ok2@x.pl": SendResult(success=True, smtp_message_id="<ok2@x.pl>", error=None),
        "ok3@x.pl": SendResult(success=True, smtp_message_id="<ok3@x.pl>", error=None),
    }
    assert sender.max_running == 2


async def smtp4dev_listening() -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("localhost", 2525), 1.5)
    except (OSError, TimeoutError):
        return False
    writer.close()
    await writer.wait_closed()
    return True


@pytest.mark.online
async def test_sends_through_smtp4dev() -> None:
    if not await smtp4dev_listening():
        pytest.skip("smtp4dev is not listening on localhost:2525 (make docker-up)")
    config = SmtpConfig(
        smtp_server="localhost",
        smtp_port=2525,
        smtp_user="noreply@localhost",
        smtp_password=None,
        smtp_use_tls=False,
    )

    result = await SmtpEmailSender(config).send(
        "jan@example.com", "Email Sender — test online 🎉", "<p>Test online</p>"
    )

    assert result.success, result.error
    assert result.smtp_message_id is not None
