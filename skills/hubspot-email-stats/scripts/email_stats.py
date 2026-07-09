#!/usr/bin/env python3
"""Fetch HubSpot marketing email statistics and content (read-only).

Uses only the Python standard library. Reads HUBSPOT_SERVICE_KEY from a .env
file found by walking up from the current working directory (or from the
environment if already set). Only ever issues GET requests.

Usage:
  python3 email_stats.py aggregate [--start 2026-06-01] [--end 2026-06-30]
                                   [--email-ids 123,456] [--property name]
  python3 email_stats.py histogram --interval DAY [--start ...] [--end ...]
                                   [--email-ids 123,456]
  python3 email_stats.py content   --email-ids 123,456 | --ids-file ids.json
                                   [--no-stats] [--full] [--limit N]

`content` fetches each email's details (name, subject, extracted body text,
and — by default — its lifetime stats in the same call) and emits one JSON
object per line (JSONL): ideal for building a content-vs-performance dataset.

Output: JSON on stdout (JSONL for `content`). Add --summary for a
human-readable digest on stderr; --out writes to a file instead of stdout.
"""

import argparse
import html
import html.parser
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://api.hubapi.com/marketing/emails/2026-03"
BASE_URL = f"{API_ROOT}/statistics"

INTERVALS = [
    "YEAR", "QUARTER", "MONTH", "WEEK", "DAY",
    "HOUR", "QUARTER_HOUR", "MINUTE", "SECOND",
]


def load_service_key():
    """Return HUBSPOT_SERVICE_KEY from env or the nearest .env file."""
    key = os.environ.get("HUBSPOT_SERVICE_KEY")
    if key:
        return key
    d = Path.cwd()
    for parent in [d, *d.parents]:
        env_file = parent / ".env"
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("HUBSPOT_SERVICE_KEY"):
                    _, _, value = line.partition("=")
                    value = value.strip().strip('"').strip("'")
                    if value:
                        return value
    sys.exit(
        "error: HUBSPOT_SERVICE_KEY not found in environment or any .env "
        "file from the current directory upward"
    )


def normalize_timestamp(value, end_of_day=False):
    """Accept YYYY-MM-DD or full ISO8601; return full ISO8601 UTC."""
    if not value:
        return None
    if len(value) == 10:  # bare date
        return f"{value}T23:59:59Z" if end_of_day else f"{value}T00:00:00Z"
    return value


def get_json(url, params, token, retries=5):
    """GET a URL, retrying on 429/5xx. Raises HTTPError on other failures."""
    query_pairs = [(n, v) for n, v in params if v is not None]
    if query_pairs:
        url = f"{url}?{urllib.parse.urlencode(query_pairs)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = float(e.headers.get("Retry-After") or 2 ** attempt)
                time.sleep(min(wait, 30))
                continue
            e.body = e.read().decode(errors="replace")
            raise


def request(url, params, token):
    """GET with fatal error reporting (for the single-shot subcommands)."""
    try:
        return get_json(url, params, token)
    except urllib.error.HTTPError as e:
        sys.exit(f"error: HTTP {e.code} from HubSpot\n{getattr(e, 'body', '')}")
    except urllib.error.URLError as e:
        sys.exit(f"error: request failed: {e.reason}")


def build_common_params(args):
    params = []
    if args.email_ids:
        for email_id in args.email_ids.split(","):
            params.append(("emailIds", email_id.strip()))
    params.append(("startTimestamp", normalize_timestamp(args.start)))
    params.append(("endTimestamp", normalize_timestamp(args.end, end_of_day=True)))
    return params


def fetch_aggregate(args, token):
    params = build_common_params(args)
    if args.property:
        params.append(("property", args.property))
    return request(f"{BASE_URL}/list", params, token)


