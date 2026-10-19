import importlib.util

from app import __version__
from app.cli import main


def test_websocket_library_installed():
    # uvicorn serves the browser terminal only with a WebSocket implementation installed;
    # the test client has its own, so without this check a clean install could ship
    # with a terminal that fails at runtime.
    assert importlib.util.find_spec("websockets") is not None


def test_cli_version(capsys):
    main(["--version"])
    assert capsys.readouterr().out.strip() == __version__
