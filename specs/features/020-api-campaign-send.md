# Campaign send in the background

> Feature: Send campaigns in the background: `POST /campaigns/{id}/send` checks the request, moves the campaign to `sending` atomically and answers 202, a background task sends with a semaphore and commits each result, and a startup sweep fails campaigns a restart interrupted, as specified in `specs/email-sender/backend.md` API-11 (covers B8, send part)

## Context

This is roadmap item API-11 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-11: Campaign send in the background" (Requirements,
Pitfalls, Acceptance criteria), plus that file's "Rules for every item" at the top. The wire
rules are in `specs/email-sender/api-contract.md` §3.3 (the `send` row, `max_concurrent` 1 to
50) and §4 (checks 1 to 4, steps 5 to 8, the exact English messages), and the background in
`specs/email-sender/README.md` §3.5 (D17), D3 (variables), D4 (plain text to HTML), D10
(concurrency), W-14 (inactive clients), W-17 (one `Email` row per pair, `retryCount`), W-24 (no
synchronous send). This spec restates them; where they differ, this spec wins. Resend
(`POST /campaigns/{id}/resend`, `retry_recipient_ids`) is the next item, API-12.

What exists today, in `api/`:

- `app/api/campaigns.py`: the campaigns router (list, create, get, `PUT`, `DELETE`, `POST
  /{id}/recipients`), each endpoint with `PrincipalDep` and `CampaignServiceDep`. No send.
