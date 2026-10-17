SHELL := /bin/bash
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

.DEFAULT_GOAL := dev
.PHONY: help setup dev backend frontend test build lint clean

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

build: frontend/node_modules/.stamp ## Typecheck + production build of the UI
	cd frontend && npm run build

lint: frontend/node_modules/.stamp ## Lint the UI
	cd frontend && npm run lint

clean: ## Remove venv, node_modules, dist
	rm -rf backend/.venv frontend/node_modules frontend/dist
