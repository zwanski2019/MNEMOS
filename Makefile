# MNEMOS — reproducible entrypoints.
# `make demo` must provision, seed, and run an end-to-end scenario with env vars only.

.PHONY: help install dev build provision seed demo test clean

help:
	@echo "MNEMOS targets:"
	@echo "  install    Install web + workspace deps (pnpm)"
	@echo "  dev        Run the Mission Control UI locally (:3000)"
	@echo "  build      Build the web app"
	@echo "  provision  [P6] Stand up CRDB Cloud + AWS via ccloud/SAM"
	@echo "  seed       [P8] Load the authorized sandbox target"
	@echo "  demo       [P8] Full end-to-end recon cycle against the sandbox"
	@echo "  test       Run unit tests across packages"

install:
	pnpm install

dev:
	pnpm dev

build:
	pnpm build

# --- Not yet implemented (tracked in CLAUDE.md §9) ---
provision:
	@echo "TODO(P6): infra/ccloud provisioning + migrations"; exit 1

seed:
	@echo "TODO(P8): scripts/seed_sandbox.py"; exit 1

demo:
	@echo "TODO(P8): end-to-end sandbox recon cycle"; exit 1

test:
	@echo "TODO: wire package test suites"; exit 0

clean:
	rm -rf apps/web/.next node_modules apps/web/node_modules
