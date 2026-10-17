# API single-email resend: `POST /emails/{id}/resend`

> Feature: Add `POST /emails/{id}/resend`, a synchronous single-email resend within the BFF's timeout, as specified in `specs/email-sender/backend.md` API-13 (covers B9, resend part)

## Context

Roadmap item API-13 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-13: Single-email resend", plus that file's "Rules for every
item" (top of the file). The wire format is `specs/email-sender/api-contract.md` §3.4 (the
`POST /emails/{id}/resend` row, already documented there) and §5 (8 s timeout, error messages).
This spec restates the backend.md section; where they differ, this spec wins.

API-13 depends only on API-8 (sending) and API-10 (email log), both merged. API-11 and API-12
(campaign send/resend) are not built yet and are not needed here.

What exists in `api/` today:

- `app/api/emails.py`: router `/emails`, tag *Emails*, every endpoint with `PrincipalDep` and
  `EmailServiceDep`, fixed paths registered before `/{email_id}`; path IDs typed `DbInt`
  (`app/schemas/base.py`). Single-email endpoints return `service.to_schema(...)`. No resend
  route (spec `specs/features/019-api-email-log.md` kept it out on purpose; this job adds it).
- `app/services/email_service.py`: `EmailService(emails: EmailRepository)` with `get_by_id`
  (raises `NotFoundError("Email {id} not found")`), `update`, `mark_opened`, `to_schema` (subject
  and content from the row's snapshot). Its docstring says "Nothing here sends email", which this
  job makes untrue.
- `app/repositories/email_repository.py`: `EmailRepository`, each write sets fields and commits
  (`mark_opened`, `soft_delete`, `update`). `app/models/email.py`: `Email` with `status`
  (`EmailStatus`), `sent_at`, `error_message`, `retry_count`, `smtp_message_id`, `subject`,
  `body`.
- The sending pattern to reuse is `POST /config/smtp/test` in `app/api/config.py`:
  `SmtpConfigService.get_smtp_config_for_sending(principal.subject)` (`None` → `BusinessRuleError`
  "SMTP configuration not found. Please configure SMTP settings first."), then
  `sender_factory(config).send(to, subject, html_body)` returning `SendResult(success,
  smtp_message_id, error)` (`app/services/smtp_sender.py`). `SmtpEmailSender` never raises; it
  maps every failure to `error` and enforces the 8 s `SMTP_TIMEOUT_SECONDS`.
- `app/dependencies.py`: `get_email_service(session)` builds `EmailService(EmailRepository(session))`;
  `get_smtp_config_service(session, container)` builds `SmtpConfigService(ConfigRepository(session,
  container.encryption))`; `container.email_sender_factory` is the `EmailSenderFactory`
  (`create_app(..., email_sender_factory=...)` in `app/main.py`, default `SmtpEmailSender`).
- Tests: `tests/test_smtp_test_api.py` defines `FakeSenders` (a fake `EmailSenderFactory` that
  records configs and sends and answers a settable `SendResult`) and overrides the `app` fixture
  to pass it. `tests/test_emails_service.py` builds `EmailService(repository)` in its `service`
  fixture. `tests/test_emails_api.py` creates rows with `add_email(...)` through the repository
  and has parametrized lists for 401 (`test_missing_token_answers_401`) and for IDs above int32 on
  writes (`test_email_id_above_int32_answers_422_on_writes`).

## Requirements

1. `EmailService.resend(email_id: int, user_sub: str) -> Email`, in this order:
   1. load the email with `get_by_id` (unknown or soft-deleted → `NotFoundError` "Email {id} not
      found", answered 404);
   2. `get_smtp_config_for_sending(user_sub)`; `None` → `BusinessRuleError` "SMTP configuration
      not found. Please configure SMTP settings first." (400), with the row unchanged;
   3. send once through the sender factory to `email.recipient_email` with `email.subject` and
      `email.body` (the stored snapshot, never the campaign's current subject or content);
   4. update the same row and commit: `status` = `sent` on success, `failed` on failure;
      `sent_at` = now on success and left unchanged on failure; `smtp_message_id` = the result's
      value; `error_message` = `null` on success, the result's `error` on failure;
      `retry_count` = previous value + 1. No other column changes.
2. `EmailService` gets what it needs through its constructor: the `EmailRepository`, a
   `SmtpConfigService` and the `EmailSenderFactory`. `get_email_service` in `app/dependencies.py`
   builds it from the request session and the container (same `SmtpConfigService` construction
   as `get_smtp_config_service`, and `container.email_sender_factory`). The service imports no
   `sqlalchemy` and raises only domain errors. Update the module docstring so it no longer says
   nothing here sends email.
3. The row update is one new `EmailRepository` method that sets the fields of requirement 1.4 and
   commits, following the style of `mark_opened`.
4. Router: `POST /emails/{email_id}/resend` in `app/api/emails.py`, `email_id: DbInt`, no body,
   `PrincipalDep` (the user is `principal.subject`) and `EmailServiceDep`, `response_model=EmailSchema`,
   status 200, returning `service.to_schema(...)`. An SMTP failure is not an HTTP error: it
   answers 200 with the row in `failed` and its `errorMessage`.
5. No retries and no extra timeout: the single `send` call and the sender's 8 s timeout keep the
   request inside the BFF's 10 s.
6. The resend does not touch the campaign, its recipients (`campaign_recipients`) or any other
   email row [PARITY].
7. Tests, through the existing fixtures, addresses on `example.com` or `.example`, no real SMTP:
   - service tests in `tests/test_emails_service.py` (update its `service` fixture for the new
     constructor, using a fake sender factory and a real `SmtpConfigService` on the test session
     with SMTP settings saved for a test `user_sub`): success, failure, no SMTP settings, unknown
     email, snapshot used after the campaign was edited, the campaign and its recipient unchanged;
   - endpoint tests with a fake sender passed to `create_app` (reuse `FakeSenders`; moving it into
     `tests/conftest.py` so both modules import it is allowed, with no behaviour change):
     200 success and failure bodies, 400 without SMTP settings, 404 for an unknown email, and the
     resend added to the existing 401 and above-int32 parametrized lists in
     `tests/test_emails_api.py`.
8. No new dependency, migration, setting or doc change: `api-contract.md` §3.4 and §5 already
   describe this endpoint, and `AGENTS.md` lists no endpoints.

## Acceptance criteria

All run in `api/` with PostgreSQL up (`make docker-up` or any run mode).

1. Success: with SMTP settings saved for the caller and a fake sender answering success with
   `smtpMessageId` `"<1@test>"`, `POST /emails/{id}/resend` on a `failed` email with
   `retryCount` 0 and an `errorMessage` answers 200 with an `EmailSchema` (exactly the contract
   keys) where `status` is `"sent"`, `sentAt` is set, `retryCount` is 1, `smtpMessageId` is
   `"<1@test>"` and `errorMessage` is `null`; a following `GET /emails/{id}` shows the same.
   Verified by an endpoint test.
2. Failure: with the fake sender answering failure with error `"SMTP error: boom"`, the resend
   answers 200 with `status` `"failed"`, `errorMessage` `"SMTP error: boom"`, `retryCount`
   incremented, and `sentAt` equal to its value before the call (both for a null and a previously
   set `sentAt`). Verified by service and endpoint tests.
3. No SMTP settings for the caller: 400 with
   `{"detail": "SMTP configuration not found. Please configure SMTP settings first."}`, the fake
   sender was not called, and the row is unchanged (`GET` before and after are equal). Verified by
   an endpoint test.
4. Unknown or soft-deleted email ID: 404 `{"detail": "Email {id} not found"}`, sender not called.
   An ID above int32 answers 422 (added to `test_email_id_above_int32_answers_422_on_writes`).
5. No token: 401 with the same body and `WWW-Authenticate` header as the other endpoints (resend
   added to `test_missing_token_answers_401`).
6. Snapshot: after the campaign's subject and content are changed with `PUT /campaigns/{id}`, the
   fake sender receives `(recipient_email, <stored subject>, <stored body>)` of the email row, not
   the campaign's new text. Verified by a test asserting on `FakeSenders.sent`.
7. The sender is built from the caller's saved settings: the `SmtpConfig` recorded by
   `FakeSenders.configs` has the server and port saved by that user with `PUT /config/smtp`.
8. Parity: after a resend, `GET /campaigns/{id}` shows the same `status` and `stats`, and the
   campaign's recipients are unchanged, as before the call. Verified by a test.
9. Routes: `uv run python -c "from app.main import create_app; s = create_app().openapi(); print({p: sorted(s['paths'][p]) for p in s['paths'] if p.startswith('/emails')})"`
   prints the API-10 paths plus `/emails/{email_id}/resend` (`post`), tagged `Emails`.
10. `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` pass in `api/`;
    `uv run alembic check` reports no differences; nothing under `bff/` or `web/` changed
    (`git diff --stat main -- bff web` is empty).

## Out of scope

- Campaign send and resend, `campaign_sender.py`, `email_content.py`, `send_many` use (API-11,
  API-12), and the demo seed (API-14).
- Retries, a `max_retries` check, a status precondition (any email can be resent), touching
  `error_code`, `smtp_response`, `delivered_at` or other columns, rendering or re-substituting
  the body.
- Catching sender exceptions in the service, changing `SmtpEmailSender`, the timeout or the
  error messages.
- Changes to `api-contract.md`, `backend.md`, `AGENTS.md`, the BFF, `web/`, settings,
  dependencies, migrations, ruff/mypy config.
- Committing the main checkout's unrelated change to `web/package-lock.json`.

## Assumptions

- `smtp_message_id` is overwritten with the result's value, so a failed resend sets it to
  `null`: the contract lists it among the always-updated fields and gives the "only on success"
  exception for `sentAt` alone.
- No `max_retries` check and no status check: backend.md and the contract give none for the
  single-email resend, and the source (parity) had none.
- A failed send answers 200 with the `failed` row, not 400: the contract gives only `404` and the
  missing-settings `400` for this endpoint (unlike `POST /config/smtp/test`).
- The 404 check runs before the SMTP settings check: backend.md lists them in that order.
- `EmailService` takes `SmtpConfigService` and the sender factory in its constructor, because
  backend.md fixes the signature `resend(email_id, user_sub)`.
