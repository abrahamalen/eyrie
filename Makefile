SHELL := /bin/bash
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

.DEFAULT_GOAL := dev
.PHONY: help setup dev backend frontend build lint clean

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

backend/.venv/.stamp: backend/requirements.txt
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -q -r backend/requirements.txt
	@touch $@

frontend/node_modules/.stamp: frontend/package-lock.json
	cd frontend && npm ci
	@touch $@

setup: backend/.venv/.stamp frontend/node_modules/.stamp ## Install backend + frontend deps

backend: backend/.venv/.stamp ## Run API only (localhost:8000)
	cd backend && .venv/bin/uvicorn app.main:app --port $(BACKEND_PORT) --reload

frontend: frontend/node_modules/.stamp ## Run UI only (localhost:5173)
	cd frontend && npm run dev -- --port $(FRONTEND_PORT)

dev: setup ## Run API + UI together, then open http://localhost:5173
	@echo "Eyrie -> http://localhost:$(FRONTEND_PORT)  (API :$(BACKEND_PORT))"
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory backend & \
	$(MAKE) --no-print-directory frontend & \
	wait

build: frontend/node_modules/.stamp ## Typecheck + production build of the UI
	cd frontend && npm run build

lint: frontend/node_modules/.stamp ## Lint the UI
	cd frontend && npm run lint

clean: ## Remove venv, node_modules, dist
	rm -rf backend/.venv frontend/node_modules frontend/dist
