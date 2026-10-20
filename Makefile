SHELL := /bin/bash
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173
# The installed (background) Eyrie, separate from `make dev` so both can run at once.
INSTALL_PORT ?= 8787
VERSION := $(shell cat VERSION)

.DEFAULT_GOAL := dev
.PHONY: help setup dev backend frontend test build lint clean types types-check check serve install uninstall status logs widget widget-dist widget-check server-dist version version-check landing-dev landing-build landing-dist

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

backend/.venv/.stamp: backend/requirements.txt backend/requirements-dev.txt
	test -d backend/.venv || python3 -m venv backend/.venv
	backend/.venv/bin/pip install -q -r backend/requirements-dev.txt
	@touch $@

frontend/node_modules/.stamp: frontend/package-lock.json
	cd frontend && npm ci
	@touch $@

setup: backend/.venv/.stamp frontend/node_modules/.stamp ## Install backend + frontend deps

backend: backend/.venv/.stamp ## Run API only (127.0.0.1:8000)
	cd backend && .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port $(BACKEND_PORT) --reload

frontend: frontend/node_modules/.stamp ## Run UI only (localhost:5173)
	cd frontend && EYRIE_BACKEND_PORT=$(BACKEND_PORT) npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT)

dev: setup ## Run API + UI together, then open http://localhost:5173
	@echo "Eyrie -> http://localhost:$(FRONTEND_PORT)  (API 127.0.0.1:$(BACKEND_PORT))"
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory backend & \
	$(MAKE) --no-print-directory frontend & \
	wait

test: backend/.venv/.stamp ## Run backend tests
	cd backend && .venv/bin/pytest -q

# TypeScript types for the API, generated from the backend's response models. The generator
# runs via npx in its own pinned environment (it needs TypeScript 5; the app uses 6).
OPENAPI_TS = npx --yes -p typescript@5.9.3 -p openapi-typescript@7.13.0 openapi-typescript
GENERATED = frontend/src/api/generated.ts

types: backend/.venv/.stamp ## Regenerate frontend/src/api/generated.ts from the API
	@tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	(cd backend && .venv/bin/python -m app.openapi) > "$$tmp/openapi.json" && \
	$(OPENAPI_TS) "$$tmp/openapi.json" -o $(GENERATED) >/dev/null && \
	echo "Wrote $(GENERATED)"

types-check: backend/.venv/.stamp ## Fail if generated.ts is out of date with the API
	@tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	(cd backend && .venv/bin/python -m app.openapi) > "$$tmp/openapi.json" && \
	$(OPENAPI_TS) "$$tmp/openapi.json" -o "$$tmp/generated.ts" >/dev/null && \
	if diff -q "$$tmp/generated.ts" $(GENERATED) >/dev/null; then echo "generated.ts is up to date"; \
	else echo "generated.ts is stale: run 'make types' and commit it"; diff -u $(GENERATED) "$$tmp/generated.ts" | head -40; exit 1; fi

version-check: ## Fail if a version copy differs from VERSION
	@python3 scripts/version.py check

version: ## Set the version everywhere: make version V=0.2.0
	@test -n "$(V)" || { echo "usage: make version V=x.y.z"; exit 1; }
	python3 scripts/version.py set $(V)

check: version-check test types-check build lint landing-build ## Everything CI runs

build: frontend/node_modules/.stamp ## Typecheck + production build of the UI
	cd frontend && npm run build

lint: frontend/node_modules/.stamp ## Lint the UI
	cd frontend && npm run lint

# The public landing page (alenabraham.me/eyrie/): its own small Vite app, sharing the UI's
# tokens and Logo. The website pins the release tarball by sha256 (docs/home-and-widget.md §3.2).
landing/node_modules/.stamp: landing/package-lock.json
	cd landing && npm ci
	@touch $@

landing-dev: landing/node_modules/.stamp ## Run the landing page with hot reload (http://localhost:5174/eyrie/)
	cd landing && npm run dev -- --host 127.0.0.1 --port 5174

landing-build: landing/node_modules/.stamp ## Typecheck, lint and build the landing page into landing/dist/
	cd landing && npm run lint && npm run build

landing-dist: landing-build ## Package the landing page as build/eyrie-landing-$(VERSION).tar.gz (index.html at the root)
	mkdir -p build
	cp scripts/install.sh landing/dist/install.sh  # served as alenabraham.me/eyrie/install.sh
	COPYFILE_DISABLE=1 tar -C landing/dist -czf build/eyrie-landing-$(VERSION).tar.gz $$(cd landing/dist && ls -A)
	@echo "Wrote build/eyrie-landing-$(VERSION).tar.gz"

serve: setup build ## Run the built app in the foreground on 127.0.0.1:$(INSTALL_PORT) (UI + API)
	@echo "Eyrie -> http://127.0.0.1:$(INSTALL_PORT)"
	cd backend && .venv/bin/python -m app.cli serve --port $(INSTALL_PORT)

install: setup build ## Run Eyrie in the background at login (launchd on macOS, systemd user unit on Linux)
	cd backend && .venv/bin/python -m app.cli service install --port $(INSTALL_PORT) $(if $(DRY_RUN),--dry-run)

uninstall: ## Remove the background agent (leaves tmux sessions running)
	cd backend && .venv/bin/python -m app.cli service uninstall $(if $(DRY_RUN),--dry-run)

status: ## Is the background agent installed and answering?
	@cd backend && .venv/bin/python -m app.cli service status

logs: ## Follow the background agent's log
	tail -f ~/.eyrie/logs/eyrie.log

# The top-bar widget (Tauri; needs Rust: https://rustup.rs). It talks to the installed Eyrie
# on 127.0.0.1:$(INSTALL_PORT); set EYRIE_URL to point it elsewhere.
# rustup's default location is added here too, so a shell opened before Rust was installed works.
RUST_PATH = PATH="$(HOME)/.cargo/bin:$$PATH"

widget-check:
	@$(RUST_PATH) command -v cargo >/dev/null || { echo "Rust isn't installed: https://rustup.rs"; exit 1; }

widget: build widget-check ## Run the top-bar widget (debug build) against the installed Eyrie
	cd widget && npm ci --silent && $(RUST_PATH) npx tauri build --debug --no-bundle && ./src-tauri/target/debug/eyrie-widget

server-dist: setup ## Build the packaged backend (build/dist/eyrie-server/, PyInstaller onedir)
	backend/.venv/bin/pip install -q -r backend/requirements-build.txt
	ONEFILE=0 backend/.venv/bin/pyinstaller -y --log-level WARN --distpath build/dist --workpath build/work packaging/eyrie-server.spec
	build/dist/eyrie-server/eyrie-server --version

widget-dist: build server-dist widget-check ## Build Eyrie for this OS: the app with its server + UI bundled (.app/.dmg, .deb/.rpm/AppImage)
	cd widget && npm ci --silent && $(RUST_PATH) CI=true npx tauri build --config src-tauri/tauri.bundle.json

clean: ## Remove venv, node_modules, dist, widget build output
	rm -rf backend/.venv frontend/node_modules frontend/dist landing/node_modules landing/dist widget/node_modules widget/src-tauri/target build
