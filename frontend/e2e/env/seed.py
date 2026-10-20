"""Seed a throwaway home for the journey suite: small, made-up Claude Code / Codex state so
every page has something to show. Never touches the real ~/.claude, ~/.codex or ~/.eyrie.

    backend/.venv/bin/python frontend/e2e/env/seed.py <root>

<root> must be an empty temp dir. Lays out <root>/home (HOME for the backend) and <root>/bin
(stand-in claude/codex binaries). Reuses the transcript builders from backend/tests.
"""
import json
import os
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

from app.tools.claude import transcript_dir  # noqa: E402
from tests.test_usage import NOW, assistant, write  # noqa: E402
from tests.test_usage_codex import meta, record, turn  # noqa: E402

CLAUDE_CONVS = {
    "eyrie": ["2b6f0d1e-5a4c-4e8b-9f21-0c3d4e5f6a7b", "6e1a2b3c-4d5e-4f60-8a9b-0c1d2e3f4a5b"],
    "atlas": ["9c8b7a6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"],
}
CODEX_THREAD = "01a13480-5390-7ed3-85c3-0e32b8d04c8e"
# The idle-sessions journey's conversation: a big context, last active three days ago.
IDLE_CONV = "7d3c2b1a-0f9e-4d8c-b7a6-5f4e3d2c1b0a"

FAKE_CLAUDE = """#!/bin/sh
# Stand-in for `claude` in the journey suite: answers the calls Eyrie makes, and otherwise
# behaves like an idle interactive session.
case "$1" in
  --version|-v) echo "2.3.1 (Claude Code)"; exit 0 ;;
  plugin)
    if [ "$2" = "list" ]; then
      cat <<'JSON'
[{"id": "release-notes@eyrie-demo", "version": "1.4.0", "scope": "user", "enabled": true},
 {"id": "pr-review@eyrie-demo", "version": "0.9.2", "scope": "user", "enabled": false}]
JSON
      exit 0
    fi
    echo "plugin changes are disabled in the journey suite" >&2; exit 1 ;;
  mcp) echo "MCP changes are disabled in the journey suite" >&2; exit 1 ;;
esac
printf '\\n  Claude Code (journey-suite stand-in)\\n  cwd: %s\\n\\n> ' "$(pwd)"
while IFS= read -r line; do printf 'you said: %s\\n> ' "$line"; done
"""

FAKE_CODEX = """#!/bin/sh
case "$1" in
  --version|-v) echo "codex-cli 0.61.0"; exit 0 ;;
  mcp) echo "MCP changes are disabled in the journey suite" >&2; exit 1 ;;
esac
printf '\\n  Codex (journey-suite stand-in)\\n\\n> '
while IFS= read -r line; do printf 'ok: %s\\n> ' "$line"; done
"""

TASKS = """# Tasks

## This week
- [ ] Review the usage dashboard numbers
- [ ] Write release notes for 0.3.0
- [x] Rotate the staging API key
- [ ] Try the Codex MCP server for docs

## Later
- [ ] Phone layout for the Sessions page
"""


