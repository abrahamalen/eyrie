"""`eyrie-server`: the entry point of the packaged backend (docs/packaging.md §2).

    eyrie-server serve [--port 8787]
    eyrie-server --version

Service install/uninstall joins here in the next step, moved from scripts/service.py.
"""
import argparse


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="eyrie-server", description="Eyrie's backend")
    p.add_argument("--version", action="store_true", help="print the version and exit")
    sub = p.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the API and UI on 127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    a = p.parse_args(argv)
    if a.version:
        from app import __version__
        print(__version__)
    elif a.command == "serve":
        import uvicorn

        from app.main import create_app
        # Loopback only, always: Eyrie can run commands as you (README "Security").
        uvicorn.run(create_app, factory=True, host="127.0.0.1", port=a.port)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
