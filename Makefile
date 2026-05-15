PY := .venv/bin/python
PYTEST := $(PY) -m pytest

.PHONY: test test-unit test-integration test-e2e test-all test-fast help \
        web-install web-dev web-typecheck web-insights ledger-dry-run

help:
	@echo "Tests:"
	@echo "  test-unit         Run unit tests (offline, < 30s)"
	@echo "  test-integration  Run integration tests (in-process, < 2min)"
	@echo "  test-e2e          Run e2e tests (live network, may be flaky)"
	@echo "  test-fast         test-unit + test-integration (no network)"
	@echo "  test-all          Everything"
	@echo "  test              Alias for test-fast"
	@echo ""
	@echo "Frontend (phase-detector):"
	@echo "  web-install       npm install in web/phase-detector"
	@echo "  web-typecheck     tsc --noEmit in web/phase-detector"
	@echo "  web-dev           Start Next.js dev server on :3000 (mock data)"
	@echo "  web-insights      Boot the dev server and open /insights"
	@echo ""
	@echo "Operational:"
	@echo "  ledger-dry-run    Print what aggregate-transfer-ledger.mjs would write"

test: test-fast

test-unit:
	$(PYTEST) v4/tests/sanity -m sanity -q

test-integration:
	$(PYTEST) v4/tests/integration v4/product/d1_phase_detector/tests v4/product/d1_phase_detector/api/tests -q

test-e2e:
	$(PYTEST) tests/e2e -m e2e -v

test-fast:
	$(PYTEST) -m "not e2e" -q

test-all:
	$(PYTEST) -v

web-install:
	cd web/phase-detector && npm install --no-audit --no-fund

web-typecheck:
	cd web/phase-detector && npx tsc --noEmit

web-dev:
	cd web/phase-detector && NEXT_PUBLIC_USE_MOCK=true npm run dev

web-insights:
	@echo "Booting dev server at http://localhost:3000/insights …"
	@echo "Press Ctrl+C to stop."
	cd web/phase-detector && NEXT_PUBLIC_USE_MOCK=true npm run dev

ledger-dry-run:
	node scripts/aggregate-transfer-ledger.mjs --dry-run
