"""One version for everything (docs/packaging.md §4): VERSION at the repo root, copied into
each place a build reads it from. Stdlib only.

    python3 scripts/version.py check          # fail if any copy differs from VERSION
    python3 scripts/version.py set 0.2.0      # write VERSION and every copy
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")

# (file, pattern whose group 2 is the version); each must match exactly once.
COPIES = [
    ("backend/app/__init__.py", r'(__version__ = ")([^"]+)(")'),
    ("widget/src-tauri/tauri.conf.json", r'(\n  "version": ")([^"]+)(")'),
    ("widget/src-tauri/Cargo.toml", r'(\[package\]\nname = "eyrie-widget"\nversion = ")([^"]+)(")'),
    ("widget/src-tauri/Cargo.lock", r'(name = "eyrie-widget"\nversion = ")([^"]+)(")'),
    ("widget/package.json", r'(\n  "version": ")([^"]+)(")'),
    ("widget/package-lock.json", r'(\n  "version": ")([^"]+)(")'),
    ("widget/package-lock.json", r'(\n    "": \{\n      "name": "[^"]+",\n      "version": ")([^"]+)(")'),
]


def current() -> str:
    return (ROOT / "VERSION").read_text().strip()


def found() -> list[tuple[str, str | None]]:
    out = []
    for path, pattern in COPIES:
        hits = re.findall(pattern, (ROOT / path).read_text())
        out.append((path, hits[0][1] if len(hits) == 1 else None))
    return out


def check() -> int:
    want = current()
    bad = [(p, v) for p, v in found() if v != want]
    for p, v in bad:
        print(f"{p}: {v or 'version not found exactly once'} (VERSION is {want})")
    if not bad:
        print(f"version {want} everywhere")
    return 1 if bad else 0


def set_version(v: str) -> int:
    if not SEMVER.match(v):
        print(f"not a version: {v}")
        return 1
    (ROOT / "VERSION").write_text(v + "\n")
    for path, pattern in COPIES:
        f = ROOT / path
        text, n = re.subn(pattern, lambda m: m.group(1) + v + m.group(3), f.read_text(), count=1)
        if n != 1:
            print(f"{path}: version not found")
            return 1
        f.write_text(text)
    return check()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["check"]:
        sys.exit(check())
    if len(args) == 2 and args[0] == "set":
        sys.exit(set_version(args[1]))
    sys.exit(__doc__)
