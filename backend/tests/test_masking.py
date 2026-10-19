import pytest

from app.masking import mask_args, mask_url, mask_value


@pytest.mark.parametrize("raw, shown", [
    ("https://user:hunter2@mcp.example.com/sse?api_key=abc&region=eu", "https://user:***@mcp.example.com/sse?api_key=***&region=***"),
    ("https://mcp.example.com/mcp", "https://mcp.example.com/mcp"),
    ("https://tok@mcp.example.com/x", "https://***@mcp.example.com/x"),
])
def test_urls(raw, shown):
    assert mask_url(raw) == shown


@pytest.mark.parametrize("raw, shown", [
    ("ghp_" + "a" * 36, "***"),
    ("sk-ant-api03-" + "x" * 30, "***"),
    ("AKIA" + "ABCDEFGHIJKLMNOP", "***"),
    ("API_KEY=abc", "API_KEY=***"),
    ("--token=abc", "--token=***"),
    ("--port=8080", "--port=8080"),
    ("npx", "npx"),
    ("@modelcontextprotocol/server-github", "@modelcontextprotocol/server-github"),
])
def test_values(raw, shown):
    assert mask_value(raw) == shown


def test_flag_then_value():
    assert mask_args(["server", "--api-key", "abc", "--verbose", "--port", "80"]) == \
        ["server", "--api-key", "***", "--verbose", "--port", "80"]
    assert mask_args(["--auth", "--debug"]) == ["--auth", "--debug"]  # a flag after a flag isn't its value


def test_mcp_add_preview_and_audit_mask_command_args_and_url(authed, fake_cli):
    r = authed.post("/api/v1/actions/mcp.add", json={"params": {
        "client": "claude", "name": "gh", "transport": "stdio", "command": "npx",
        "args": ["gh-mcp", "--token", "ghp_" + "b" * 36]}, "dry_run": True}).json()
    assert "ghp_" not in str(r["argv"]) and r["argv"][-1] == "***"
    authed.post("/api/v1/actions/mcp.add", json={"params": {
        "client": "claude", "name": "remote", "transport": "http", "url": "https://x.example/mcp?key=s3cret"}})
    entry = authed.get("/api/v1/audit").json()[0]
    assert "s3cret" not in str(entry) and any("key=s3cret" in a for a in fake_cli.calls[-1][1])  # the real value still runs
