"""Sending email over SMTP (api-contract.md §5). send_many is the only place with concurrency."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Protocol, TypeVar

import aiosmtplib

from app.services.smtp_config_service import SmtpConfig

logger = logging.getLogger(__name__)

# Below the BFF's 10 s proxy timeout, so a synchronous send answers before the BFF gives up.
SMTP_TIMEOUT_SECONDS = 8
IMPLICIT_TLS_PORT = 465


@dataclass(frozen=True)
class SendResult:
    success: bool
    smtp_message_id: str | None
    error: str | None


@dataclass(frozen=True)
class EmailItem:
    """One email for send_many; subclass it to carry more, such as the recipient's row."""

    to: str
    subject: str
    html_body: str


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, html_body: str) -> SendResult: ...


EmailSenderFactory = Callable[[SmtpConfig], EmailSender]

ItemT = TypeVar("ItemT", bound=EmailItem)


def build_message(sender: str | None, to: str, subject: str, html_body: str) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    if sender:
        message["From"] = sender
    message["To"] = to
    # Header.encode gives the RFC 2047 encoded word, so non-ASCII subjects (emoji) arrive intact.
    message["Subject"] = Header(subject, "utf-8").encode()
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message


class SmtpEmailSender:
    """One connection per send, with the user's saved settings."""

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    async def send(self, to: str, subject: str, html_body: str) -> SendResult:
        message = build_message(self._config.smtp_user, to, subject, html_body)
        # Most specific first: the aiosmtplib errors are SMTPException subclasses, and its
        # timeouts are TimeoutError too, so every timeout gets the same message.
        try:
            async with asyncio.timeout(SMTP_TIMEOUT_SECONDS):
                await self._deliver(message)
        except aiosmtplib.SMTPAuthenticationError as exc:
            error = f"SMTP Authentication failed: {exc}"
        except aiosmtplib.SMTPRecipientsRefused as exc:
            error = f"Recipient refused: {exc}"
        except TimeoutError:
            error = f"SMTP error: timed out after {SMTP_TIMEOUT_SECONDS} s"
        except aiosmtplib.SMTPException as exc:
            error = f"SMTP error: {exc}"
        except Exception as exc:
            error = f"Unexpected error: {exc}"
        else:
            return SendResult(success=True, smtp_message_id=message["Message-ID"], error=None)
        # Neither the password nor the body goes into the log.
        logger.warning("Sending email to %s failed: %s", to, error)
        return SendResult(success=False, smtp_message_id=None, error=error)

    async def _deliver(self, message: MIMEMultipart) -> None:
        config = self._config
        implicit_tls = config.smtp_use_tls and config.smtp_port == IMPLICIT_TLS_PORT
        # start_tls is always given: aiosmtplib's default None upgrades whenever the server
        # offers STARTTLS, even with TLS off.
        smtp = aiosmtplib.SMTP(
            hostname=config.smtp_server,
            port=config.smtp_port,
            timeout=SMTP_TIMEOUT_SECONDS,
            use_tls=implicit_tls,
            start_tls=config.smtp_use_tls and not implicit_tls,
        )
        async with smtp:
            if config.smtp_user and config.smtp_password:
                await smtp.login(config.smtp_user, config.smtp_password)
            await smtp.send_message(message)


async def send_many(
    sender: EmailSender,
    items: Iterable[ItemT],
    max_concurrent: int,
    on_result: Callable[[ItemT, SendResult], Awaitable[None]],
) -> None:
    """Send every item, at most max_concurrent at once, and await on_result as each finishes."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def send_one(item: ItemT) -> None:
        async with semaphore:
            try:
                result = await sender.send(item.to, item.subject, item.html_body)
            except Exception as exc:
                logger.warning("Sending email to %s failed: %s", item.to, exc)
                result = SendResult(
                    success=False, smtp_message_id=None, error=f"Unexpected error: {exc}"
                )
        await on_result(item, result)

    # One failing item never stops the others; an on_result error is raised once all finished.
    outcomes = await asyncio.gather(*(send_one(item) for item in items), return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            raise outcome
