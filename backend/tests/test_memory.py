import os

import pytest

from app.fsutil import etag

URL = "/api/v1/memory"


@pytest.fixture
def agent_dir(home):
    d = home / ".claude/agent-memory/code-reviewer"
    (d / "vite-proxy.md").write_text("# Vite proxy\n\nCheck the port.\n")
    (d / "MEMORY.md").write_text("- [Vite proxy](vite-proxy.md) — 404s in dev\n- [[notes]]\n")
    return d


def test_snapshot_lists_files(client, agent_dir):
    agent = client.get("/api/v1/sources/memory").json()["agents"][0]
    assert agent["agent"] == "code-reviewer" and agent["file_count"] == 3
    assert [f["name"] for f in agent["files"]] == ["MEMORY.md", "notes.md", "vite-proxy.md"]


def test_read_includes_etag_and_backlinks(client, agent_dir):
    r = client.get(f"{URL}/code-reviewer/vite-proxy.md").json()
    assert r["content"].startswith("# Vite proxy") and r["etag"] == etag(r["content"])
    assert r["linked_from"] == ["MEMORY.md"]
    assert client.get(f"{URL}/code-reviewer/notes.md").json()["linked_from"] == ["MEMORY.md"]  # [[notes]]


def test_write_with_matching_etag(authed, agent_dir):
    cur = authed.get(f"{URL}/code-reviewer/vite-proxy.md").json()
    r = authed.put(f"{URL}/code-reviewer/vite-proxy.md", json={"content": "# Vite proxy\n\nUse port 8000.\n"},
                   headers={"If-Match": cur["etag"]})
    assert r.status_code == 200 and "8000" in (agent_dir / "vite-proxy.md").read_text()
    assert authed.get("/api/v1/audit").json()[0]["action"] == "memory.write"


def test_stale_write_refused_and_file_kept(authed, agent_dir):
    cur = authed.get(f"{URL}/code-reviewer/vite-proxy.md").json()
    (agent_dir / "vite-proxy.md").write_text("# Edited by the agent meanwhile\n")
    r = authed.put(f"{URL}/code-reviewer/vite-proxy.md", json={"content": "mine"}, headers={"If-Match": cur["etag"]})
    assert r.status_code == 409 and r.json()["current"]["content"] == "# Edited by the agent meanwhile\n"
    assert (agent_dir / "vite-proxy.md").read_text() == "# Edited by the agent meanwhile\n"


def test_create_new_file_needs_absent(authed, agent_dir):
    r = authed.put(f"{URL}/code-reviewer/new note.md", json={"content": "x"}, headers={"If-Match": "absent"})
    assert r.status_code == 200 and (agent_dir / "new note.md").read_text() == "x"
    # creating over an existing file is a conflict
    r = authed.put(f"{URL}/code-reviewer/vite-proxy.md", json={"content": "x"}, headers={"If-Match": "absent"})
    assert r.status_code == 409


def test_cant_create_agent_folders(authed, agent_dir):
    r = authed.put(f"{URL}/brand-new-agent/a.md", json={"content": "x"}, headers={"If-Match": "absent"})
    assert r.status_code == 404


def test_delete_moves_to_eyrie_trash(authed, agent_dir, home):
    cur = authed.get(f"{URL}/code-reviewer/vite-proxy.md").json()
    r = authed.delete(f"{URL}/code-reviewer/vite-proxy.md", headers={"If-Match": cur["etag"]}).json()
    assert r["trashed_to"] == "agent-memory/code-reviewer/vite-proxy.md"
    assert not (agent_dir / "vite-proxy.md").exists()
    assert (home / ".eyrie/trash" / r["trashed_to"]).read_text().startswith("# Vite proxy")
    entry = authed.get("/api/v1/audit").json()[0]
    assert entry["action"] == "memory.delete" and "Moved to agent-memory/" in entry["message"]


def test_delete_twice_keeps_both_in_trash(authed, agent_dir, home):
    for _ in range(2):
        (agent_dir / "tmp.md").write_text("again")
        authed.delete(f"{URL}/code-reviewer/tmp.md", headers={"If-Match": etag("again")})
    assert len(list((home / ".eyrie/trash/agent-memory/code-reviewer").iterdir())) == 2


def test_delete_stale_refused(authed, agent_dir):
    r = authed.delete(f"{URL}/code-reviewer/vite-proxy.md", headers={"If-Match": "0" * 16})
    assert r.status_code == 409 and (agent_dir / "vite-proxy.md").exists()


def test_writes_need_token(client, agent_dir):
    assert client.put(f"{URL}/code-reviewer/vite-proxy.md", json={"content": "x"}, headers={"If-Match": "absent"}).status_code == 401
    assert client.delete(f"{URL}/code-reviewer/vite-proxy.md", headers={"If-Match": "x"}).status_code == 401


@pytest.mark.parametrize("path", [
    "code-reviewer/..%2F..%2F..%2FTasks.md",
    "code-reviewer/notes.txt",
    "code-reviewer/.hidden.md",
    "..%2Fsecrets/a.md",
    "code-reviewer/a%2Fb.md",
])
def test_names_outside_scope_rejected(authed, agent_dir, home, path):
    r = authed.put(f"{URL}/{path}", json={"content": "pwned"}, headers={"If-Match": "absent"})
    assert r.status_code in (404, 422)
    assert "pwned" not in (home / "vault/Tasks.md").read_text()


def test_symlinks_refused(authed, agent_dir, home):
    target = home / "vault/Tasks.md"
    os.symlink(target, agent_dir / "link.md")
    assert authed.get(f"{URL}/code-reviewer/link.md").status_code == 422
    r = authed.put(f"{URL}/code-reviewer/link.md", json={"content": "pwned"}, headers={"If-Match": etag(target.read_text())})
    assert r.status_code == 422 and "pwned" not in target.read_text()
    names = [f["name"] for f in authed.get("/api/v1/sources/memory").json()["agents"][0]["files"]]
    assert "link.md" not in names


def test_symlinked_agent_folder_refused(authed, agent_dir, home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.md").write_text("secret")
    os.symlink(outside, agent_dir.parent / "evil-agent")
    assert authed.get(f"{URL}/evil-agent/a.md").status_code == 404
    assert "evil-agent" not in [a["agent"] for a in authed.get("/api/v1/sources/memory").json()["agents"]]


def test_size_limit(authed, agent_dir):
    cur = authed.get(f"{URL}/code-reviewer/vite-proxy.md").json()
    r = authed.put(f"{URL}/code-reviewer/vite-proxy.md", json={"content": "x" * 1_000_001}, headers={"If-Match": cur["etag"]})
    assert r.status_code == 422


def test_memory_folder_may_itself_be_a_symlink(settings, home, tmp_path):
    """e.g. ~/.claude/agent-memory -> a folder in a notes vault."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    real = tmp_path / "vault/agent-memory/Nexus"
    (real / "reviewer").mkdir(parents=True)
    (real / "reviewer/a.md").write_text("hi")
    link = tmp_path / "linked-memory"
    os.symlink(real, link)
    s = settings.model_copy(update={"paths": settings.paths.model_copy(update={"agent_memory": link})})
    c = TestClient(create_app(s), base_url="http://localhost")
    assert [a["agent"] for a in c.get("/api/v1/sources/memory").json()["agents"]] == ["reviewer"]
    assert c.get(f"{URL}/reviewer/a.md").json()["content"] == "hi"


def test_default_folder_follows_claude_home(settings, home):
    assert settings.paths.memory == home / ".claude/agent-memory"
