"""`eyrie-server`: the entry point of the packaged backend (docs/packaging.md §2), and of
`make install` from a checkout (`python -m app.cli`).

    eyrie-server serve [--port 8787]
    eyrie-server service install [--port 8787] [--ui-dir DIR] [--dry-run]
    eyrie-server service uninstall [--dry-run]
    eyrie-server service status
    eyrie-server --version
"""
import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="eyrie-server", description="Eyrie's backend")
    p.add_argument("--version", action="store_true", help="print the version and exit")
    sub = p.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the API and UI on 127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    svc = sub.add_parser("service", help="run Eyrie in the background at login (launchd / systemd user unit)")
    svc.add_argument("action", choices=["install", "uninstall", "status"])
    svc.add_argument("--port", type=int, default=8787)
    svc.add_argument("--ui-dir", type=Path, help="the built UI to serve (packaged installs)")
    svc.add_argument("--dry-run", action="store_true", help="print what would be written and run")
    a = p.parse_args(argv)
    if a.version:
        from app import __version__
        print(__version__)
    elif a.command == "serve":
        import uvicorn

        from app.main import create_app
        # Loopback only, always: Eyrie can run commands as you (README "Security").
        uvicorn.run(create_app, factory=True, host="127.0.0.1", port=a.port)
    elif a.command == "service":
        from app import service
        if a.action == "install":
            service.install(a.port, a.dry_run, a.ui_dir)
        elif a.action == "uninstall":
            service.uninstall(a.dry_run)
        else:
            service.status()
    else:
        p.print_help()


if __name__ == "__main__":
    main()
