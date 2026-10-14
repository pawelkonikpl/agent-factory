# Email Sender HTTP contract

The source of truth between `web/` and `api/`. It describes the old version's behaviour
**[PARITY]** with its additions **[NEW]**, fixes **[FIX]** and the changes for this repo
**[ADAPT]** (tags as in `README.md`). Auth is the BFF's and Keycloak's (`README.md` §3.1). An
item that changes this contract updates this file in the same job.

## 0. Conventions

- **Base path [ADAPT].** The API serves every route below at its root
  (`http://localhost:8001/categories/` and so on); the source's `/api/v1` prefix is dropped
  (D13). The SPA calls the same paths with an `/api` prefix (`/api/categories/`), and the BFF
  proxy forwards `/api/<path>` to the API as `/<path>`, adding the access token. OpenAPI docs
  (`/docs`, `/redoc`, `/openapi.json`) are on the API directly; they don't work through the BFF.
- **Auth [ADAPT].** Every endpoint below requires an access token for `demo-api`
  (`PrincipalDep`). The BFF attaches it from the session; the browser never sees it. Without
  a valid token the API answers `401 {"detail": "Invalid or missing access token"}` (the
  existing handler). Through the BFF the SPA can also get `401 {"detail": "Not authenticated"}`
  (no session), `403 {"detail": "CSRF check failed"}` (no `X-CSRF` header) and `502` (the API
  is down or took longer than the BFF's 10 s timeout).
- **JSON is camelCase** both ways (`BaseSchema`); the API also accepts snake_case input.
  **Query parameters are snake_case**: `campaign_id`, `client_id`, `include_deleted`,
  `max_concurrent`, `from_date`, `to_date`, `has_error`, `skip`, `limit`, `search`, `status`.
- Dates are ISO 8601 with a UTC offset (every stored date is timezone-aware). Every ID is an
  `int`.
- **Trailing slashes.** Collections end with `/` (`GET /clients/`, `POST /campaigns/`);
  resources by ID don't (`/clients/5`). The stats and failed lists keep theirs:
  `/emails/stats/`, `/emails/failed/`. [ADAPT] The SPA calls these exact paths: FastAPI answers a
  slash mismatch with a `307` redirect, and the BFF doesn't forward `Location`, so the call
  would fail.
- **Errors.**
  - Domain errors: `{ "detail": "<English message>" }`, `400` (business rule or conflict) or
    `404` (missing resource).
  - Pydantic validation: `422 { "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }`.
    A message raised by a field validator arrives in `msg` with Pydantic's `Value error, `
    prefix.
  - [FIX W-23] Typed domain errors (`NotFoundError` → 404, `ConflictError` and
    `BusinessRuleError` → 400) mapped by one handler; nothing matches exception text.
  - The SPA shows `detail` (or `message`) in its global error snackbar unless the screen shows
    the error itself.
- **Pagination [ADAPT].** Paginated lists take `skip` (default 0, at least 0) and `limit`
  (default 100, 1 to 1000; D28) and answer `200 Page<T>`: `{ "items": [...], "total": N }`,
  where `total` counts the rows after filters and before `skip`/`limit`. This replaces the
  source's X-Total-Count header and its CORS `expose_headers`, both dropped (D13).
- **Deleting** is a soft delete. It answers `204`, except `DELETE /emails/{id}`, which answers
  `200 {"message": ...}`.

## 1. Enums

Values on the wire are lowercase.

| Enum | Values |
|---|---|
| `CampaignStatus` | `draft`, `sending` **[ADAPT]**, `sent`, `failed`, `scheduled` |
| `RecipientStatus` | `pending`, `sent`, `failed`, `bounced` |
| `EmailStatus` | `pending`, `sending`, `sent`, `failed`, `bounced`, `rejected`, `deferred` |

`delivered` is **not** a status (the old frontend counted it); use `deliveredAt != null`.
`sending` on a campaign means its background send is running (§4). Nothing sets `scheduled`
yet (D6), but the value stays valid.

## 2. Schemas

### Page<T> [ADAPT]

`{ items: T[], total: number }`.

### CategorySchema

`{ id, name, createdAt, updatedAt }`

### CategoryCreateSchema / CategoryUpdateSchema

`{ name: string }`: trimmed; not empty; at most 64 characters. Messages:
"Category name cannot be empty", "Category name cannot exceed 64 characters".

### ClientSchema

```
{ id, companyName, primaryEmail, additionalEmails: string|null, phoneNumber: string|null,
  address: string|null, isActive: boolean, notes: string|null, createdAt, updatedAt,
  categories: [ { id, name, createdAt, updatedAt } ] }
```

`additionalEmails` is one text with comma-separated addresses.

### ClientCreateSchema / ClientUpdateSchema

```
{ companyName: string,            // trimmed, not empty, at most 128
  primaryEmail: EmailStr,
  additionalEmails?: string|null, phoneNumber?: string|null, address?: string|null,
  isActive?: boolean = true, notes?: string|null,
  categoryIds?: number[] = [] }
```

Messages: "Company name cannot be empty", "Company name cannot exceed 128 characters".
Update has the same shape and is a **full replacement** [PARITY]: an omitted optional field
becomes `null` (or `true` for `isActive`, `[]` for `categoryIds`). [FIX W-01] The SPA always
sends every field.

### ClientBulkCreateSchema / ClientBulkResultSchema [NEW]

Request `{ clients: object[] }`, 1 to 1000 rows; each row is validated on its own as a
`ClientCreateSchema`. Response `{ success: number, failed: number, errors: [ { row: number,
message: string } ] }`, `row` counted from 1.

### CampaignRecipientSchema

`{ id, clientId, clientName, clientEmail, status: RecipientStatus, sentAt: datetime|null, error: string|null }`

### CampaignStatsSchema

```
{ total, sent, failed, pending, bounced,
  progressPercentage: number,   // (sent+failed)/total*100, 2 decimal places, 0 when total = 0
  successRate: number }         // sent/total*100, 2 decimal places, 0 when total = 0
```

Computed from the campaign's **active** (not deleted) recipients. While a campaign is
`sending`, these numbers are its progress (§4).

### CampaignSchema

```
{ id, name, subject, content, status: CampaignStatus, sentAt: datetime|null,
  scheduledFor: datetime|null, createdAt, updatedAt,
  recipients: CampaignRecipientSchema[], stats: CampaignStatsSchema|null }
```

### CampaignCreateSchema

```
{ name: string,       // trimmed, not empty, at most 255
  subject: string,    // trimmed, not empty, at most 500
  content: string,    // not empty after trimming (the content itself is NOT trimmed)
  recipientIds?: number[] = [],   // client IDs
  scheduledFor?: datetime|null }
```

Messages: "Campaign name cannot be empty", "Campaign name cannot exceed 255 characters",
"Email subject cannot be empty", "Email subject cannot exceed 500 characters",
"Email content cannot be empty".

### CampaignUpdateSchema

Every field optional (`name, subject, content, recipientIds, scheduledFor`), with the same
validation when a field is given ([FIX] the old update lacked the 500 limit on `subject`). An
omitted field, or `null`, means "don't change", except `scheduledFor`: [FIX] an explicit
`"scheduledFor": null` clears it (the API tells "absent" from "null" with `model_fields_set`).

### CampaignResendSchema

`{ recipientIds?: number[]|null }`: IDs of **`CampaignRecipient` rows**, not clients. Absent or
`null` means all failed recipients.

### SendCampaignResultSchema (dropped)

Dropped with the synchronous send [ADAPT, D17]. Send and resend answer `202 CampaignSchema`;
the progress and the outcome are the campaign's `status` and `stats`, read with
`GET /campaigns/{id}`.

### EmailSchema

```
{ id, campaignId, clientId, recipientEmail, clientName: string|null, campaignName: string|null,
  subject, content, status: EmailStatus,
  sentAt, deliveredAt, openedAt, clickedAt, bouncedAt: datetime|null,
  errorMessage: string|null, errorCode: string|null, retryCount: number = 0, maxRetries: number = 3,
  smtpMessageId: string|null, smtpResponse: string|null, createdAt, updatedAt }
```

[FIX W-17, D25] `subject` and `content` are the snapshot stored with the email (`emails.subject`
and `emails.body`), not the campaign's current text.

### EmailUpdateSchema

Every field optional: `status (string), sentAt, deliveredAt, openedAt, clickedAt, bouncedAt,
errorMessage, errorCode, smtpMessageId, smtpResponse`. `null` means "don't change". `status`
must be an `EmailStatus` value, else `400 "Invalid email status: {value}"`.

### EmailStatsSchema

```
{ total, pending, sending, sent, failed, bounced, rejected, deferred,
  delivered,       // rows with deliveredAt != null
  opened,          // openedAt != null
  clicked,         // clickedAt != null
  deliveryRate,    // delivered/total*100
  openRate,        // opened/sent*100
  clickRate,       // clicked/sent*100
  bounceRate }     // bounced/total*100     (each rate: 2 decimal places, 0.0 when the denominator is 0)
```

Counted over non-deleted emails, filtered by `campaign_id` when given.

### SmtpConfigResponseSchema

`{ smtpServer: string|null, smtpPort: number|null, smtpUser: string|null, smtpUseTls: boolean|null }`.
**The password is never returned.**

### SmtpConfigUpdateSchema

Every field optional: `smtpServer` (trimmed, not empty), `smtpPort` (1 to 65535), `smtpUser`
(trimmed, not empty; [FIX] it doesn't have to be an email address), `smtpPassword` (a non-empty
string; `null` means "don't change"), `smtpUseTls` (bool). A field can't be cleared [PARITY].

### SmtpTestRequestSchema / SmtpTestResultSchema [NEW]

Request `{ recipient: EmailStr }`. Response `{ success: true, message: string }`.

### MessageSchema

`{ message: string }`

---

## 3. Endpoints

Every endpoint requires the access token (§0). Paths are the API's; the SPA prefixes `/api`.

### 3.1 Categories: `/categories`

| Method and path | Description | Response |
|---|---|---|
| `GET /categories/?include_deleted=false` | list; without deleted ones by default; ordered by `id` | `200 CategorySchema[]` |
| `POST /categories/` | create | `201 CategorySchema`; `400` when the name is taken by a non-deleted category: "Category with name '{name}' already exists" |
| `PUT /categories/{id}` | rename | `200 CategorySchema`; `404` "Category {id} not found"; `400` duplicate |
| `DELETE /categories/{id}` | remove its links to clients, then soft delete | `204`; `404` |

[FIX W-04] Every endpoint requires the token. No pagination, so the list is a plain array.

### 3.2 Clients: `/clients`

| Method and path | Description | Response |
|---|---|---|
| `GET /clients/?skip&limit&search` | non-deleted clients; **[NEW]** `search` = case-insensitive match on `companyName`, `primaryEmail`, `phoneNumber` and the name of a linked category; **[NEW]** stable order (`companyName`, `id`) | `200 Page<ClientSchema>` |
| `POST /clients/` | create; `primaryEmail` unique among non-deleted clients | `201 ClientSchema`; `400` "Client with email '{email}' already exists" |
| `GET /clients/{id}` | | `200 ClientSchema`; `404` "Client {id} not found" |
| `PUT /clients/{id}` | full replacement of the fields and categories; uniqueness excluding itself | `200 ClientSchema`; `404`; `400` |
| `DELETE /clients/{id}` | soft delete and drop its category links | `204`; `404` |
| **[NEW]** `POST /clients/bulk` | body `ClientBulkCreateSchema`; row by row, a failing row doesn't stop the others; a row's email must be unique against the database and the earlier rows of the batch | `200 ClientBulkResultSchema`; `422` for more than 1000 rows |

[FIX W-26] `categoryIds` must exist and not be deleted, else `400` "Categories not found: 3, 7".
Duplicate IDs are ignored.

### 3.3 Campaigns: `/campaigns`

| Method and path | Description | Response |
|---|---|---|
| `GET /campaigns/?skip&limit&search` | non-deleted campaigns; `search` = case-insensitive match on `name`, `subject`, `content`; order `createdAt desc, id desc` | `200 Page<CampaignSchema>` |
| `POST /campaigns/` | creates a `draft`; sets the recipients from `recipientIds` | `201 CampaignSchema`; `400` |
| `GET /campaigns/{id}` | also what the SPA polls while `sending` | `200 CampaignSchema`; `404` "Campaign {id} not found" |
| `PUT /campaigns/{id}` | **`draft` only**: "Only draft campaigns can be modified" (400); a `sending` campaign gives "Campaign is being sent" (400) instead [ADAPT]; partial update; `recipientIds` REPLACES the recipients | `200 CampaignSchema`; `404`; `400` |
| `DELETE /campaigns/{id}` | soft delete of the campaign and its recipients, any status except `sending`: "Campaign is being sent" (400) [ADAPT] | `204`; `404`; `400` |
| `POST /campaigns/{id}/recipients` | **the body is a bare array** `[1,2,3]` (client IDs); `draft` only ("Only draft campaigns can have recipients added"); skips clients already on the campaign | `201 CampaignSchema`; `404`; `400` |
| `POST /campaigns/{id}/send?max_concurrent=10` | starts the background send, rules in §4 | `202 CampaignSchema` with `status: "sending"` [ADAPT]; `400`; `404`; `422` |
| `POST /campaigns/{id}/resend?max_concurrent=10` | optional body `CampaignResendSchema`; the same flow as `send`, with the chosen recipients | `202 CampaignSchema` with `status: "sending"` [ADAPT]; `400`; `404`; `422` |

[FIX W-26] `recipientIds` (create, update, add): duplicates are dropped; every ID must be a
non-deleted client, else `400` "Clients not found: 3, 7".

`max_concurrent` is 1 to 50 (`422` outside); without it the API uses
`API_EMAIL_MAX_CONCURRENT` (D10).

### 3.4 Emails (the log): `/emails`

| Method and path | Description | Response |
|---|---|---|
| `GET /emails/?skip&limit&campaign_id&client_id&status&from_date&to_date&has_error&search` | filters; `from_date`/`to_date` on `createdAt`; `has_error` = `errorMessage is [not] null`; order `createdAt desc, id desc`; **[NEW]** `search` on `recipientEmail`, the client name, the campaign name and the subject | `200 Page<EmailSchema>` |
| `GET /emails/stats/?campaign_id` | stats from SQL aggregates | `200 EmailStatsSchema` |
| `GET /emails/failed/?campaign_id` | only `status = failed` | `200 EmailSchema[]` |
| `GET /emails/campaign/{campaign_id}?skip&limit` | a campaign's emails, `createdAt desc` | `200 EmailSchema[]` (D27) |
| `GET /emails/client/{client_id}?skip&limit` | a client's emails, `createdAt desc` | `200 EmailSchema[]` (D27) |
| `GET /emails/{id}` | | `200 EmailSchema`; `404` "Email {id} not found" |
| `PUT /emails/{id}` | manual update (`EmailUpdateSchema`) | `200 EmailSchema`; `404`; `400` |
| `POST /emails/{id}/mark-opened` · `/mark-clicked` | set `openedAt` / `clickedAt` to now | `200 EmailSchema`; `404` |
| `DELETE /emails/{id}` | soft delete | `200 { "message": "Email deleted successfully" }`; `404` |
| `POST /emails/{id}/resend` | send again, synchronously, to `recipientEmail` with the stored `subject`/`body` and the **calling user's** SMTP settings; updates the same row (`status` sent or failed, `sentAt` on success only, `smtpMessageId`, `errorMessage`, `retryCount + 1`); answers within 8 s (§5) | `200 EmailSchema`; `404`; `400` "SMTP configuration not found. Please configure SMTP settings first." (the source's table shortens this message) |