def main(root: Path) -> None:
    home, bin_dir = root / "home", root / "bin"
    projects = home / "projects"
    for name in CLAUDE_CONVS:
        (projects / name).mkdir(parents=True)
    (projects / "scratch").mkdir()

    # Claude Code: projects + MCP servers in ~/.claude.json, transcripts with usage spread
    # over the last two weeks, two subagents' memory.
    (home / ".claude.json").write_text(json.dumps({
        "projects": {str(projects / n): {} for n in CLAUDE_CONVS},
        "mcpServers": {
            "obsidian": {"type": "stdio", "command": "npx", "args": ["-y", "obsidian-mcp"]},
            "linear": {"type": "http", "url": "https://mcp.linear.example/mcp"},
        },
    }, indent=2))
    claude_home = home / ".claude"
    models = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    n = 0
    for name, convs in CLAUDE_CONVS.items():
        cwd = str(projects / name)
        for ci, conv in enumerate(convs):
            records = []
            for day in range(14):
                for k in range(1 + (day * 7 + ci) % 4):
                    n += 1
                    records.append(assistant(
                        f"msg_{n}", model=models[(day + k + ci) % 3], ts=NOW - timedelta(days=day, hours=k),
                        session=conv, cwd=cwd, req=f"req_{n}",
                        input_tokens=1200 + 97 * (n % 13), output_tokens=400 + 53 * (n % 11),
                        cache_read_input_tokens=20000 + 1500 * (n % 7), cache_creation_input_tokens=800 * (n % 3)))
            write(transcript_dir(claude_home, cwd) / f"{conv}.jsonl", records)
    idle_at = NOW - timedelta(days=3)
    idle = transcript_dir(claude_home, str(projects / "eyrie")) / f"{IDLE_CONV}.jsonl"
    write(idle, [
        assistant("msg_idle", model=models[0], ts=idle_at, session=IDLE_CONV, cwd=str(projects / "eyrie"), req="req_idle",
                  input_tokens=1800, output_tokens=900, cache_read_input_tokens=138000, cache_creation_input_tokens=2400),
        {"type": "custom-title", "customTitle": "tidy-release-notes", "sessionId": IDLE_CONV},
    ])
    os.utime(idle, (idle_at.timestamp(), idle_at.timestamp()))
    (claude_home / "settings.json").write_text('{"enabledPlugins": {"release-notes@eyrie-demo": true}}\n')
    mem = claude_home / "agent-memory"
    (mem / "code-reviewer").mkdir(parents=True)
    (mem / "code-reviewer/conventions.md").write_text(
        "# Conventions\n\n- Prefer small PRs, one topic each.\n- Tests live next to the code they cover.\n")
    (mem / "release-captain").mkdir()
    (mem / "release-captain/checklist.md").write_text(
        "# Release checklist\n\n1. Bump VERSION\n2. Build the widget\n3. Tag and publish\n")

    # Codex: an MCP server, a thread in the state DB, and rollouts for usage.
    codex_home = home / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text('model = "gpt-6.1-sol"\n\n[mcp_servers.docs]\nurl = "https://docs.example/mcp"\n')
    with sqlite3.connect(codex_home / "state_5.sqlite") as con:
        con.execute("CREATE TABLE threads (id TEXT, cwd TEXT, model TEXT, tokens_used INT, created_at INT, "
                    "updated_at INT, reasoning_effort TEXT, title TEXT, archived INT)")
        ts = int(NOW.timestamp())
        con.execute("INSERT INTO threads VALUES (?, ?, 'gpt-6.1-sol', 184000, ?, ?, 'medium', ?, 0)",
                    (CODEX_THREAD, str(projects / "atlas"), ts - 7200, ts - 600, "Tidy the atlas importer"))
    for day in range(0, 10, 2):
        when = NOW - timedelta(days=day)
        cwd = str(projects / "atlas")
        write(codex_home / f"sessions/{when.astimezone():%Y/%m/%d}/rollout-{day}-{CODEX_THREAD}.jsonl", [
            meta(ts=when, cwd=cwd), turn("gpt-6.1-sol", ts=when, cwd=cwd),
            # input counts the cached part too, as Codex reports it.
            record(f"resp_{day}_a", ts=when, input=39000 + day * 500, cached=30000, output=2500),
            record(f"resp_{day}_b", ts=when, input=16000, cached=12000, output=900 + day * 40),
        ])

    notes = home / "notes"
    notes.mkdir()
    (notes / "Tasks.md").write_text(TASKS)

    bin_dir.mkdir()
    for name, body in (("claude", FAKE_CLAUDE), ("codex", FAKE_CODEX)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)

    eyrie = home / ".eyrie"
    eyrie.mkdir()
    (eyrie / "eyrie.toml").write_text(
        '[tools]\nenabled = ["claude", "codex"]\n\n'
        f'[sessions]\nroots = ["{projects}"]\n\n'
        f'[paths]\ntasks = "{notes / "Tasks.md"}"\n')


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve()
    if any(target.iterdir()):
        raise SystemExit(f"{target} isn't empty; seed only into a fresh temp dir")
    main(target)
