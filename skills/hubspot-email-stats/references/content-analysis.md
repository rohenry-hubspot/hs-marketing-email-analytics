# Semantic content analysis — which emails perform better, and why?

The flagship workflow: correlate what emails *say* (subject line + body
copy) with how they *perform*. You are the semantic layer — no external ML
is needed; you read the copy directly, in whatever language the corpus is in.

## 1. Build the dataset

1. `aggregate` over the analysis period to get email IDs. **Dedupe** them
   (the `emails` array holds ~one entry per send) and save as a JSON array.
2. `content --ids-file <file> --out emails.jsonl` fetches each email's
   subject, extracted body text, and lifetime stats in one call per email
   (~8 emails/s). Sanity-check with `--limit 20` first. Expect some 404s
   for deleted emails — the script warns and skips them.

Dataset gotchas:

- In `content` records, `ratios` are **percentages (0–100)** (e.g.
  `openratio: 21.4`) — unlike the 0–1 fractions of the statistics
  endpoints. Check magnitude before formatting.
- Body/subject text may contain personalization tokens
  (`{{ contact.firstname }}`, `{{ personalization_token(...) }}`). Treat
  them as placeholders; record "uses personalization" as a feature. A raw
  token in a *subject* usually means a broken send — flag it, it's a
  valuable QA finding.

## 2. Tag semantic features

Read each email (subject + bodyText) and assign a compact feature set:

- **topic/theme** — infer from the corpus, keep to 5–10 values
- **email type** — newsletter digest / event invite / sales pitch /
  announcement / transactional-ish
- **subject style** — question, urgency/FOMO, curiosity gap, announcement,
  emoji, personalization, time-specific, plain-informative
- **tone** — urgent / informative / playful / salesy
- **offer & CTA** — offer type if any, CTA strength (none / soft / strong),
  CTA count
- **length** — approximate body word count (compute, don't guess)

For corpora too large to read whole (more than a few hundred emails), tag a
**stratified sample** — stratify by `subcategory` and send volume — and say
so explicitly in the output.

## 3. Write a tidy dataset

One CSV row per email: id, subject, the features above, delivered,
open rate, CTR (click/open), click rate (click/delivered). Compute rates
from `counters` rather than trusting pre-computed ratios blindly.

## 4. Correlate honestly

- **Median** (not mean) open rate and CTR per feature value, always with
  `n` alongside.
- Compare **within `subcategory`** — automated emails run on different
  dynamics than batch newsletters; mixing them produces false signals.
- Exclude tiny sends (< 100 delivered) from feature medians.
- Lead with **CTR** — Apple Mail Privacy Protection inflates opens, so
  click-through (click/open) is the more trustworthy engagement signal.
  High opens + zero clicks is itself a finding (content satisfies without
  clicking, or links lack pull).
- Correlation is not causation. Frame findings as "worth A/B testing",
  never "this works". Confounders to name when relevant: audience/list,
  send time, seasonality, send volume.

## 5. Present

Read [reporting.md](reporting.md) — content analyses deserve the full HTML
report, not just a chat summary.