`status` must be an `EmailStatus` value (`422` otherwise). Route order: `/stats/`, `/failed/`,
`/campaign/…` and `/client/…` are registered **before** `/{email_id}`.

### 3.5 SMTP settings: `/config`

| Method and path | Description | Response |
|---|---|---|
| `GET /config/smtp` | the calling user's settings; all `null` when none are saved | `200 SmtpConfigResponseSchema` |
| `PUT /config/smtp` | partial upsert for the calling user; the password is encrypted before it is stored | `200 { "message": "Configuration updated successfully" }`; `422` |
| **[NEW]** `POST /config/smtp/test` | body `SmtpTestRequestSchema`; sends a test message with the saved settings; answers within 8 s (§5) [ADAPT: the source's 30 s is dropped] | `200 { "success": true, "message": "Test email sent to {recipient}" }`; `400` with `detail` = "SMTP configuration not found. Please configure SMTP settings first." or the SMTP error (§5) |

"The calling user" is `Principal.subject`; each user has their own settings.

---

## 4. Campaign send rules (`send` / `resend`)

[ADAPT, D17] The request checks and starts; a background task sends. Checks 1 to 4 run in the
request, in this order and with these `400` messages (English, in `detail`):

1. The campaign exists and isn't deleted (`404` "Campaign {id} not found"). Its status is
   `draft` or `failed`, else `"Campaign cannot be sent — current status: {status}"` (the SPA
   looks for the substring `current status: sent`). A `sending` campaign therefore fails both
   endpoints with `"Campaign cannot be sent — current status: sending"`.
2. Choosing the recipients:
   - `draft`: every `pending` recipient. Given `recipientIds` (resend) →
     `"Only failed campaigns can be resent"`.
   - `failed`: the `failed` recipients, which step 5 resets to `pending` (status,
     `error = null`, `sentAt = null`):
     - without `recipientIds`, every failed recipient (this is also what `send` on a failed
       campaign does);
     - with `recipientIds`, every ID must be a recipient of this campaign
       (`"Recipients not found in campaign: 3, 5"`) and be `failed`
       (`"Can only resend failed recipients: 4"`); an empty list chooses nobody.
3. Nobody to send to → `"Campaign has no pending recipients"`.
4. The calling user has no saved `smtpServer` →
   `"SMTP configuration not found. Please configure SMTP settings first."` Unset values default
   to port 587 and `useTls` true (TLS rules in §5).
5. **Start.** In one transaction: `UPDATE campaigns SET status = 'sending' WHERE id = :id AND
   status IN ('draft', 'failed') AND is_deleted = false`. When it changes no row (another
   request won the race), answer the same 400 as check 1 with the status now stored. Otherwise
   reset the chosen failed recipients to `pending`, commit, start the background task and
   answer **`202 CampaignSchema`** with `status: "sending"`. The task gets the user's SMTP
   settings from the request; it doesn't need the principal.
6. **The background task** uses its own database session and sends to the `pending`
   recipients with `asyncio.Semaphore(max_concurrent)`. For each recipient:
   - [FIX W-14] a client that is inactive or deleted → the recipient becomes `failed` with
     `error = "Client is inactive"`, with no SMTP attempt and no `Email` row;
   - [FIX W-17] when the recipient's `Email` row already has `retryCount >= maxRetries` → the
     recipient becomes `failed` with `error = "Maximum retries exceeded"`, with no attempt;
   - the address is `client.primaryEmail` (never `additionalEmails` [PARITY]); the subject is
     `campaign.subject`; the body is `campaign.content`, turned into HTML when it has no tags
     (D4) and with `{name}`, `{email}` and `{company}` substituted (D3);
   - success → the recipient is `sent` (`sentAt`, `error = null`) and its `Email` row is
     `sent` with `sentAt`, `smtpMessageId` and `errorMessage = null`;
   - failure → the recipient is `failed` with `error`, and its `Email` row is `failed` with
     `errorMessage`;
   - [FIX W-17] the first attempt creates the `Email` row for the (campaign, client) pair; a
     later attempt updates that row and adds 1 to `retryCount`. Each attempt stores the
     `subject` and `body` it sent;
   - the recipient's result and its `Email` row are committed as soon as that recipient
     finishes, so `stats` show the progress.
7. **The end.** If any recipient of the campaign is still `failed`, the campaign becomes
   `failed`; otherwise `sent` with `sentAt = now`. If the task fails with an unexpected error
   (anything that isn't one recipient's SMTP failure), every recipient still `pending` becomes
   `failed` with `"Unexpected error: …"` and the campaign becomes `failed`.
8. **Restart.** At startup, campaigns left in `sending` by a restart get the same treatment:
   their `pending` recipients become `failed` with `"Sending interrupted"`, then step 7 sets
   the status.

A `sending` campaign also refuses `PUT` and `DELETE` with `400 "Campaign is being sent"`.

**How the SPA reads the outcome.** After the `202` it polls `GET /campaigns/{id}` while the
status is `sending`. With `successCount = stats.sent` and `failedCount = stats.failed` of the
final campaign: `failedCount == 0` → success; `successCount > 0` → warning "Wysłano częściowo"; otherwise an error.

## 5. SMTP behaviour

- **TLS [FIX W-13].** `smtpUseTls` true and port 465 → implicit TLS; true and any other port →
  STARTTLS; false → a plain connection, with STARTTLS explicitly off (smtp4dev). The client logs
  in only when both `smtpUser` and `smtpPassword` are set.
- **Timeout [ADAPT, D18].** 8 s per email, connect included. `POST /config/smtp/test` and
  `POST /emails/{id}/resend` send one email inside the request, so they answer within the BFF's
  10 s.
- **The message.** `From` = `smtpUser`, `To`, `Subject` (UTF-8 encoded), `Date`, [FIX W-12]
  `Message-ID`; one `text/html; charset=utf-8` part.
- **Error messages**, stored in the recipient's `error` and the email's `errorMessage`, and used
  as the `detail` of the synchronous endpoints: `SMTP Authentication failed: …`,
  `Recipient refused: …`, `SMTP error: …` (a timeout gives `SMTP error: timed out after 8 s`),
  `Unexpected error: …`.
