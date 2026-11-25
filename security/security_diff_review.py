"""
Layer 6 — AI Security Diff Review (Astra or Claude Opus)
========================================================
Extracts the current staged git diff and sends it to one AI reviewer for a
structured security review against a 10-point checklist. A commit made from a
Claude Code session is reviewed by Astra, any other commit by Claude Opus, so
no lab reviews its own agent's code (rule of 2026-11-24):

  astra   gpt-6.2-astra through the Codex CLI (codex exec), reasoning effort medium
  claude  claude-opus-5-5 through the Claude Code CLI (claude -p), effort low

Reviewer choice: SECURITY_DIFF_REVIEWERS=astra|claude when set; otherwise astra
when CLAUDECODE is set (Claude Code sets it for the commands it runs);
otherwise claude. Each CLI uses its own login (no API key), starts in a new
empty temporary directory without the user's settings or MCP servers, and is
stopped after TIMEOUT_S seconds.

Exit codes:
  0 — No Critical/High findings (commit proceeds)
  1 — Critical or High finding detected (commit blocked)
  2 — Reviewer unavailable: unknown SECURITY_DIFF_REVIEWERS value, CLI missing,
      failed or timed out, or no findings list in its answer (caller issues
      WARN, does not block)

Usage: python security/security_diff_review.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_S = 150  # one reviewer call; pre_commit_hook.py gives this script 180 s
MIN_DIFF_LINES = 20  # caller already checks this, but guard here too

REVIEWERS_ENV = "SECURITY_DIFF_REVIEWERS"
ASTRA_MODEL = "gpt-6.2-astra"
ASTRA_EFFORT = "medium"
CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_EFFORT = "low"
LABELS = {"astra": f"Astra ({ASTRA_MODEL})", "claude": f"Claude Opus ({CLAUDE_MODEL})"}

SECURITY_PROMPT = """You are a security code reviewer. Analyze the following git diff for security vulnerabilities.

CRITICAL — understand git diff syntax before reviewing:
- Lines starting with "+" are NEWLY ADDED code. Review these for introduced vulnerabilities.
- Lines starting with "-" are REMOVED/OLD code being deleted. Do NOT flag these as vulnerabilities — they are being removed.
- Lines with no prefix (+/-) are unchanged context lines shown for readability only.
- A diff that REMOVES insecure code (e.g. removes inline onclick handlers, removes unsafe-inline CSP, removes missing auth checks) is a SECURITY FIX. Do NOT flag it as a vulnerability.
- A diff that ADDS security controls (e.g. adds @admin_required decorator, adds CSP nonce, adds rate limiting, adds input validation) is a SECURITY IMPROVEMENT. Do NOT flag it as a vulnerability.
- Only flag code that is INTRODUCED by this diff (i.e. on "+" lines) and that represents a net new security risk.

Return ONLY valid JSON (no markdown, no explanation outside the JSON) with this exact structure:
{
  "findings": [
    {
      "severity": "Critical|High|Medium|Low|Info",
      "description": "clear description of the issue",
      "file": "filename or empty string",
      "line": "line number or range, or empty string"
    }
  ]
}

If there are no findings, return: {"findings": []}

Review checklist (apply only to NEWLY ADDED "+" lines):
1. Authorization logic gaps — new endpoints added without auth checks
2. Privilege escalation — new code granting lower-privilege users higher-privilege access
3. Missing input validation — new routes or handlers that accept user input without sanitization
4. Authentication bypass — new code that allows skipping authentication
5. SQL injection — new code using raw string formatting or concatenation with user input in SQL
6. Insecure direct object references — new code accessing records by ID without ownership check
7. Business logic vulnerabilities — new logic that can be abused for unintended outcomes
8. Secret or credential exposure — keys, tokens, passwords hardcoded in new code
9. Dangerous function calls — new uses of eval(), exec(), subprocess with shell=True, pickle.loads()
10. Missing CSRF protection or rate-limiting on new state-changing routes

