# PyInstaller spec for eyrie-server (docs/packaging.md §2). Build from the repo root:
#   pyinstaller --distpath build/dist --workpath build/work packaging/eyrie-server.spec
# ONEFILE=0 in the environment builds a folder instead (faster start, more files).
import os

from PyInstaller.utils.hooks import collect_submodules

onefile = os.environ.get("ONEFILE", "1") == "1"
# uvicorn picks its loop, protocol and lifespan implementations by name at runtime, and
# websockets loads its server implementation the same way; analysis can't see either.
hidden = collect_submodules("uvicorn") + collect_submodules("websockets")

a = Analysis(
    ["../backend/app/cli.py"],
    pathex=["../backend"],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "httpx"],
)
pyz = PYZ(a.pure)

if onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="eyrie-server", console=True, strip=True, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="eyrie-server", console=True, strip=True, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="eyrie-server", strip=True, upx=False)
