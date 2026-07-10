#!/usr/bin/env python3
"""PreToolUse guard: keep every HubSpot API interaction strictly read-only.

The plugin's service key carries the `content` scope, which technically
allows writes. This hook is the compensating control: it inspects each tool
call before execution and blocks anything that could modify the portal.

Policy (deny by default for commands touching the HubSpot API):
- Bash commands that don't reference the HubSpot API pass through untouched.
- Bash commands that do reference it are allowed only when they are
  (a) an invocation of the plugin's vetted read-only script
      (email_stats.py, GET-only by construction), or
  (b) a plain curl/wget fetch with no method-changing or data-sending flags.
  Anything else — including inline Python/Node that could hide a write —
  is blocked.
- HubSpot MCP tools whose names indicate writes (create/update/delete/...)
  are blocked as well, in case a HubSpot connector is enabled alongside.

Design note — why tokenize instead of regex-scanning the raw string:
curl's write flags (`-d`, `-F`, `-T`) collide with unrelated tools that a
legitimate read command pipes through (`cut -d=`, `tr -d`, `grep -F`,
`sort -T`). A raw scan flags those and produces false blocks. So we parse the
command into shell tokens and only treat `-d`/`-F`/`-T`/`-X POST`/etc. as
writes when they are genuine arguments to a curl/wget invocation. Token
extraction inside a quoted `$(...)` stays hidden (it is part of one quoted
token), so `curl -H "Authorization: Bearer $(grep K .env | cut -d= -f2)"` is
correctly read as a GET. Safety is preserved by (1) keeping a global scan for
code-based writes regardless of tokenization, and (2) failing CLOSED — any
parse failure or ambiguity blocks rather than allows.

Exit codes: 0 = allow, 2 = block (stderr explains why to Claude).
"""

import json
import re
import shlex
import sys

HUBSPOT_API = re.compile(r"hubapi\.com|api\.hubspot\.com", re.I)

# Code-based HTTP writes (python/node). Scanned across the whole command,
# since these can hide in a segment that doesn't start with curl/wget.
CODE_WRITE = re.compile(
    r"""(?x)
      \brequests\.(post|put|patch|delete)\b     # python requests
    | \.urlopen\([^)]*\bdata\s*=                 # urllib with a body
    | \bmethod\s*=\s*["'](POST|PUT|PATCH|DELETE) # explicit write method
    | \bhttp\.client\b
    | \bfetch\(                                  # js fetch
    | \baxios\b
    | \bXMLHttpRequest\b
    | \burllib\.request\.(Request|urlopen)\b     # unvetted inline urllib
    """,
    re.I,
)

# Shell operators that separate one simple command from the next.
SEGMENT_SEPARATORS = {"|", "||", "&&", ";", "&", "|&"}

# HTTP methods that read (everything else on -X/--request is treated as write).
READ_METHODS = {"GET", "HEAD"}

# Conservative fallback used only when the command can't be tokenized: matches
# curl/wget write flags in raw text. Case-sensitive so -d/-F/-T (write) are not
# confused with -D/-f/-t (read); may over-block, which is the safe direction.
FALLBACK_WRITE = re.compile(
    r"(^|\s)-X\s*['\"]?(POST|PUT|PATCH|DELETE|MERGE)"
    r"|--request\b|--method\b|--data|--form\b|--upload-file\b"
    r"|(^|\s)-[A-Za-z]*d[\s=@'\"]|(^|\s)-[A-Za-z]*[FT][\s=@'\"]"
)

READONLY_INVOCATIONS = re.compile(
    r"email_stats\.py|^\s*(curl|wget)\b", re.I
)

MCP_WRITE_TOOL = re.compile(
    r"create|update|delete|merge|archive|publish|upsert|batch-create"
    r"|batch-update|manage",
    re.I,
)


def block(reason):
    print(
        f"BLOCKED by hs-marketing-email-analytics read-only guard: {reason} "
        "This plugin never modifies the HubSpot portal. For data retrieval, "
        "use the bundled email_stats.py script (GET-only).",
        file=sys.stderr,
    )
    sys.exit(2)


def _short_flag_is_write(token):
    """True if a clustered short-flag token carries a curl write flag.

    Case-sensitive: only -d (data), -F (form), -T (upload-file) are writes.
    Their lowercase/uppercase counterparts (-D, -f, -t) are reads. Handles
    bundles and attached values, e.g. -sd, -d@file, -F'x=1'.
    """
    core = re.split(r"[=@'\"]", token[1:], 1)[0]  # flags before any value
    return any(c in core for c in ("d", "F", "T"))


def _method_is_write(method):
    return method.upper() not in READ_METHODS  # unknown/empty -> treat as write


def _segment_writes(segment):
    """True if this simple command is a curl/wget invocation that writes."""
    if not segment or segment[0].lower() not in ("curl", "wget"):
        return False
    args = segment[1:]
    for i, tok in enumerate(args):
        low = tok.lower()
        # Method override: -X / --request / --method  (case-sensitive -X, not -x proxy)
        if tok == "-X" or low in ("--request", "--method"):
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if _method_is_write(nxt):
                return True
            continue
        if tok.startswith("-X") and len(tok) > 2:            # -XPOST bundled
            if _method_is_write(tok[2:]):
                return True
            continue
        # Body / form / upload — long forms are unambiguous.
        if low.startswith("--data") or low in ("--form", "--upload-file"):
            return True
        # Short-flag clusters (not long options): case-sensitive d/F/T.
        if re.match(r"^-[A-Za-z]", tok) and not tok.startswith("--"):
            if _short_flag_is_write(tok):
                return True
    return False


def command_writes_to_api(command):
    """True if `command` could send a write to the HubSpot API."""
    if CODE_WRITE.search(command):
        return True
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Unparseable (e.g. unbalanced quotes) — fail closed.
        return bool(FALLBACK_WRITE.search(command))
    segment = []
    for tok in tokens:
        if tok in SEGMENT_SEPARATORS:
            if _segment_writes(segment):
                return True
            segment = []
        else:
            segment.append(tok)
    return _segment_writes(segment)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # nothing to inspect — don't break unrelated tooling

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool == "Bash":
        command = tool_input.get("command", "")
        if not HUBSPOT_API.search(command):
            sys.exit(0)
        if command_writes_to_api(command):
            block("the command contains an HTTP write indicator "
                  "(method override, request body, or code-based write).")
        if not READONLY_INVOCATIONS.search(command):
            block("only the vetted email_stats.py script or plain "
                  "curl/wget GETs may talk to the HubSpot API.")
        sys.exit(0)

    if tool.startswith("mcp__") and re.search(r"hubspot", tool, re.I):
        if MCP_WRITE_TOOL.search(tool):
            block(f"MCP tool '{tool}' can modify HubSpot records.")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
