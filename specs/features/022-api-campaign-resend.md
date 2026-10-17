# Campaign resend in the background

> Feature: Add `POST /campaigns/{id}/resend` for all or chosen failed recipients, through the same background flow, as specified in `specs/email-sender/backend.md` API-12 (covers B8, resend part)

## Context

This is roadmap item API-12 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-12: Campaign resend in the background", plus the "Rules for
every item" at the top of that file. The wire rules are in `specs/email-sender/api-contract.md`:
"CampaignResendSchema" (§2: `{ recipientIds?: number[]|null }`, IDs of `CampaignRecipient` rows,
absent or `null` meaning all failed recipients), the `resend` row of §3.3 (`202 CampaignSchema`,
400, 404, 422) and §4 check 2 (the resend messages). This spec restates them; where they differ,
this spec wins.

Job 020 (`specs/features/020-api-campaign-send.md`, API-11) built the whole flow this item
reuses. In `api/`:

- `app/services/campaign_sender.py`: `CampaignSender.start(campaign_id, user_sub,
  retry_recipient_ids=None)` already takes the parameter but ignores it. It runs §4 checks 1 to 4
  (404, "Campaign cannot be sent — current status: {status}", "Campaign has no pending
  recipients", "SMTP configuration not found. Please configure SMTP settings first.") and then
  `CampaignRepository.start_sending(campaign, reset)`, the conditional `UPDATE ... SET status =
  'sending'` plus the reset of the `reset` recipients to `pending`, in one commit. Today a
  `draft` chooses its `pending` recipients (reset nobody) and a `failed` campaign chooses and
  resets every non-deleted `failed` recipient. `run(campaign_id, smtp_config, max_concurrent)`
  sends to the `pending` recipients only, so recipients not reset stay `failed`, and `_finish`
  (§4 step 7) then ends the campaign `failed` again. Helpers `_active` (non-deleted recipients)
  and `_pending` exist.
- `app/repositories/campaign_repository.py`: `start_sending` (lines ~149-174).
- `app/api/campaigns.py`: `send_campaign`, `POST /{campaign_id}/send`, with `PrincipalDep`,
  `CampaignSenderDep`, `CampaignServiceDep`, `EmailMaxConcurrentDep`, `BackgroundTasks` and
  `max_concurrent: int | None = Query(None, ge=1, le=50)`; answers 202 `CampaignSchema`. No
  resend route.
- `app/schemas/campaigns.py`: campaign schemas on `BaseSchema` (`app/schemas/base.py`, camelCase
  aliases). No `CampaignResendSchema`.
- `app/main.py`: the `DomainError` handler maps `NotFoundError` to 404 and `BusinessRuleError`
  to 400.
- Tests: `tests/test_campaign_sender.py` (service tests with `FakeSenders` from
  `tests/conftest.py`, helpers `create`, `add_client`, `save_smtp`, `stored`,
  `recipient_states`), `tests/test_campaign_send_api.py` (endpoint tests with the `senders` and
  `app` fixtures and helpers `draft_with_recipients`, `get`, `emails`, `send`, `by_email`),
  `tests/test_campaigns_api.py` (the 401 parametrization `test_missing_token_answers_401` and
  the 404 parametrization `test_unknown_campaign_answers_404`, both listing `send`).

No model, migration or setting change is needed.

## Requirements

1. `CampaignResendSchema(BaseSchema)` in `app/schemas/campaigns.py` with one field
   `recipient_ids: list[int] | None = None` (wire name `recipientIds`).
2. `CampaignSender.start` honours `retry_recipient_ids` (§4 check 2), still before changing
   anything and still in the order of checks 1 to 4:
   - `None`: unchanged behaviour (as `send`).
   - Given (a list, empty included) on a `draft` → `BusinessRuleError("Only failed campaigns can
     be resent")`.
   - Given on a `failed` campaign: duplicates are dropped; every ID must be a non-deleted
     recipient of this campaign, else `"Recipients not found in campaign: {ids}"`; then every ID
     must be a `failed` recipient, else `"Can only resend failed recipients: {ids}"`. `{ids}` are
     the offending IDs, ascending, joined with `", "` (for example `3, 5`). The not-found check
     runs before the not-failed check. The chosen and reset recipients are exactly those IDs;
     an empty list chooses nobody, so check 3 answers "Campaign has no pending recipients".
   - All IDs are validated before `start_sending` runs, so a failing check resets no recipient
     and leaves the status as it was. The status checks (404, check 1 for `sending`/`sent`/
     `scheduled`) come first, so they answer the same as for `send`.
3. Router `app/api/campaigns.py`: `POST /campaigns/{campaign_id}/resend`, built like
   `send_campaign`: `status_code=202`, `response_model=CampaignSchema`, `PrincipalDep`,
   `CampaignSenderDep`, `CampaignServiceDep`, `EmailMaxConcurrentDep`, `BackgroundTasks`,
   `max_concurrent: int | None = Query(None, ge=1, le=50)`, and an optional body
   `payload: CampaignResendSchema | None = None`. It calls
   `start(campaign_id, principal.subject, retry_recipient_ids)` with `payload.recipient_ids`
   (or `None` without a body), then adds `sender.run(campaign_id, smtp_config, max_concurrent)`
   as a background task, as `send` does. A request with no body, with `{}` and with
   `{"recipientIds": null}` all mean "every failed recipient".
4. Tests, with the fake sender factory (never real SMTP): service tests in
   `tests/test_campaign_sender.py` for the new `start` branches; endpoint tests (in
   `tests/test_campaign_send_api.py` or a new `tests/test_campaign_resend_api.py`) covering 202,
   every 400, 404, 422 and the chosen-IDs flow; add `resend` to the 401 parametrization and the
   404 parametrization in `tests/test_campaigns_api.py`.
5. `specs/email-sender/api-contract.md` changes only if the implementation disagrees with it.
   `AGENTS.md` needs no change.

## Acceptance criteria

All run in `api/` with PostgreSQL up (`make docker-up` or any run mode); none needs smtp4dev.

1. Resend without a body after a partial failure: a draft with 3 recipients is sent with the
   fake failing one address (campaign `failed`); after clearing the failures, `POST
   /campaigns/{id}/resend` with no body answers 202 with `status: "sending"`, the fake records
   one send (the failed address), and `GET /campaigns/{id}` shows `status: "sent"` with every
   recipient `sent`; `GET /emails/campaign/{id}` still lists 3 rows, the retried one with
   `retryCount` 1. The same holds with body `{}`. Endpoint test.
2. Resend with chosen IDs: a campaign with 2 failed recipients, resent with `{"recipientIds":
   [<one of their CampaignRecipient ids>]}`: the fake records one send, to that recipient's
   client; that recipient ends `sent`, the other stays `failed` with its old `error`, and the
   campaign ends `failed`. This also shows the router passes the chosen IDs to the service.
   Endpoint test.
3. 400 with the exact `detail`, each leaving the campaign's status and recipients unchanged and
   the fake uncalled (endpoint tests):
   - a draft with `{"recipientIds": [<its recipient id>]}` → "Only failed campaigns can be
     resent";
   - a failed campaign with two unknown IDs (for example a deleted recipient's ID and 999999,
     or another campaign's recipient IDs) → "Recipients not found in campaign: a, b" with the
     IDs ascending;
   - a failed campaign with the ID of a `sent` recipient → "Can only resend failed recipients:
     {id}", and no failed recipient was reset (a valid failed ID in the same list stays
     `failed`);
   - a failed campaign with `{"recipientIds": []}` → "Campaign has no pending recipients";
   - a campaign set to `sending` → "Campaign cannot be sent — current status: sending"; one set
     to `sent` → "… current status: sent";
   - without SMTP settings → "SMTP configuration not found. Please configure SMTP settings
     first.".
4. 404 `{"detail": "Campaign 999999 not found"}` for `POST /campaigns/999999/resend` (and for a
   deleted campaign); 422 for `?max_concurrent=0` and `?max_concurrent=51`; 401 without a
   token. Endpoint tests, including the `resend` entries in `tests/test_campaigns_api.py`.
5. Service test in `tests/test_campaign_sender.py`: `start(id, "alice", [a, a])` on a failed
   campaign with failed recipients `a` and `b` moves it to `sending` and resets only `a` to
   `pending` (`error` and `sent_at` cleared); `b` stays `failed`.
6. `cd api && uv run pytest && uv run ruff check . && uv run mypy app tests && uv run alembic
   check` pass; `git diff --stat main -- bff web` is empty.

## Out of scope

- `POST /emails/{id}/resend` (API-13).
- Any change to `run`, `send_many`, `recover_interrupted`, the `Email` row rules or the
  `max_retries` handling: the resend reuses them as they are.
- Accepting client IDs in `recipientIds`, or resending `sent` recipients.
- Any model, migration, setting or `.env.example` change.
- Any `web/` or `bff/` change (the SPA's resend is UI-10, Phase 5).

## Assumptions

- Duplicate IDs in `recipientIds` are dropped rather than rejected. Reason: the contract drops
  duplicates for every other `recipientIds` (W-26), and choosing a recipient twice means the
  same thing.
- The offending IDs in the two messages are listed ascending, deduplicated. Reason: a stable,
  testable order; the contract's examples ("3, 5") are ascending.
- A soft-deleted recipient's ID counts as "not found in campaign". Reason: deleted recipients
  are invisible everywhere else (`get` skips them, `start` never chooses them).
- When some IDs are unknown and others not failed, only the "not found" message is returned.
  Reason: the contract lists that check first; one 400 carries one message.
- On a draft, an empty list also answers "Only failed campaigns can be resent". Reason: the
  contract's draft rule fires whenever `recipientIds` is given; only the failed-campaign rule
  mentions an empty list.
- `POST /resend` on a draft without IDs sends the draft like `send`. Reason: backend.md says
  "Without IDs it behaves like `send`".
- backend.md AC 4's "old router test" is met by the endpoint test of AC 2 rather than a mock of
  the service. Reason: the end-to-end test proves the IDs reach `start`, and the repo's tests use
  the real service with a fake sender, not mocks.
