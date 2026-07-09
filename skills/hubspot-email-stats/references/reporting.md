# Presenting results

## Quick answers — stay in the conversation

For simple questions ("what was June's open rate?"), answer compactly in
chat: a small table for totals/comparisons, a trend description for
histograms, then 2–3 observations — what stands out, what to check, what to
do next. Show absolute counts alongside rates (a 40% open rate on 10 sends
is noise), and note when a rate sits on a small denominator.

Rough framing benchmarks (vary by industry — use to frame, not judge):
open 20–35%, click 2–5%, bounce < 2%, unsubscribe < 0.5%.

## Shareable output — the HTML report

For content analyses, period reviews, or anything the user will share
(training sessions, customer demos, stakeholder reviews), generate a
self-contained HTML report from the bundled template at
`assets/report_template.html` under this skill's base directory. It needs
no network access, no dependencies, and honours light/dark mode.

Steps:

1. Copy the template into the user's project (e.g. `email_report.html`).
2. Build the report JSON. The full schema is documented in a comment
   directly above the `__REPORT_DATA__` placeholder inside the template —
   read it there. In short: `title`, `subtitle`, `kpis[]`,
   `features[]` (each with `values[]` of label/n/ctr/open), `top[]` /
   `bottom[]` email tables, `insights[]`.
3. Replace the literal `__REPORT_DATA__` token with the JSON (keep
   `ensure_ascii=False` so non-English copy renders properly).
4. Tell the user to open the file in a browser (`open email_report.html`
   on macOS).

Content guidance:

- `subtitle` should state the period, corpus size, and any sampling — the
  report must be honest about its own basis.
- `features` bars are sorted by whatever story you're telling; keep 2–4
  feature groups, each with 3–6 values. All rates as percentages (0–100).
- `top`/`bottom` tables: rank by CTR with a minimum-delivered threshold;
  4–10 rows each.
- `insights` is the payoff: 3–5 specific, actionable findings with numbers
  and a recommendation each ("Newsletters: 30–42% opens but 0% CTR —
  A/B test stronger in-body CTAs"). Never generic advice.