Only flag Critical or High for confirmed net-new vulnerabilities introduced by this diff. Use Medium/Low for potential issues. Do not flag pre-existing patterns in unchanged context lines.

IMPORTANT — Deployment context (do NOT flag these as vulnerabilities):
- This is a SINGLE-USER, LOCAL-ONLY application. There is no network-facing API and no multi-tenant access. The CLI runs on the operator's machine — filesystem access IS the authorization boundary.
- MCP (Model Context Protocol) tools run on localhost over stdio — they are invoked by a local AI agent, not over a network. Process-level isolation is the access control.
- Do NOT flag CLI commands or MCP tools for "missing authorization" or "missing authentication". These are local operator tools, not web endpoints.
- Do NOT flag parameterized SQL (SQLAlchemy text() with :named_params, or psycopg %s placeholders) as SQL injection. Only flag raw string concatenation/formatting of user input into SQL.
- Do NOT flag psycopg.connect() with keyword arguments (host=, password=) as credential exposure — these read from environment variables, which is standard practice.
"""


def get_staged_diff() -> str:
    result = subprocess.run(
        ["git", "diff", "--staged"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout


class ReviewerUnavailable(Exception):
    """The reviewer gave no usable answer; layer 6 is skipped with a WARN."""


def choose_reviewer() -> str:
    """SECURITY_DIFF_REVIEWERS when set; otherwise astra when CLAUDECODE is set,
    otherwise claude. A name other than astra or claude raises ValueError."""
    chosen = os.environ.get(REVIEWERS_ENV, "").strip().lower()
    if not chosen:
        chosen = "astra" if os.environ.get("CLAUDECODE") else "claude"
    if chosen not in LABELS:
        raise ValueError(f"{REVIEWERS_ENV}={chosen!r} is not astra or claude")
    return chosen


def _which(name: str) -> str | None:
    """The CLI on PATH, else in ~/.local/bin, where both CLIs install by default
    (a commit started from an editor can run with a shorter PATH)."""
    found = shutil.which(name)
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / name
    return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None


def _run_cli(cmd: list[str], stdin_text: str, workdir: str) -> subprocess.CompletedProcess[str]:
    """One reviewer CLI run in workdir with stdin_text as its input."""
    name = Path(cmd[0]).name
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired as e:
        raise ReviewerUnavailable(f"{name} timed out after {TIMEOUT_S} s") from e
    except OSError as e:
        raise ReviewerUnavailable(f"{name} could not start ({type(e).__name__})") from e
    if proc.returncode != 0:
        detail = " ".join((proc.stderr.strip() or proc.stdout.strip())[-200:].split())
        raise ReviewerUnavailable(f"{name} exit {proc.returncode}: {detail}")
    return proc


def _review_astra(prompt: str, workdir: str) -> str:
    """codex exec: one read-only, ephemeral turn with the user's Codex config,
    MCP servers and web search off. The final message is read from the -o file."""
    binary = _which("codex")
    if binary is None:
        raise ReviewerUnavailable("codex CLI not found")
    out_file = Path(workdir) / "last_message.txt"
    cmd = [
        binary, "exec", "--json", "-s", "read-only", "--ephemeral", "--skip-git-repo-check",
        "--ignore-user-config", "-c", "mcp_servers={}", "-c", 'web_search="disabled"',
        "-m", ASTRA_MODEL, "-c", f'model_reasoning_effort="{ASTRA_EFFORT}"',
        "-C", workdir, "-o", str(out_file), "-",
    ]
    _run_cli(cmd, prompt, workdir)
    try:
        return out_file.read_text(encoding="utf-8")
    except OSError as e:
        raise ReviewerUnavailable("codex wrote no final message") from e


def _review_claude(system_prompt: str, user_text: str, workdir: str) -> str:
    """claude -p: the checklist as the system prompt and the diff on stdin; no
    tools, no settings files, no MCP servers, no saved session. The answer is
    the "result" field of the JSON output."""
    binary = _which("claude")
    if binary is None:
        raise ReviewerUnavailable("claude CLI not found")
    cmd = [
        binary, "-p", "--output-format", "json", "--model", CLAUDE_MODEL, "--effort", CLAUDE_EFFORT,
        "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
        "--system-prompt", system_prompt,
    ]
    proc = _run_cli(cmd, user_text, workdir)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ReviewerUnavailable("claude printed no JSON result") from e
    if not isinstance(data, dict) or data.get("is_error") or data.get("subtype") != "success" or not data.get("result"):
        subtype = data.get("subtype") if isinstance(data, dict) else type(data).__name__
        raise ReviewerUnavailable(f"claude returned no answer ({str(subtype)[:80]})")
    return str(data["result"])


def review(reviewer: str, diff: str) -> str:
    """The reviewer's answer for the diff. The CLI starts in a new empty
    directory, removed afterwards. Raises ReviewerUnavailable."""
    framed = f"Diff to review:\n```\n{diff}\n```"
    workdir = tempfile.mkdtemp(prefix="xpc-diff-review-")
    try:
        if reviewer == "astra":
            return _review_astra(f"{SECURITY_PROMPT}\n\n{framed}", workdir)
        return _review_claude(SECURITY_PROMPT, framed, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def parse_findings(raw: str) -> list[dict]:
    """The findings list of a reviewer's JSON answer, each severity capitalised
    ("HIGH" -> "High"). An answer without a findings list raises ValueError."""
    text = raw.strip()
    # Strip markdown code fences if the reviewer wraps the JSON
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:]).rstrip("`").strip()
    result = json.loads(text)
    if not isinstance(result, dict) or not isinstance(result.get("findings"), list):
        raise ValueError("no findings list")
    findings: list[dict] = []
    for item in result["findings"]:
        finding = item if isinstance(item, dict) else {"description": str(item)}
        severity = finding.get("severity")
        finding["severity"] = severity.strip().capitalize() if isinstance(severity, str) else "?"
        findings.append(finding)
    return findings


def main() -> None:
    try:
        reviewer = choose_reviewer()
    except ValueError as e:
        print(f"WARN: {e} — skipping Layer 6", file=sys.stderr)
        sys.exit(2)
    label = LABELS[reviewer]

    try:
        diff = get_staged_diff()
    except Exception as e:
        print(f"WARN: Could not get staged diff ({e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    if not diff.strip() or len(diff.splitlines()) < MIN_DIFF_LINES:
        print(f"SKIP: diff too small ({len(diff.splitlines())} lines)")
        sys.exit(0)

    try:
        raw = review(reviewer, diff)
    except ReviewerUnavailable as e:
        print(f"WARN: {label} review unavailable ({e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    try:
        findings = parse_findings(raw)
    except ValueError as e:
        print(f"WARN: {label} answer is not a findings list ({e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    if not findings:
        print(f"Layer 6 — {label}: No security findings.")
        sys.exit(0)

    blocked: list[dict] = []
    for f in findings:
        sev = f.get("severity", "?")
        desc = f.get("description", "")
        file_ = f.get("file", "")
        line = f.get("line", "")
        loc = f"{file_}:{line}" if file_ else "(no location)"
        print(f"  [{sev}] {loc} — {desc}")
        if sev in ("Critical", "High"):
            blocked.append(f)

    if blocked:
        print(f"\nLayer 6 — {label}: {len(blocked)} Critical/High finding(s) — commit blocked.")
        sys.exit(1)

    print(f"Layer 6 — {label}: {len(findings)} finding(s), none Critical/High — passing.")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # a fault in this script: the review did not happen
        print(f"WARN: Layer 6 review failed ({type(e).__name__}: {e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)
