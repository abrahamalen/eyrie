import typing

import pytest

from app.tools import TOOLS, ToolId

UUID = "516f62bf-361d-40b5-9698-9d33633899d1"


def test_tool_ids_follow_the_registry():
    assert typing.get_args(ToolId) == tuple(TOOLS)


@pytest.mark.parametrize("tool", [t for t in TOOLS.values() if t.sessions], ids=lambda t: t.id)
def test_session_argv_is_always_two_or_more_items(tool):
    # tmux only execs without `sh -c` when the program is 2+ argv items.
    for mode in tool.sessions.modes:
        conv = UUID if tool.sessions.wants_conversation_id(mode) else None
        argv = tool.sessions.argv("/bin/x", mode, "/p", UUID if mode == "resume" else None, conv)
        assert len(argv) >= 2 and argv[0] == "/bin/x" and all(isinstance(a, str) and a for a in argv)


def test_every_tool_says_what_breaks_without_it():
    assert all(t.title and t.binary and t.needs for t in TOOLS.values())
