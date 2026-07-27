# MNEMOS — reproducible entrypoints.
# `make demo` provisions, seeds, and runs an end-to-end scenario from env vars only.

PY      ?= .venv/bin/python
PIP     ?= uv pip install --python $(PY)
COMPOSE ?= docker compose

# Local default; override with the CockroachDB Cloud connection string.
export DATABASE_URL ?= postgresql://root@localhost:26257/mnemos?sslmode=disable

.PHONY: help install dev build db-up db-down migrate demo demo-cloud gateway test \
        verify-invariants lint clean

help:
	@echo "MNEMOS targets:"
	@echo "  install            Install web + python workspace deps"
	@echo "  db-up              Start CockroachDB + NATS + MinIO locally"
	@echo "  migrate            Apply the memory schema (idempotent)"
	@echo "  demo               Full two-pass recon cycle — the thesis, in one command"
	@echo "  demo-cloud         Same, against CockroachDB Cloud + Bedrock (needs creds)"
	@echo "  gateway            Run the FastAPI gateway on :8080"
	@echo "  dev                Run Mission Control locally (:3000)"
	@echo "  test               Full test suite (needs db-up)"
	@echo "  verify-invariants  Prove the append-only guarantees from outside the app"
	@echo "  db-down            Stop local infrastructure"

install:
	pnpm install
	uv venv .venv
	$(PIP) -e packages/memory -e packages/recon -e apps/gateway
	$(PIP) pytest

dev:
	pnpm dev

build:
	pnpm build

db-up:
	$(COMPOSE) up -d
	@echo "waiting for CockroachDB…"
	@until $(COMPOSE) exec -T crdb ./cockroach sql --insecure -e "SELECT 1" >/dev/null 2>&1; \
		do sleep 1; done
	@echo "CockroachDB ready on :26257 (console :8081)"

db-down:
	$(COMPOSE) down

migrate:
	$(PY) -c "from mnemos_memory import migrate; print('applied:', ', '.join(migrate()))"

# The demo runs offline by default so a fresh clone works with no cloud account.
demo:
	MNEMOS_EMBEDDER=$${MNEMOS_EMBEDDER:-auto} MNEMOS_ANALYST=$${MNEMOS_ANALYST:-auto} \
		$(PY) scripts/demo.py --reset

# Explicitly the production path: CockroachDB Cloud + Bedrock Titan + Claude.
demo-cloud:
	@test -n "$$DATABASE_URL" || (echo "set DATABASE_URL to your CockroachDB Cloud DSN"; exit 1)
	MNEMOS_EMBEDDER=bedrock MNEMOS_ANALYST=bedrock $(PY) scripts/demo.py --reset

gateway:
	$(PY) -m uvicorn mnemos_gateway.app:app --host 0.0.0.0 --port 8080

test:
	$(PY) -m pytest tests/ -q

verify-invariants:
	$(PY) -m pytest tests/test_invariants.py -q -k "append_only or fails_closed or ceiling"

lint:
	$(PY) -m compileall -q packages apps/gateway scripts

clean:
	rm -rf apps/web/.next node_modules apps/web/node_modules .venv
