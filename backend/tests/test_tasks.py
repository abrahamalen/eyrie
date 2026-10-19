import pytest

FILE = (
    "# Personal tasks\n"
    "\n"
    "- [ ] Renew passport\n"
    "  - [ ] Book photo slot\n"
    "* [x] Dentist\n"
    "- [/] Half done\n"
    "\n"
    "Notes: keep this short.\n"
)


@pytest.fixture
def tasks_file(home):
    path = home / "vault/Personal/Tasks.md"
    path.write_text(FILE)
    return path


def snap(authed):
    return authed.get("/api/v1/tasks").json()


def test_parses_obsidian_checklists(authed, tasks_file):
    tasks = snap(authed)["tasks"]
    assert [(t["text"], t["done"]) for t in tasks] == [
        ("Renew passport", False), ("Book photo slot", False), ("Dentist", True), ("Half done", False)]


def test_toggle_edits_only_that_line(authed, tasks_file):
    s = snap(authed)
    dentist = next(t for t in s["tasks"] if t["text"] == "Dentist")
    r = authed.patch(f"/api/v1/tasks/{dentist['id']}", json={"done": False}, headers={"If-Match": s["etag"]})
    assert r.status_code == 200
    assert tasks_file.read_text() == FILE.replace("* [x] Dentist", "* [ ] Dentist")
    # id is stable across toggles
    assert any(t["id"] == dentist["id"] and not t["done"] for t in r.json()["tasks"])


def test_rename_keeps_indent_and_bullet(authed, tasks_file):
    s = snap(authed)
    sub = next(t for t in s["tasks"] if t["text"] == "Book photo slot")
    authed.patch(f"/api/v1/tasks/{sub['id']}", json={"text": "Book photo  slot  online"}, headers={"If-Match": s["etag"]})
    assert "  - [ ] Book photo slot online\n" in tasks_file.read_text()


def test_add_goes_after_last_task_and_keeps_notes(authed, tasks_file):
    s = snap(authed)
    r = authed.post("/api/v1/tasks", json={"text": "Back up Postgres"}, headers={"If-Match": s["etag"]})
    assert r.status_code == 200
    assert tasks_file.read_text() == FILE.replace("- [/] Half done\n", "- [/] Half done\n- [ ] Back up Postgres\n")


def test_delete_removes_one_line(authed, tasks_file):
    s = snap(authed)
    half = next(t for t in s["tasks"] if t["text"] == "Half done")
    authed.delete(f"/api/v1/tasks/{half['id']}", headers={"If-Match": s["etag"]})
    assert tasks_file.read_text() == FILE.replace("- [/] Half done\n", "")


def test_stale_etag_is_refused_and_file_untouched(authed, tasks_file):
    s = snap(authed)
    tasks_file.write_text(FILE + "- [ ] Added in Obsidian\n")
    edited = tasks_file.read_text()
    r = authed.post("/api/v1/tasks", json={"text": "mine"}, headers={"If-Match": s["etag"]})
    assert r.status_code == 409
    assert tasks_file.read_text() == edited
    assert r.json()["current"]["tasks"][-1]["text"] == "Added in Obsidian"


def test_missing_if_match_is_rejected(authed, tasks_file):
    assert authed.post("/api/v1/tasks", json={"text": "x"}).status_code == 422


def test_unknown_id_404_with_current_state(authed, tasks_file):
    s = snap(authed)
    r = authed.delete("/api/v1/tasks/deadbeef00", headers={"If-Match": s["etag"]})
    assert r.status_code == 404
    assert len(r.json()["current"]["tasks"]) == 4


def test_duplicate_texts_get_distinct_ids(authed, home):
    path = home / "vault/Personal/Tasks.md"
    path.write_text("- [ ] same\n- [ ] same\n")
    s = snap(authed)
    a, b = s["tasks"]
    assert a["id"] != b["id"]
    authed.patch(f"/api/v1/tasks/{b['id']}", json={"done": True}, headers={"If-Match": s["etag"]})
    assert path.read_text() == "- [ ] same\n- [x] same\n"


def test_first_add_creates_file(authed, home):
    path = home / "vault/Personal/Tasks.md"
    s = snap(authed)
    assert s == {"etag": "absent", "tasks": []}
    authed.post("/api/v1/tasks", json={"text": "first"}, headers={"If-Match": "absent"})
    assert path.read_text() == "# Personal tasks\n\n- [ ] first\n"


def test_crlf_and_no_trailing_newline_preserved(authed, home):
    path = home / "vault/Personal/Tasks.md"
    path.write_bytes(b"- [ ] a\r\nnote")
    s = snap(authed)
    authed.patch(f"/api/v1/tasks/{s['tasks'][0]['id']}", json={"done": True}, headers={"If-Match": s["etag"]})
    assert path.read_bytes() == b"- [x] a\r\nnote"


def test_empty_text_rejected(authed, tasks_file):
    s = snap(authed)
    assert authed.post("/api/v1/tasks", json={"text": "   "}, headers={"If-Match": s["etag"]}).status_code == 422
    assert tasks_file.read_text() == FILE


def test_write_keeps_file_mode_and_leaves_no_temp(authed, tasks_file):
    tasks_file.chmod(0o600)
    s = snap(authed)
    authed.post("/api/v1/tasks", json={"text": "x"}, headers={"If-Match": s["etag"]})
    assert tasks_file.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tasks_file.parent.iterdir()] == ["Tasks.md"]


def test_task_edits_are_audited_without_their_text(authed):
    cur = authed.get("/api/v1/tasks").json()
    r = authed.post("/api/v1/tasks", json={"text": "call the dentist"}, headers={"If-Match": cur["etag"]}).json()
    t = next(t for t in r["tasks"] if t["text"] == "call the dentist")
    authed.patch(f"/api/v1/tasks/{t['id']}", json={"done": True}, headers={"If-Match": r["etag"]})
    entries = authed.get("/api/v1/audit").json()
    assert [e["action"] for e in entries[:2]] == ["tasks.update", "tasks.add"]
    assert entries[0]["params"] == {"id": t["id"], "done": True, "text_changed": False}
    assert "dentist" not in str(entries)
