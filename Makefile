.PHONY: venv install dev run test test-match lint format clean

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

test-match:
	@if [ -z "$(MATCH)" ]; then echo "Usage: make test-match MATCH='dccav'"; exit 2; fi
	$(VENV_DIR)/bin/python tests/test_all.py --match "$(MATCH)"

lint:
	$(VENV_DIR)/bin/python -m ruff check src tests ui_app.py

format:
	$(VENV_DIR)/bin/python -m ruff format src tests ui_app.py

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	@echo "Cleaned."
