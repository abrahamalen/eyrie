# Packaging and releases (design)

Status: design, 2026-10-20. Prototype and code follow as separate PRs.

`docs/home-and-widget.md` §5 settled the shape: one installer per OS, holding the tray widget
(Tauri), the backend as a self-contained `eyrie-server` binary (PyInstaller, a Tauri
sidecar) and the built UI. This doc settles what's still open: how first launch installs the
service, versions, signing, updates and the release pipeline.

## 1. Goals

1. Someone without Python, Node or a checkout installs one file and gets Eyrie running in the
   background, the widget in the menu bar, and the first-run screen in the browser.
2. Upgrades keep `~/.eyrie` (token, usage history, audit log, config) and running sessions.
3. One tag builds every installer; the same tag publishes the `/eyrie` landing page artifact
   the website pins (alenabraham-site `docs/build.md`).
4. `make install` from a checkout keeps working, through the same service code.

5. Installs from the terminal on macOS and Linux, as well as from a downloaded package
   (§7.1), with ready `.deb` (Debian, Ubuntu) and `.rpm` (Fedora) packages.

Non-goals: Windows (deferred, §5.1 of the earlier doc), app stores, auto-installing
`tmux`/`claude`/`codex`/`gemini` (they're yours; missing ones are flagged, with how to
install).

## 2. The server binary

- `eyrie-server` is a PyInstaller **onefile** build of a small entry point
  (`backend/app/cli.py`):
  - `eyrie-server serve --port 8787` runs uvicorn on 127.0.0.1;
  - `eyrie-server service install|uninstall|status [--port]` manages the background service;
  - `eyrie-server --version`.
- **The service code moves into the package.** `scripts/service.py`'s logic (launchd agent,
  systemd user unit, login-shell PATH capture) becomes `app/service.py`, so the binary
  carries it. `make install` calls the same code through `python -m app.cli service install`.
  One implementation, two entry points.
- **Where things live in a packaged install:**
  - the service's program is the sidecar's real path inside the app: on macOS
    `Eyrie.app/Contents/MacOS/eyrie-server`, on Linux `/usr/lib/eyrie/eyrie-server`;
  - the UI is a Tauri resource, passed to the service as `EYRIE_SERVER__UI_DIR`;
  - config is `~/.eyrie/eyrie.toml` (already the default since #31).
- **Measured (prototype, 2026-10-20), PyInstaller 6.22.3, Python 3.12:**

  | | macOS arm64 | Debian 12 arm64 (container) |
  |---|---|---|
  | onefile size | 14 MB | 15 MB |
  | onedir size | 29 MB | 33 MB |
  | onefile `--version` / ready to serve | 10.7 s first run, 6.6 s after | 0.17 s |
  | onedir `--version` / ready to serve | 2.0 s first run, 0.97 s after | 0.07 s |
  | glibc needed | n/a | 2.35+ (Ubuntu 22.04, Debian 12, Fedora 41 and newer) |

  On macOS onefile unpacks itself on every start and the OS scans the fresh files, so it's
  6–10 s. **Decision: onedir everywhere** (one layout to reason about). Tauri's `externalBin`
  takes a single file, so the folder ships as a bundle **resource** and the widget starts
  `<resources>/eyrie-server/eyrie-server` itself; the service points at the same path.
  Built with `packaging/eyrie-server.spec` (hidden imports: uvicorn's and websockets' runtime
  plug-ins). Smoke-tested: `/api/v1/health`, `/summary`, `/meta`, the UI at `/`, and the
  terminal WebSocket handshake reaching the app.
- **Found by the prototype:** `websockets` wasn't in `requirements.txt` (only installed by hand
  in my venv), so a clean install had no WebSocket support and the browser terminal would
  fail at runtime; tests didn't notice because the test client has its own. Now pinned, with
  a test that it's installed.

## 3. First launch and upgrades

The widget owns the lifecycle, because it's what people launch:

1. The widget starts. If `GET /api/v1/health` doesn't answer, or `/api/v1/meta`'s version
   differs from the bundled sidecar's `--version`, it runs `eyrie-server service install`.
   Install is idempotent and rewrites the unit, so an upgrade repoints the service at the new
   binary and restarts it. Sessions survive, thanks to `AbandonProcessGroup` /
   `KillMode=process`.
