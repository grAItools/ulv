.PHONY: help test test-all lint fmt fmt-check verify dev clean docs docs-build docs-serve docs-check

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n\nTargets:\n"} \
	/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

test:  ## Run fast unit tests
	uv run pytest -q

test-all: test  ## Run the full suite (override to add integration/e2e)
	@echo "test-all: extend this target with integration suites as needed"

lint:  ## Run static checks (does not auto-fix)
	uv run ruff check .

fmt:  ## Auto-format the codebase
	uv run ruff format .

fmt-check:  ## Check formatting without modifying files (CI-safe)
	uv run ruff format --check .

verify:  ## What the agent runs before claiming done
	@./scripts/verify.sh

dev:  ## Run the local dev workflow (override per-project)
	@echo "dev: override this target to start your dev server / watcher"

clean:  ## Remove generated artefacts (override per-project)
	@echo "clean: override this target to remove build/ dist/ etc."

docs:  ## Build user documentation
	uv run python scripts/gen_cli_reference.py
	uv run zensical build

docs-build:  ## Build the docs site without regenerating references (CI-safe)
	uv run zensical build

docs-serve:  ## Serve documentation locally for preview
	uv run zensical serve

docs-check:  ## Check if documentation is up to date
	uv run python scripts/check_docs_staleness.py
