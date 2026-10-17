"""Print Eyrie's OpenAPI spec (stable key order) without touching real state:
`python -m app.openapi > openapi.json`. Used by `make types`."""
import json
import sys
import tempfile
from pathlib import Path

from app.config import Paths, Settings
from app.main import create_app


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(paths=Paths(data_dir=Path(tmp), vault=Path(tmp), claude_home=Path(tmp),
                                        claude_json=Path(tmp) / ".claude.json", codex_home=Path(tmp)))
        spec = create_app(settings).openapi()
    json.dump(spec, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