- `app/services/campaign_service.py`: `CampaignService` with `get_by_id` (404 "Campaign {id} not
  found"), `update` (400 "Only draft campaigns can be modified" for any non-draft), `delete`
  (any status), `to_schema` and `compute_stats`. No rule for `sending` yet (backend.md API-9
  Pitfalls defers it here).
- `app/repositories/campaign_repository.py`: `CampaignRepository` (`get_by_id` skips deleted
  campaigns; recipients and their clients load with `selectin`, deleted recipients included and
  skipped by readers).
- `app/models/campaign.py`: `Campaign` (`status: CampaignStatus` with `draft`, `sending`,
  `sent`, `failed`, `scheduled`; `sent_at`), `CampaignRecipient` (`status: RecipientStatus`,
  `sent_at`, `error`, `client`). `app/models/client.py`: `Client` (`company_name`,
  `primary_email`, `is_active`, `is_deleted`).
- `app/models/email.py` and `app/repositories/email_repository.py` (job 019): `Email` with the
  `subject`/`body` snapshot, `status: EmailStatus`, `sent_at`, `error_message`, `retry_count`
  (default 0), `max_retries` (default 3), `smtp_message_id`; `EmailRepository.create(campaign=,
  client=, recipient_email=, subject=, body=)` (takes objects, commits) and
  `get_for_recipient(campaign_id, client_id)` (newest row of the pair). Job 019 changed the
  `emails` FKs to `ON DELETE RESTRICT` (rows are never hard-deleted), unlike backend.md's
  CASCADE; nothing here deletes rows, so that does not matter for this item.
- `app/services/smtp_sender.py` (job 017): `EmailSender` protocol, `EmailSenderFactory =
  Callable[[SmtpConfig], EmailSender]`, `SendResult`, `EmailItem` (subclass it to carry the
  recipient), and `send_many(sender, items, max_concurrent, on_result)`, the only place with
  send concurrency (a semaphore; `on_result` is awaited as each send finishes; a raising sender
  becomes an `Unexpected error: …` result; an `on_result` error is re-raised after all finish).
- `app/services/smtp_config_service.py`: `SmtpConfigService.get_smtp_config_for_sending(user_sub)`
  returns a `SmtpConfig` (defaults port 587, TLS on) or `None` when no server is saved.
- `app/dependencies.py`: `Container` (`verifier`, `notes`, `sessions` (the session factory),
  `encryption`, `email_sender_factory`), `build_container(settings, …)`, `SessionDep` (one
  session per request) and the per-area service providers. `Settings` is not in the container.
- `app/main.py`: `create_app(settings, *, http_client, clock, session_factory,
  email_sender_factory)`; the lifespan runs `run_migrations` in a thread, logs and re-raises on
  failure; the `DomainError` handler maps `NotFoundError` to 404 and the rest to 400.
- `app/config.py`: `Settings` (env prefix `API_`), no `email_max_concurrent` yet;
  `api/.env.example` has no `API_EMAIL_MAX_CONCURRENT` (README.md's env table already lists it).
- `app/database.py`: `create_session_factory` uses `expire_on_commit=False`.
- Tests: `tests/conftest.py` gives `session_factory` (bound to one connection inside an outer
  transaction, savepoint per session), `app`, `client` (`httpx.ASGITransport`), `bearer`.
  `tests/test_smtp_test_api.py` has the `FakeSenders` factory pattern and an `app` fixture
  override that passes `email_sender_factory=`; `tests/test_campaigns_api.py` has `create_client`,
  `create` and `set_status` helpers; `tests/test_database.py` drives the lifespan with
  `app.router.lifespan_context(app)`.

FastAPI is 0.143 (`api/uv.lock`). Since 0.118 the exit code of a `yield` dependency runs after
the response is done, so the request's `SessionDep` session may still be open (idle) while the
background task runs. backend.md's Pitfall "the request's session is closed when the task runs"
is therefore not guaranteed: the task must never touch the request session, and must not rely on
it being closed.

## Requirements

1. `app/services/email_content.py` with one public function that renders a campaign's content
   for one client:
   - when the content has no HTML tag (no match for `<[a-zA-Z/!][^>]*>`), it is HTML-escaped
     (`html.escape`) and then every `\n` becomes `<br>` (a `\r\n` becomes one `<br>`); content
     with a tag is left as it is;
   - then `{name}`, `{email}` and `{company}` are replaced with one `re.sub` over these three
     keys only: `{company}` and `{name}` = `client.company_name`, `{email}` =
     `client.primary_email`, each value HTML-escaped. Any other `{x}` stays as it is.
2. `app/services/campaign_sender.py` with a `CampaignSender` class and the three operations of
   backend.md API-11:
   - `start(campaign_id, user_sub, retry_recipient_ids=None)`: runs contract §4 checks 1 to 4
     in order, before changing anything (`retry_recipient_ids` is always `None` in this item:
     `draft` chooses the `pending` recipients, `failed` chooses every `failed` recipient;
     deleted recipients are never chosen). Messages, exactly: 404 "Campaign {id} not found";
     400 "Campaign cannot be sent — current status: {status}" (an em dash, status as the
     lowercase value); 400 "Campaign has no pending recipients"; 400 "SMTP configuration not
     found. Please configure SMTP settings first.". Then step 5 in one transaction: the
     conditional `UPDATE campaigns SET status = 'sending' WHERE id = :id AND status IN
     ('draft','failed') AND is_deleted = false`; zero rows changed → re-read the stored status
     and raise the check-1 message with it, changing nothing; otherwise reset the chosen failed
     recipients to `pending` (`error = None`, `sent_at = None`) and commit once. It returns the
     campaign (its `status` reads `sending`) and the `SmtpConfig` for the task.
   - `run(campaign_id, smtp_config, max_concurrent)`: the background task. It opens its own
     session from the container's session factory (never the request's), loads the campaign's
     non-deleted `pending` recipients with their clients, builds the sender with the
     container's `email_sender_factory(smtp_config)` and sends through `send_many`. Before
     sending, per recipient (§4 step 6):
     - client inactive or soft-deleted → recipient `failed`, `error = "Client is inactive"`, no
       send and no `Email` row;
     - its existing `Email` row (`get_for_recipient`) has `retry_count >= max_retries` →
       recipient `failed`, `error = "Maximum retries exceeded"`, no send, the row unchanged.
     Every other recipient is sent to `client.primary_email` only (never `additional_emails`),
     with `campaign.subject` and the rendered body (Requirement 1). Each result is written in
     `on_result` under one `asyncio.Lock` and committed before the lock is released:
     - success → recipient `sent`, `sent_at = now`, `error = None`; `Email` row `sent`,
       `sent_at = now`, `smtp_message_id`, `error_message = None`;
     - failure → recipient `failed` with `error`; `Email` row `failed` with `error_message`
       (`sent_at` and `smtp_message_id` not set);
     - the first attempt for the (campaign, client) pair creates the `Email` row; a later one
       updates that row and adds 1 to `retry_count`; every attempt writes the `subject` and
       `body` it sent and the `recipient_email`.
     Then step 7: any non-deleted recipient still `failed` → campaign `failed`; otherwise
     `sent` with `sent_at = now`; committed. Any unexpected exception in the task is caught
     and logged: the recipients still `pending` become `failed` with `"Unexpected error: {exc}"`
     and the campaign `failed` (written in a fresh session if the first is unusable). `run`
     never raises.
   - `recover_interrupted()`: §4 step 8. For every non-deleted campaign in `sending`, its
     `pending` recipients become `failed` with `"Sending interrupted"`, then step 7 sets its
     status (`failed` when any recipient is failed, else `sent` with `sent_at`). Committed.
   Only the SMTP calls run concurrently; one `AsyncSession` is never used by two coroutines at
   once.
3. Router `app/api/campaigns.py`: `POST /campaigns/{campaign_id}/send` with
   `max_concurrent: int | None = Query(None, ge=1, le=50)` (`None` → the
   `email_max_concurrent` setting), `status_code=202`, `response_model=CampaignSchema`,
   `PrincipalDep` (the user is `principal.subject`), and FastAPI `BackgroundTasks` adding
   `run(campaign_id, smtp_config, max_concurrent)` after `start` succeeds. It answers
   `CampaignSchema` with `status: "sending"`. The default concurrency reaches the router through
   `app/dependencies.py` (for example a field on `Container` set from `Settings` in
   `build_container`); `CampaignSender` is wired there like the other services.
4. `Settings.email_max_concurrent: int = Field(10, ge=1, le=50)` in `app/config.py`;
   `api/.env.example` gets `API_EMAIL_MAX_CONCURRENT=10` with a one-line comment.
5. The lifespan in `app/main.py` calls `recover_interrupted()` after the migrations succeed and
   before `yield`, with a session from the app's session factory. An exception there is logged
   and re-raised, as for the migrations.
6. `CampaignService.update` and `CampaignService.delete` raise `BusinessRuleError("Campaign is
   being sent")` for a `sending` campaign (checked after the 404). `update` keeps "Only draft
   campaigns can be modified" for `sent`, `failed` and `scheduled`. `add_recipients` keeps its
   own message for every non-draft, `sending` included.
7. Tests, all with a fake sender factory passed as `email_sender_factory` to `create_app` (the
   `FakeSenders` pattern, extended to record in-flight sends and to fail or raise for chosen
   addresses), never real SMTP: unit tests for `email_content`; service tests for `start`,
   `run` and `recover_interrupted` against the test database; endpoint tests through `client`
   covering 202, 400, 404, 422 and 401 for `send`, and the 400 for `PUT`/`DELETE` on `sending`;
   a lifespan test that a campaign left in `sending` is failed after
   `app.router.lifespan_context(app)`. Add `send` to the 401 parametrization in
   `tests/test_campaigns_api.py`.
8. `specs/email-sender/api-contract.md` needs no change unless the implementation disagrees with
   it; if it does, the contract is updated in this job. `AGENTS.md` needs no change (the
   setting has a default, so an existing `api/.env` keeps working).

## Acceptance criteria

All run in `api/` with PostgreSQL up (`make docker-up` or any run mode); none needs smtp4dev.

1. A draft with 3 recipients and saved SMTP settings (`PUT /config/smtp`): `POST
   /campaigns/{id}/send` answers 202 with `status: "sending"`; the next `GET /campaigns/{id}`
   shows `status: "sent"`, a `sentAt`, every recipient `sent`, and `GET
   /emails/campaign/{id}` lists 3 emails `sent` with `smtpMessageId`, the campaign subject and
   the rendered body. Verified by an endpoint test.
2. One failure out of 3 (the fake fails one address): the campaign ends `failed`,
   `stats.sent = 2`, `stats.failed = 1`; that recipient's `error` and its `Email` row's
   `errorMessage` carry the fake's error. Endpoint test.
3. `send` on that failed campaign sends only to the failed recipient (the fake records one
   call), updates its existing `Email` row (`retryCount` 1, still 3 rows) and the campaign ends
   `sent`. Endpoint test.
4. 400 with the exact `detail`: on `sent` ("Campaign cannot be sent — current status: sent"), on
   `sending` ("… current status: sending"), on a draft with no recipients ("Campaign has no
   pending recipients"), without SMTP settings ("SMTP configuration not found. Please configure
   SMTP settings first."); 404 "Campaign {id} not found" for an unknown or deleted campaign;
   422 for `max_concurrent=0` and `max_concurrent=51`; 401 without a token. After each failing
   check the campaign's status and recipients are unchanged and the fake was not called.
   Endpoint tests.
5. Lost race: with the stored status changed to `sending` after the checks and before the
   conditional update (for example by patching a step `start` calls after check 4 to update the
   row through another session), `start` raises "Campaign cannot be sent — current status:
   sending", the recipients are unchanged and nothing is sent. Service test.
6. Rendering, in unit tests of `email_content`: plain content `"Dzień dobry {name},\n<{email}> {x}"`
   (no tag, since `<{` doesn't match the pattern) is escaped and gets `<br>`; content with a tag
   (`<p>…</p>`) keeps its tags and gets no `<br>`; `{company}`/`{name}` become the company name
   and `{email}` the primary email; a company name `A<B` arrives as `A&lt;B`; an unknown `{x}`
   stays.
7. An inactive client among the recipients: its recipient ends `failed` with "Client is
   inactive", the fake was not called for its address and no `Email` row exists for it. A
   recipient whose `Email` row has `retry_count` equal to `max_retries` ends `failed` with
   "Maximum retries exceeded" and is not sent. Service or endpoint tests.
8. With 6 recipients and `max_concurrent=2`, the fake (whose `send` awaits an
   `asyncio.sleep(0)` or an event) records at most 2 sends in flight; with no `max_concurrent`
   the setting's value is passed. Test.
9. An unexpected error in the task, outside one recipient's send (for example the sender
   factory raising, or the `on_result` write raising for one recipient): `run` returns without
   raising, the recipients still `pending` and the campaign end `failed`, with errors starting
   "Unexpected error: ". A sender whose `send` raises for one address only fails that
   recipient with "Unexpected error: …" (`send_many` turns it into a result) and the others are
   sent. Service tests.
10. `recover_interrupted()` on a campaign set to `sending` with 2 pending and 1 sent recipient:
    the pending ones become `failed` with "Sending interrupted" and the campaign `failed`; a
    campaign in `draft` is untouched. Service test, plus the lifespan test of Requirement 7.
11. `PUT /campaigns/{id}` and `DELETE /campaigns/{id}` on a campaign set to `sending` (with
    `set_status`) answer 400 `{"detail": "Campaign is being sent"}`; `PUT` on `sent` still
    answers "Only draft campaigns can be modified". Endpoint tests.
12. `grep API_EMAIL_MAX_CONCURRENT=10 api/.env.example` matches.
13. In `api/`: `uv run pytest`, `uv run ruff check .`, `uv run mypy app tests` and `uv run
    alembic check` pass; `bff/` is untouched (`git diff --stat main -- bff` is empty).

## Out of scope

- `POST /campaigns/{id}/resend`, `CampaignResendSchema` and any `retry_recipient_ids` handling
  beyond the `None` default (API-12).
- `POST /emails/{id}/resend` (single-email resend).
- A task queue, a scheduler, sending `scheduled` campaigns, or cancelling a running send.
- A `text/plain` MIME part, or changes to `smtp_sender.py` beyond what `run` needs from it
  (`send_many`, `EmailItem` subclassing).
- Any migration or model change (the `sending` status and the `Email` columns already exist).
- Sending to `additional_emails`.
- Any `web/` or `bff/` change (the SPA polling is UI work, Phase 5).

## Assumptions

- A soft-deleted client gets the same treatment and message as an inactive one ("Client is
  inactive"). Reason: contract §4 step 6 groups them under one message.
- "Maximum retries exceeded" leaves the `Email` row untouched (no status change, no
  `retry_count` increment). Reason: no attempt was made, and the contract names only the
  recipient's change.
- A failed send does not touch the `Email` row's earlier `sent_at` or `smtp_message_id`, and a
  failed recipient keeps `sent_at = None`. Reason: the contract sets them on success only.
- The campaign's `sent_at` is set only when it ends `sent`, and left as it is when it ends
  `failed`. Reason: step 7 names `sentAt` only for `sent`.
- `recover_interrupted()` ends a campaign with no failed recipients as `sent`, as step 7 says,
  even though a restart interrupted it. Reason: the contract says step 7 sets the status.
- A recovery error at startup stops the API, like a migration error. Reason: consistency with
  the existing lifespan; a half-swept database would leave campaigns stuck in `sending`.
- `{name}` uses the company name. Reason: D3; a client has no person field.
- `\r\n` in plain content becomes one `<br>`. Reason: a textarea posts `\r\n`, and two breaks
  per line would double the spacing.
- The task does not rely on the request's session being closed (FastAPI 0.143 may close it
  after background tasks). Reason: the task uses its own session and never shares one.
- backend.md AC 9's "a sender that raises mid-campaign" is split in two (AC 9 here): a raising
  `send` fails only its recipient, because `send_many` (job 017) already turns it into a result;
  the "remaining pending → failed" path is for errors outside one send. Reason: `send_many`'s
  existing contract.
- The fake-sender tests use the `create_app(email_sender_factory=…)` injection already used by
  `tests/test_smtp_test_api.py`, not monkeypatching. Reason: reuse the existing pattern.
