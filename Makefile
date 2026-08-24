.PHONY: venv install dev run test test-fast test-ui test-catalog test-smoke test-match crawl-ts crawl-datasheets crawl-peerless crawl-monacor crawl-sica crawl-faitalpro crawl-ciare catalog-plan catalog-complete lint format clean

VENV_DIR := .venv
PYTHON  := python3

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "Virtual environment created at $(VENV_DIR)."
	@echo "Activate with: source $(VENV_DIR)/bin/activate"

install: venv
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install -r requirements.txt
	@echo "Dependencies installed."

dev: install
	$(VENV_DIR)/bin/pip install ruff
	@echo "Dev tooling installed (ruff)."

run:
	./run.sh

test:
	$(VENV_DIR)/bin/python tests/test_all.py

test-fast:
	$(VENV_DIR)/bin/python tests/test_all.py --fast

test-smoke:
	$(VENV_DIR)/bin/python tests/test_all.py --smoke

test-ui:
	$(VENV_DIR)/bin/python tests/test_all.py --ui

test-catalog:
	$(VENV_DIR)/bin/python tests/test_catalog.py
	$(VENV_DIR)/bin/python tests/test_crawler_registry.py

test-match:
	@if [ -z "$(MATCH)" ]; then echo "Usage: make test-match MATCH='acoustic-load smoke'"; exit 2; fi
	$(VENV_DIR)/bin/python tests/test_all.py --match "$(MATCH)"

crawl-ts:
	@if [ -z "$(ARGS)" ]; then echo "Usage: make crawl-ts ARGS='--seed URL --fresh --dry-run'"; exit 2; fi
	$(VENV_DIR)/bin/python tools/crawl_thiele_small.py $(ARGS)

crawl-datasheets:
	@if [ -z "$(ARGS)" ]; then echo "Usage: make crawl-datasheets ARGS='--seed PRODUCT_URL'"; exit 2; fi
	$(VENV_DIR)/bin/python tools/crawl_driver_datasheets.py $(ARGS)

crawl-peerless:
	$(VENV_DIR)/bin/python tools/harvest_peerless_official.py $(ARGS)

crawl-monacor:
	$(VENV_DIR)/bin/python tools/harvest_monacor_official.py $(ARGS)

crawl-sica:
	$(VENV_DIR)/bin/python tools/harvest_sica_official.py $(ARGS)

crawl-faitalpro:
	$(VENV_DIR)/bin/python tools/harvest_faitalpro_official.py $(ARGS)

crawl-ciare:
	$(VENV_DIR)/bin/python tools/harvest_ciare_official.py $(ARGS)

catalog-plan:
	$(VENV_DIR)/bin/python tools/run_catalog_completion_cycle.py plan $(ARGS)

catalog-complete:
	$(VENV_DIR)/bin/python tools/run_catalog_completion_cycle.py run $(ARGS)

lint:
	$(VENV_DIR)/bin/python -m ruff check src tests ui_app.py

format:
	$(VENV_DIR)/bin/python -m ruff format src tests ui_app.py

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	@echo "Cleaned."
