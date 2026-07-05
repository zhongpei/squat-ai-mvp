.PHONY: install test dev clean lint fmt run server-up server-down docker-up docker-down

# ── Environment ──────────────────────────────────────────────────────
PYTHON ?= python3.11
UV     ?= uv
PYTEST ?= $(UV) run pytest

# ── Install ──────────────────────────────────────────────────────────
install: .venv/bin/activate
.venv/bin/activate: pyproject.toml
	test -d .venv || $(UV) venv --python $(PYTHON)
	$(UV) sync --dev
	touch "$@"

.PHONY: sync
sync:
	$(UV) sync --dev

# ── Tests ────────────────────────────────────────────────────────────
test: .venv/bin/activate
	$(PYTEST) -v --tb=short

test-quiet: .venv/bin/activate
	$(PYTEST) -q --tb=no

test-coverage: .venv/bin/activate
	$(UV) pip install pytest-cov
	$(PYTEST) --cov=squat_ai_mvp --cov-report=term --cov-report=html

# ── Dev server (re-run tests on file change) ─────────────────────────
dev: install
	$(UV) run ptw --config pytest.ini tests -c -- -v --tb=short

.PHONY: test-watch
test-watch: .venv/bin/activate
	$(UV) run ptw --config pytest.ini tests -v --tb=short

# ── Lint & Format ────────────────────────────────────────────────────
lint: .venv/bin/activate
	$(UV) pip install ruff
	$(UV) run ruff check .

fmt: .venv/bin/activate
	$(UV) pip install ruff
	$(UV) run ruff format .

check: .venv/bin/activate
	$(UV) run ruff check .
	$(UV) run ruff format --check .

# ── Run app ──────────────────────────────────────────────────────────
run: .venv/bin/activate
	$(UV) run python run.py $(ARGS)

# ── Docker (MediaMTX stream gateway) ─────────────────────────────────
docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Clean ────────────────────────────────────────────────────────────
clean:
	rm -rf .venv/
	rm -rf __pycache__/ .ruff_cache/ .pytest_cache/ .hypothesis/
	rm -rf *.egg-info/ .eggs/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

clean-all: clean
	rm -rf sessions/
	rm -f uv.lock

# ── Help ─────────────────────────────────────────────────────────────
help:
	@echo "────────────────────────────────────────────────────────"
	@echo "squat-ai-mvp  Makefile"
	@echo "────────────────────────────────────────────────────────"
	@echo "make install       Create venv + install all deps"
	@echo "make sync          Sync deps from pyproject.toml"
	@echo "make test          Run tests (verbose)"
	@echo "make test-quiet    Run tests (quiet)"
	@echo "make dev           Watch mode: re-run tests on change"
	@echo "make lint          Run ruff linter"
	@echo "make fmt           Run ruff formatter"
	@echo "make check         Lint + format check"
	@echo "make run ARGS=...  Run app (e.g. ARGS='--tts print')"
	@echo "make docker-up     Start MediaMTX gateway"
	@echo "make docker-down   Stop MediaMTX gateway"
	@echo "make clean         Remove venv + caches"
	@echo "────────────────────────────────────────────────────────"
