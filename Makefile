.PHONY: venv install dev run check-version test test-fast test-ui test-catalog test-contracts test-smoke test-match lint format clean

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

check-version:
	$(VENV_DIR)/bin/python tools/check_version_consistency.py

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

test-contracts:
	$(VENV_DIR)/bin/python tests/test_repository_contracts.py

test-match:
	@if [ -z "$(MATCH)" ]; then echo "Usage: make test-match MATCH='acoustic-load smoke'"; exit 2; fi
	$(VENV_DIR)/bin/python tests/test_all.py --match "$(MATCH)"

lint:
	$(VENV_DIR)/bin/python -m ruff check src tests ui_app.py

format:
	$(VENV_DIR)/bin/python -m ruff format src tests ui_app.py

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	@echo "Cleaned."