def fetch_histogram(args, token):
    """Fetch all pages of the histogram, following paging.next.after."""
    results = []
    after = None
    while True:
        params = build_common_params(args)
        params.append(("interval", args.interval))
        if after:
            params.append(("after", after))
        page = request(f"{BASE_URL}/histogram", params, token)
        results.extend(page.get("results", []))
        after = page.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return {"total": len(results), "results": results}


# ---------------------------------------------------------------- content --

class _TextExtractor(html.parser.HTMLParser):
    """Collect visible text from HTML, skipping style/script."""

    SKIP = {"style", "script", "head", "title"}

    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.chunks.append(data.strip())


def strip_html(fragment):
    parser = _TextExtractor()
    try:
        parser.feed(fragment)
        parser.close()
    except Exception:
        return html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return " ".join(parser.chunks)


# Widget/flex-area keys whose string values hold email copy.
COPY_KEYS = {"html", "text", "richText", "rich_text", "value", "markdown"}
# Keys whose subtrees are styling/config, never copy.
NOISE_KEYS = {"css", "styles", "styleSettings", "fonts", "templatePath",
              "backgroundColor", "color", "url", "src", "href", "id", "key"}


def collect_copy(node, out):
    """Recursively collect copy-like strings from the content structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in NOISE_KEYS:
                continue
            if key in COPY_KEYS and isinstance(value, str) and value.strip():
                text = strip_html(value) if "<" in value else value.strip()
                if text:
                    out.append(text)
            else:
                collect_copy(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_copy(item, out)


def extract_body_text(email):
    """Best-effort plain text of the email body."""
    content = email.get("content") or {}
    plain = (content.get("plainTextVersion") or "").strip()
    if plain:
        return re.sub(r"[ \t]+", " ", plain)
    chunks = []
    for section in ("widgets", "widgetContainers", "flexAreas"):
        collect_copy(content.get(section), chunks)
    seen, unique = set(), []
    for chunk in chunks:
        if chunk not in seen:
            seen.add(chunk)
            unique.append(chunk)
    return "\n".join(unique)


def email_record(email, include_stats):
    record = {
        "id": email.get("id"),
        "name": email.get("name"),
        "subject": email.get("subject"),
        "state": email.get("state"),
        "publishDate": email.get("publishDate") or email.get("publishedAt"),
        "campaign": email.get("campaign"),
        "campaignName": email.get("campaignName"),
        "subcategory": email.get("subcategory"),
        "bodyText": extract_body_text(email),
    }
    if include_stats and email.get("stats"):
        stats = email["stats"]
        record["counters"] = stats.get("counters", {})
        record["ratios"] = stats.get("ratios", {})
    return record


def load_ids(args):
    ids = []
    if args.email_ids:
        ids += [i.strip() for i in args.email_ids.split(",") if i.strip()]
    if args.ids_file:
        raw = Path(args.ids_file).read_text().strip()
        if raw.startswith("["):
            ids += [str(i) for i in json.loads(raw)]
        else:
            ids += [line.strip() for line in raw.splitlines() if line.strip()]
    # dedupe, preserve order
    seen = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]
    if not ids:
        sys.exit("error: content mode needs --email-ids and/or --ids-file")
    return ids[: args.limit] if args.limit else ids


def fetch_content(args, token, sink):
    """Fetch details for each email ID; write one JSON object per line."""
    ids = load_ids(args)
    include_stats = not args.no_stats
    fetched = errors = 0
    for n, email_id in enumerate(ids, 1):
        params = [("includeStats", "true")] if include_stats else []
        try:
            email = get_json(f"{API_ROOT}/{email_id}", params, token)
        except urllib.error.HTTPError as e:
            errors += 1
            print(f"warn: email {email_id}: HTTP {e.code}", file=sys.stderr)
            continue
        except urllib.error.URLError as e:
            errors += 1
            print(f"warn: email {email_id}: {e.reason}", file=sys.stderr)
            continue
        record = email if args.full else email_record(email, include_stats)
        sink.write(json.dumps(record, ensure_ascii=False) + "\n")
        fetched += 1
        if args.summary and not args.full:
            c = record.get("counters", {})
            delivered = c.get("delivered", 0)
            rate = (f" open={100 * c.get('open', 0) / delivered:.1f}%"
                    if delivered else "")
            print(f"[{n}/{len(ids)}] {email_id} \"{(record.get('subject') or '')[:60]}\""
                  f"{rate}", file=sys.stderr)
        time.sleep(args.delay)
    print(f"done: {fetched} fetched, {errors} errors", file=sys.stderr)


# ------------------------------------------------------------------ stats --

def pct(numerator, denominator):
    return f"{100.0 * numerator / denominator:.2f}%" if denominator else "n/a"


def summarize_stats(stats):
    """One-line digest of an EmailStatisticsData counters block."""
    c = stats.get("counters", {})
    sent = c.get("sent", 0)
    delivered = c.get("delivered", 0)
    return (
        f"sent={sent} delivered={delivered} "
        f"open={c.get('open', 0)} ({pct(c.get('open', 0), delivered)}) "
        f"click={c.get('click', 0)} ({pct(c.get('click', 0), delivered)}) "
        f"bounce={c.get('bounce', 0)} ({pct(c.get('bounce', 0), sent)}) "
        f"unsubscribed={c.get('unsubscribed', 0)}"
    )


def print_summary(mode, data):
    print("\n--- summary ---", file=sys.stderr)
    if mode == "aggregate":
        aggregate = data.get("aggregate") or {}
        print(f"overall: {summarize_stats(aggregate)}", file=sys.stderr)
        emails = data.get("emails") or []
        print(f"emails in range: {len(set(emails))} unique "
              f"({len(emails)} entries incl. duplicates)", file=sys.stderr)
        for campaign_id, stats in (data.get("campaignAggregations") or {}).items():
            print(f"campaign {campaign_id}: {summarize_stats(stats)}", file=sys.stderr)
    else:
        for bucket in data.get("results", []):
            start = bucket.get("interval", {}).get("start", "?")
            print(f"{start}: {summarize_stats(bucket.get('aggregations', {}))}",
                  file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("aggregate", "histogram", "content"):
        p = sub.add_parser(mode)
        p.add_argument("--email-ids", help="comma-separated email IDs")
        p.add_argument("--summary", action="store_true",
                       help="print a human-readable digest to stderr")
        p.add_argument("--out", help="write output to this file instead of stdout")
        if mode == "content":
            p.add_argument("--ids-file",
                           help="file of email IDs (JSON array or one per line)")
            p.add_argument("--no-stats", action="store_true",
                           help="skip per-email lifetime stats")
            p.add_argument("--full", action="store_true",
                           help="emit the raw PublicEmail JSON instead of the "
                                "extracted record")
            p.add_argument("--limit", type=int,
                           help="stop after this many emails")
            p.add_argument("--delay", type=float, default=0.12,
                           help="seconds between requests (default 0.12)")
        else:
            p.add_argument("--start", help="startTimestamp (YYYY-MM-DD or ISO8601)")
            p.add_argument("--end", help="endTimestamp (YYYY-MM-DD or ISO8601)")
            if mode == "aggregate":
                p.add_argument("--property",
                               help="limit which email properties are returned")
            else:
                p.add_argument("--interval", default="DAY", choices=INTERVALS)
    args = parser.parse_args()

    token = load_service_key()

    if args.mode == "content":
        sink = open(args.out, "w") if args.out else sys.stdout
        try:
            fetch_content(args, token, sink)
        finally:
            if args.out:
                sink.close()
                print(f"wrote {args.out}", file=sys.stderr)
        return

    data = fetch_aggregate(args, token) if args.mode == "aggregate" \
        else fetch_histogram(args, token)
    output = json.dumps(data, indent=2)
    if args.out:
        Path(args.out).write_text(output)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(output)
    if args.summary:
        print_summary(args.mode, data)


if __name__ == "__main__":
    main()
