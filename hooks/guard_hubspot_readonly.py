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

Exit codes: 0 = allow, 2 = block (stderr explains why to Claude).
"""

import json
import re
import sys

HUBSPOT_API = re.compile(r"hubapi\.com|api\.hubspot\.com", re.I)

# Anything that changes the HTTP method or sends a body / uploads data.
WRITE_INDICATORS = re.compile(
    r"""(?x)
      (^|\s)-X[\s=]* \w                       # curl -X <METHOD>
    | --request\b
    | (^|\s)-d\b | --data\b | --data-\w+\b    # request bodies
    | (^|\s)-F\b | --form\b
    | (^|\s)-T\b | --upload-file\b
    | --method\b
    | \brequests\.(post|put|patch|delete)\b   # python requests
    | \burlopen\([^)]*\bdata\s*=              # urllib with a body
    | \bmethod\s*=\s*["'](POST|PUT|PATCH|DELETE)
    | \bhttp\.client\b
    | \bfetch\( | \baxios\b                   # js clients
    """,
    re.I,
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
        if WRITE_INDICATORS.search(command):
            block("the command contains an HTTP write indicator "
                  "(method override or request body).")
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
