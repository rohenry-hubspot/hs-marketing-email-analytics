# HubSpot Marketing Email API — endpoint reference

API version: `2026-03`. Base: `https://api.hubapi.com/marketing/emails/2026-03`

Authentication: `Authorization: Bearer <token>` where the token is a private
app access token (here: `HUBSPOT_SERVICE_KEY` from the project `.env`).
Required scope: `content` (alternatively `marketing-email` or
`transactional-email` per the Marketing Emails API guide).

The API host defaults to `https://api.hubapi.com` and can be overridden with
an `API_ROOT` value in the environment or project `.env` (e.g. to point at a
proxy or sandbox host). The bundled script picks this up automatically —
see `scripts/email_stats.py`.

Note: this API only covers **marketing** emails. Sales emails sent from
contact records are not included (those live in the Engagements API).
Statistics match what the HubSpot app shows on a sent email's *Performance*
page.

Docs:
- Guide: https://developers.hubspot.com/docs/api-reference/latest/marketing/marketing-emails/guide
- Histogram: https://developers.hubspot.com/docs/api-reference/latest/marketing/marketing-emails/statistics/get-histogram
- Aggregated: https://developers.hubspot.com/docs/api-reference/latest/marketing/marketing-emails/statistics/get-statistics
- Email details: https://developers.hubspot.com/docs/api-reference/latest/marketing/marketing-emails/emails/get-email

## GET /{emailId} — email details (name, subject, body content)

Path parameter: `emailId` (required). Useful query parameters:

| Param | Type | Notes |
|---|---|---|
| `includeStats` | boolean | Attach lifetime `stats` (EmailStatisticsData) to the response — content + performance in one call. |
| `includedProperties` | array of strings | Restrict returned properties. |
| `marketingCampaignNames` | boolean | Include campaign names. |
| `variantStats` | boolean | Include A/B variant statistics. |
| `archived` | boolean | Fetch archived emails. |

Response (`PublicEmail`), key fields for content analysis:

- `name` — internal display name
- `subject` — the subject line recipients saw
- `content.plainTextVersion` — plain-text body when populated (often empty)
- `content.widgets` / `widgetContainers` / `flexAreas` — the body as
  structured components; copy lives in string fields like `html`, `text`,
  `value` (the bundled script's `content` mode extracts and strips these)
- `state` (DRAFT / PUBLISHED / ...), `publishDate`, `subcategory`
  (`batch`, `automated`, ...), `from`, `to`
- `stats` — only when `includeStats=true`

Quirks observed live:
- Some email IDs returned by `/statistics/list` **404 here** (deleted
  emails). Expect and skip them; the bundled script warns and continues.
- `stats.ratios` in this response are **percentages (0–100)**, e.g.
  `openratio: 21.374` — unlike the fraction-style ratios elsewhere. Check
  magnitude before formatting.
- Body copy may contain personalization tokens like
  `{{ contact.firstname }}` — treat them as placeholders, not content.

## GET /statistics/list — aggregated statistics

Query parameters (all optional):

| Param | Type | Notes |
|---|---|---|
| `emailIds` | array of int64 | Repeat the param for each ID (`emailIds=1&emailIds=2`). Only include statistics of emails with these IDs. |
| `startTimestamp` | ISO8601 date-time | Start of the time range. |
| `endTimestamp` | ISO8601 date-time | End of the time range. |
| `property` | string | Which email properties to return; all by default. |

Response (`AggregateEmailStatistics`):

```json
{
  "aggregate":            { ...EmailStatisticsData },   // overall totals
  "campaignAggregations": { "<campaignId>": { ...EmailStatisticsData } },
  "emails":               [ 12345, 67890 ]              // email IDs sent in the span
}
```

## GET /statistics/histogram — time-bucketed statistics

Query parameters (all optional):

| Param | Type | Notes |
|---|---|---|
| `emailIds` | array of int64 | Repeat the param for each ID. |
| `startTimestamp` | ISO8601 date-time | Start of the time span. |
| `endTimestamp` | ISO8601 date-time | End of the time span. |
| `interval` | enum | `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAY`, `HOUR`, `QUARTER_HOUR`, `MINUTE`, `SECOND` |

Response: paged collection. Each result is one time bucket:

```json
{
  "paging": { "next": { "after": "...", "link": "..." } },
  "results": [
    {
      "interval": { "start": "2026-06-01T00:00:00Z", "end": "2026-06-01T23:59:59Z" },
      "aggregations": { ...EmailStatisticsData }
    }
  ],
  "total": 30
}
```

Follow `paging.next.after` (pass it back as the `after` query param) until it
is absent. The bundled script does this automatically.

## EmailStatisticsData

The stats object used by both endpoints:

- `counters` — int64 event counts, e.g. `sent`, `delivered`, `open`, `click`,
  `bounce`, `unsubscribed`, `spamreport`, `dropped`, `notsent`, `reply`.
- `ratios` — precomputed rates, e.g. `openratio`, `clickratio`,
  `clickthroughratio`, `deliveredratio`, `bounceratio`, `unsubscribedratio`.
  Values are fractions (0–1) unless observed otherwise.
- `deviceBreakdown` — opens/clicks split by device type
  (mobile / desktop / etc.), nested objects of int64 counts.
- `qualifierStats` — detail on `bounced` and `dropped` messages (reasons /
  qualifiers).

Exact key sets vary by portal and time range — always inspect the actual
response rather than assuming a key exists; missing keys mean zero events of
that type.

## Errors

Standard HubSpot error object: `category`, `message`, `correlationId`,
optional `context` / `errors`. Common causes:

- `401` — bad or missing token: check `.env` `HUBSPOT_SERVICE_KEY`.
- `403` — token lacks the `content` scope.
- `429` — rate limited; back off and retry.