2. With no config yet, the widget opens `http://127.0.0.1:8787/`, which redirects to first
   run (#31).
3. The widget's menu gets **Quit and remove service**, which runs `service uninstall`. The
   `.deb`/`.rpm` `prerm` does the same. Neither ever deletes `~/.eyrie`.

## 4. Versions

- **One version, in one place:** `VERSION` at the repo root. A `make version V=x.y.z`
  target writes it into `backend/app/__init__.py`, `widget/src-tauri/tauri.conf.json`,
  `widget/src-tauri/Cargo.toml` and `widget/package.json`.
- `make check` (and CI) fails if any of them disagree.
- Tags are `vX.Y.Z`. The release job refuses a tag that doesn't match `VERSION`.
- The first release is `v0.2.0` (0.1.0 is the dev line).

## 5. Signing

| Platform | Without signing | With signing |
|---|---|---|
| macOS | Gatekeeper blocks a downloaded unsigned app: "can't be opened". The workarounds are right-click → Open, or `xattr -dr com.apple.quarantine /Applications/Eyrie.app`. Fine for me, rough for anyone else | An Apple Developer ID ($99/year), signing plus notarization in CI (`APPLE_CERTIFICATE`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` secrets; Tauri's bundler does both). Opens normally |
| Linux | `.deb`/`.rpm` install fine unsigned; packages carry a sha256 in the release | Optional GPG signature on the checksums file |

**Decision (2026-10-20): `v0.2.0` ships unsigned.** Nobody installing Eyrie signs in to
anything either way; signing only needs a developer account on the build side. Gatekeeper
only checks files a browser downloaded (they carry a quarantine attribute), so the terminal
installs in §7.1 (`curl`, Homebrew) run as they are. A `.dmg` downloaded in a browser needs a
one-time right-click → Open, which the release notes and the landing page explain. Sign once
browser downloads are how most people install.

## 6. Updates

- **v0.2 (decided):** no auto-update. The widget checks the GitHub releases API at most once
  a day (one GET, no account) and shows "Update available: v0.x" with a link and the one-line
  terminal command. It needs no signing keys and has no moving parts.
- **Later:** Tauri's updater plugin (signed update manifest on GitHub Releases, ed25519 key
  as a CI secret) once releases are regular.

## 7. Release pipeline

`.github/workflows/release.yml`, triggered by a `v*` tag. Like `ci.yml`, it's skipped on the
`alenabraham-qure` fork and runs on the public `abrahamalen/eyrie`.

| Job | Runner | Produces |
|---|---|---|
| macOS arm64 | `macos-14` | `Eyrie_X.Y.Z_aarch64.dmg` |
| macOS x86_64 | `macos-15-intel` (macos-13 was retired Dec 2025; Intel runners end fall 2027) | `Eyrie_X.Y.Z_x64.dmg` (PyInstaller can't build universal binaries from one runner) |
| Linux x86_64 | `ubuntu-22.04` (older glibc, so the binary runs on newer distros) | `.deb` (Debian, Ubuntu), `.rpm` (Fedora), `.AppImage`, `eyrie-server-X.Y.Z-linux-x86_64.tar.gz` |
| Linux arm64 | `ubuntu-22.04-arm` | `.deb`, `.rpm`, `eyrie-server-X.Y.Z-linux-aarch64.tar.gz` |
| Landing page | `ubuntu-24.04` | `eyrie-landing-X.Y.Z.tar.gz` for alenabraham.me/eyrie (once `landing/` exists) |
| Publish | after all | a GitHub release with every artifact and `SHA256SUMS` |

Each build job:
1. `make check`;
2. build the UI;
3. build `eyrie-server` with PyInstaller (pinned);
4. `tauri build` with the sidecar as `externalBin`;
5. a **smoke test** of the artifact:
   - macOS: mount the dmg and run `Eyrie.app/Contents/MacOS/eyrie-server --version`, then `serve` and curl `/api/v1/health` and `/`;
   - Linux: install in clean `debian:12`, `ubuntu:24.04` and `fedora:41` containers (`apt install ./eyrie.deb`, `dnf install ./eyrie.rpm`) and do the same, so dependencies are checked on each distro family.

### 7.1 Installing from the terminal

Two ways, both verifying checksums and both ending with `eyrie-server service install`:

1. **One-line script**, macOS and Linux:

   ```
   curl -fsSL https://alenabraham.me/eyrie/install.sh | sh
   ```

   - The script is served from the website (a copy of `scripts/install.sh` from the pinned release), so the URL stays stable.
   - It detects OS and architecture, downloads the matching release artifact from GitHub, and checks it against `SHA256SUMS`. Then:
     - **macOS:** copies `Eyrie.app` to `~/Applications`;
     - **Debian/Ubuntu:** `sudo apt install ./eyrie_X.Y.Z_amd64.deb`;
     - **Fedora:** `sudo dnf install ./eyrie-X.Y.Z.x86_64.rpm`;
     - **anything else, or `--user`:** unpacks the `eyrie-server` tarball into `~/.local/lib/eyrie` and links `~/.local/bin/eyrie-server`, with no root needed.
   - It installs the service and prints the URL.
   - Flags: `--version vX.Y.Z` pins a version; `--server-only` skips the widget, for machines without a desktop (servers, SSH boxes; you reach the UI over an SSH tunnel); `--uninstall` removes the service and package, never `~/.eyrie`.
   - The script is short and readable, and the docs show how to download and read it before running it.
2. **Homebrew** (macOS and Linux), from a tap repo `abrahamalen/homebrew-eyrie` that the release job updates:

   ```
   brew install abrahamalen/eyrie/eyrie          # app + widget (cask, macOS)
   brew install abrahamalen/eyrie/eyrie-server   # server only (formula, macOS + Linux)
   ```

   - Formula installs aren't quarantined, so unsigned binaries run.
   - The cask sets `quarantine: false` via its `postflight` (`xattr -dr`), with a note saying so.

apt and dnf **repositories** (`apt install eyrie` with no download step) are deferred. They need a signed repo hosted somewhere. The `.deb`/`.rpm` from releases, plus the script, cover installing for now.

## 8. Plan (one PR each)

1. **Prototype:** build `eyrie-server` with PyInstaller locally on macOS and in an
   Ubuntu container. Check its size, start time, and that `serve` passes the API tests'
   smoke subset. Measure, then confirm onefile against onedir.
2. **Code (done):** `app/cli.py` plus `app/service.py`, with `scripts/service.py` folded in;
   `make install` keeps working. Packaged installs pass `--ui-dir`; the service runs
   `<program> serve --port N`.
3. **Code (done):** the widget ships `eyrie-server` (onedir) and the UI as resources, via
   `src-tauri/tauri.bundle.json` so `make widget` dev builds don't need them. On launch it
   installs the service when Eyrie doesn't answer or runs another version, opens `/setup` once
   if unconfigured, checks GitHub releases daily, and adds "Quit and remove service".
   `make widget-dist` = `make server-dist` + `tauri build`; the macOS `.dmg` is built and
   checked locally (app 53 MB, dmg 23 MB). The `.deb`/`.rpm` builds move to the release job's
   distro containers (step 5), where they're installed and smoke-tested.
4. **Code (done):** `VERSION`, `make version V=x.y.z` (`scripts/version.py`, 7 copies:
   backend, tauri.conf.json, Cargo.toml/.lock, widget package.json/-lock), and `make
   version-check` as the first step of `make check`.
5. **Code (done, untested until the first tag):** `.github/workflows/release.yml`: verify
   (tag = `v$(cat VERSION)`, `make check`) → build (macOS arm64/x64, Linux x64/arm64; the macOS
   dmg is smoke-tested in the job) → install-test (`.deb` on debian:12 and ubuntu:24.04, `.rpm`
   on fedora:41; each `serve` + `/health`, `/meta`, `/`) → publish (`SHA256SUMS`, notes,
   pre-release for tags with `-`). Lints clean with actionlint 1.7.9 (1.7.7 doesn't know `macos-15-intel`). First real run: a
   `v0.2.0-rc1` tag on the personal repo. Watch: RPM versions can't contain `-`.
6. **Code (install script done):** `scripts/install.sh`, POSIX sh, shellcheck clean. Tested
   against a local mirror of the rc1 release: `.deb` on debian:12, `.rpm` on fedora:41,
   `--server-only` tarball on ubuntu:24.04, a tampered file refused on checksum, `--uninstall`
   (package gone, `~/.eyrie` kept), and a macOS `--dry-run`. Shipped inside the landing tarball
   (so the site serves `/eyrie/install.sh`) and attached to each release. The Homebrew tap
   (`abrahamalen/homebrew-eyrie`) is still to do.

## 9. Decisions (2026-10-20)

1. **macOS signing:** unsigned for v0.2 (§5). No sign-in for users either way.
2. **Update check:** yes, a daily GitHub releases check in the widget (§6).
3. **Linux:** `.deb` for Debian/Ubuntu and `.rpm` for Fedora, x86_64 and arm64, each
   smoke-tested on its distro; plus terminal installs on macOS and Linux (§7.1).
