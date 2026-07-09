---
name: hubspot-email-stats
description: Retrieve and analyse HubSpot marketing email performance and content via the Marketing Emails API (v2026-03). Use this whenever the user asks about email performance, open/click/bounce rates, engagement over time, campaign email stats, subject-line or body-copy analysis, or which email content performs best — even if they don't name the API. Covers aggregated statistics (/statistics/list), time-bucketed histograms (/statistics/histogram), and email details/content (GET /{emailId}), authenticated with HUBSPOT_SERVICE_KEY from the project .env.
---

# HubSpot Marketing Email Statistics

Fetch marketing email performance data and content from HubSpot and turn it
into analysis: totals, trends, per-campaign comparisons, and — the flagship —
correlating email *content* with performance.

## Authentication

The user's project `.env` contains `HUBSPOT_SERVICE_KEY` (a private app
token with the `content` scope). The bundled script loads it automatically —
never print, echo, or commit this key. No key → walk the user through the
plugin README setup. 401/403 → have the user check the key and its scopes;
don't retry.

## Fetching data

Use the bundled script — never hand-write API calls. It lives at
`scripts/email_stats.py` under this skill's base directory (`$SKILL_DIR`
below); run it from the user's project root so it finds `.env`:

```bash
# Totals + per-campaign breakdown ("how did our emails do?")
python3 "$SKILL_DIR/scripts/email_stats.py" aggregate --start 2026-06-01 --end 2026-06-30 --summary

# Time-bucketed trend ("how is it trending?") — auto-paginates
python3 "$SKILL_DIR/scripts/email_stats.py" histogram --interval DAY --start 2026-06-01 --end 2026-06-30 --summary

# Per-email content + lifetime stats as JSONL ("what does the copy do?")
python3 "$SKILL_DIR/scripts/email_stats.py" content --ids-file ids.json --out emails.jsonl --summary
```

Non-negotiable operational rules (learned against the live API):

- Always pass `--start`/`--end` — omitting them returns 400.
- Wide ranges 500/504 on HubSpot's side: chunk into ≤ 6-month windows and
  merge.
- Dedupe the `emails` array before counting — it holds ~one entry per send.
- Match histogram interval to range (DAY for a month, WEEK/MONTH for longer).

## Going deeper — read these when the task calls for it

| Read | When |
|---|---|
| [references/api-details.md](references/api-details.md) | You need exact parameters, response schemas, or hit an API error/quirk not covered above |
| [references/content-analysis.md](references/content-analysis.md) | The user asks which emails/content/subject lines perform better — the full dataset → semantic tagging → honest correlation workflow |
| [references/reporting.md](references/reporting.md) | Before presenting any analysis: chat-answer guidelines, and how to generate the self-contained HTML report from `assets/report_template.html` |

## Analysis principles (always apply)

- Rates on **delivered**, not sent; bounce rate on sent. Lead with CTR —
  Apple Mail Privacy Protection inflates opens.
- Never compare across `subcategory` (automated vs batch) without saying so;
  never report a rate on < 100 delivered without flagging it.
- Show counts alongside rates; frame content findings as "worth A/B
  testing", not causal facts.

## Scope & read-only guarantee

Marketing emails only — 1:1 sales emails live in the Engagements API. Stats
match the in-app *Performance* page. Statistics endpoints return bare email
IDs; the `content` subcommand resolves names, subjects, and body copy.

This skill is strictly **read-only**: every call is a GET. Never issue
POST/PUT/PATCH/DELETE against the HubSpot API, even though the token's
`content` scope technically allows it. The plugin's PreToolUse hook enforces
this — if it blocks a command, use the bundled script instead of working
around the guard.
