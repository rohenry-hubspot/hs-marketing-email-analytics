# HubSpot Marketing Email Analytics

A Claude Code / Cowork plugin for HubSpot marketing email performance —
built to answer not just *how* emails performed, but *why*: which subject
lines and body copy actually drive opens and clicks. It wraps the Marketing
Emails API (v2026-03):

- **Aggregated statistics** (`/statistics/list`) — overall totals, per-campaign
  breakdowns, and the list of email IDs sent in a time range.
- **Statistics histogram** (`/statistics/histogram`) — time-bucketed metrics
  (year down to second granularity) for trend analysis.
- **Email details** (`GET /{emailId}`) — name, subject, and body copy for a
  given email, the raw material for content analysis.

Ask things like *"how did our emails perform in June?"*, *"show me the daily
open-rate trend for Q2"*, or — the flagship use case — *"which of our emails
perform better, and what do the winners have in common?"* and the bundled
skill fetches the data and produces an honest analysis (rates on delivered,
Apple MPP caveats, small-sample warnings, correlation framed as correlation).

## Installation

```
/plugin marketplace add rohenry-hubspot/hs-marketing-email-analytics
/plugin install hs-marketing-email-analytics@hs-marketing-email-analytics
```

## Setup

The skill authenticates with a HubSpot **private app access token** read from
a `.env` file in your project directory:

1. In HubSpot: **Settings → Integrations → Private Apps → Create app**, and
   grant the **`content`** scope.
2. Copy the access token into your project's `.env`
   (see [.env.example](.env.example)):

   ```
   HUBSPOT_SERVICE_KEY=your-private-app-token-here
   ```

3. Keep `.env` out of version control.

Optional: set `API_ROOT` (env or `.env`) to point the script at a different
host (e.g. a proxy or sandbox) — it defaults to `https://api.hubapi.com`.

## What's inside

| Component | Purpose |
|---|---|
| `skills/hubspot-email-stats/SKILL.md` | Entry point: auth, quick-reference fetch commands, operational rules, and routing to the references below |
| `skills/hubspot-email-stats/scripts/email_stats.py` | Dependency-free Python fetcher (stdlib only): statistics, histograms, and per-email content+stats as JSONL; `.env` loading, retries, pagination |
| `skills/hubspot-email-stats/references/api-details.md` | Full parameter/response schemas for all three endpoints |
| `skills/hubspot-email-stats/references/content-analysis.md` | The dataset → semantic tagging → honest correlation workflow — how to answer "which content performs better?" |
| `skills/hubspot-email-stats/references/reporting.md` | How to present findings: chat-answer guidelines, and generating the HTML report |
| `skills/hubspot-email-stats/assets/report_template.html` | Self-contained HTML report template (KPIs, feature-impact charts, top/bottom emails, insights) — no external assets, light/dark aware |
| `hooks/` | **Read-only guard**: a PreToolUse hook that blocks any write (POST/PUT/PATCH/DELETE) to the HubSpot API and any write-capable HubSpot MCP tool, since the `content` scope technically permits writes |

## Content-vs-performance analysis

Beyond stats retrieval, the skill can answer *"which emails perform better
based on their content?"*: it builds a JSONL dataset (subject + extracted
body text + lifetime stats per email), tags each email with semantic content
features (topic, tone, subject style, CTA strength — Claude does this
directly, in any language), correlates features with click-through rates,
and renders the findings as a shareable single-file HTML report.

## Anatomy: progressive disclosure

The skill is deliberately structured as a textbook example of **progressive
disclosure** — context is loaded in three levels, so simple questions stay
cheap and deep workflows get full detail only when needed:

| Level | What | In context |
|---|---|---|
| 1 | Skill name + description (frontmatter) | Always — this is how Claude decides to trigger the skill |
| 2 | `SKILL.md` body: quick reference, operational rules, and a "read X when Y" routing table | Only when the skill triggers |
| 3a | `references/api-details.md` — full endpoint schemas and quirks | Only when schemas or errors demand it |
| 3b | `references/content-analysis.md` — the semantic tagging + correlation workflow | Only for content-vs-performance analyses |
| 3c | `references/reporting.md` — presentation rules + HTML report generation | Only when presenting results |
| — | `scripts/email_stats.py`, `assets/report_template.html` | Never — executed/copied without entering context |

A "what was June's open rate?" question costs one lean SKILL.md; a full
content study progressively pulls in exactly the two extra references it
needs. This structure is worth walking through in trainings: it's the
difference between a skill that scales and a prompt dump.

## Read-only guarantee

The bundled script only ever issues GET requests, and the plugin ships a
deterministic PreToolUse hook that blocks — before execution — any shell
command that would send a write to `hubapi.com` (method overrides, request
bodies, or unvetted code touching the API) as well as HubSpot MCP tools with
write semantics. Your portal cannot be modified by this plugin.

## API notes & known quirks

- `startTimestamp` / `endTimestamp` are effectively required (400 otherwise).
- Very wide date ranges can 500/504 on HubSpot's side — chunk into ~6-month
  windows and merge.
- The `emails` array in aggregate responses contains duplicate IDs (~one per
  send); dedupe before counting.
- Covers marketing emails only — 1:1 sales emails live in the Engagements API.

## Requirements

- Python 3.8+ (standard library only, no pip installs)
- A HubSpot account with marketing emails and a private app token with the
  `content` scope
